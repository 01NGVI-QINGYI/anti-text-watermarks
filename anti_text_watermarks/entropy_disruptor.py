"""Stage 2: Entropy-Calibrated Context-Window Cascade Disruptor.

Combines insights from:
- OpenAI's `textGrain` technical report (Entropy-Calibrated Optimal Transport & Gumbel coupling)
- `THU-KEG/MarkLLM` (Substitution & Syntactic Attack Pipelines)
- `plll4zzx/mip_watermark_stealing` (Interval-optimized context-window hash invalidation)

Algorithm Overview:
1. Scrub high-probability AI multi-word clichés (`ZH_AI_CLICHES`, `EN_AI_CLICHES`).
2. Apply clause-level syntactic inversions (`ZH_SYNTACTIC_PATTERNS`, `EN_SYNTACTIC_PATTERNS`).
3. Segment text into a bilingual token stream while locking `MarkdownGuard` placeholders.
4. Identify all high-entropy candidate positions (content words + functional connectors).
5. Run a greedy/DP set-cover scheduler over sliding h-gram windows: select perturbation
   sites that maximize the fraction of invalidated h-gram context hashes under `target_edit_rate`.
"""

from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from .lexicon import (
    EN_AI_CLICHES,
    EN_SYNONYM_MAP,
    EN_SYNTACTIC_PATTERNS,
    ZH_AI_CLICHES,
    ZH_LEXICON_KEYS_SORTED,
    ZH_SYNONYM_MAP,
    ZH_SYNTACTIC_PATTERNS,
)
from .markdown_guard import MarkdownGuard
from .models import DisruptionStats, PipelineConfig


# High-entropy Chinese functional connectors (safe to swap in non-fixed contexts)
ZH_FUNCTIONAL_CONNECTORS: Dict[str, List[str]] = {
    "与": ["和", "同", "以及"],
    "和": ["与", "同", "及"],
    "以及": ["与", "还有", "连同"],
    "或者": ["或是", "抑或", "又或"],
    "关于": ["有关", "围绕", "针对"],
    "对于": ["针对", "就", "至于"],
    "根据": ["依据", "按照", "基于"],
    "按照": ["依据", "依照", "遵循"],
    "基于": ["依托", "立足于", "依据"],
    "通过": ["借助", "经由", "依靠"],
    "旨在": ["意在", "力求", "致力于"],
    "从而": ["进而", "借此", "由此"],
}


@dataclass
class TokenSpan:
    """A single token in the bilingual stream."""

    text: str
    is_word: bool
    lang: str  # "zh", "en", "punct", "space", "guard"
    entropy_weight: float = 0.0
    candidates: Optional[List[str]] = None


def tokenize_bilingual(text: str) -> List[TokenSpan]:
    """Segment text into protected placeholders, Chinese lexicon words, English words, and punctuation."""
    tokens: List[TokenSpan] = []
    n = len(text)
    i = 0

    # Pre-compile regexes anchored at current position
    guard_re = re.compile(r"⟦ATW_\d{4}⟧")
    en_word_re = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
    num_re = re.compile(r"\d+(?:\.\d+)?%?")
    space_re = re.compile(r"\s+")

    # Build fast first-char index for Chinese lexicon keys
    zh_first_char_map: Dict[str, List[str]] = {}
    for key in ZH_LEXICON_KEYS_SORTED:
        zh_first_char_map.setdefault(key[0], []).append(key)
    for fc, lst in zh_FUNCTIONAL_FIRST_CHAR_MAP.items():
        existing = zh_first_char_map.setdefault(fc, [])
        for item in lst:
            if item not in existing:
                existing.append(item)
        existing.sort(key=len, reverse=True)

    while i < n:
        ch = text[i]

        # 1. Protected MarkdownGuard token
        if ch == "⟦":
            m = guard_re.match(text, i)
            if m:
                tokens.append(TokenSpan(text=m.group(0), is_word=False, lang="guard"))
                i = m.end()
                continue

        # 2. Whitespace
        if ch.isspace():
            m = space_re.match(text, i)
            if m:
                tokens.append(TokenSpan(text=m.group(0), is_word=False, lang="space"))
                i = m.end()
                continue

        # 3. English word
        if "a" <= ch.lower() <= "z":
            m = en_word_re.match(text, i)
            if m:
                w = m.group(0)
                lw = w.lower()
                cands = EN_SYNONYM_MAP.get(lw)
                weight = 0.85 if cands else 0.15
                tokens.append(
                    TokenSpan(
                        text=w,
                        is_word=True,
                        lang="en",
                        entropy_weight=weight,
                        candidates=cands,
                    )
                )
                i = m.end()
                continue

        # 4. Numbers
        if ch.isdigit():
            m = num_re.match(text, i)
            if m:
                tokens.append(TokenSpan(text=m.group(0), is_word=True, lang="num", entropy_weight=0.0))
                i = m.end()
                continue

        # 5. Chinese character
        if "\u4e00" <= ch <= "\u9fff":
            matched_word: Optional[str] = None
            for cand_key in zh_first_char_map.get(ch, ()):
                if text.startswith(cand_key, i):
                    matched_word = cand_key
                    break

            if matched_word:
                cands = ZH_SYNONYM_MAP.get(matched_word) or ZH_FUNCTIONAL_CONNECTORS.get(matched_word)
                weight = 0.90 if matched_word in ZH_SYNONYM_MAP else 0.65
                tokens.append(
                    TokenSpan(
                        text=matched_word,
                        is_word=True,
                        lang="zh",
                        entropy_weight=weight,
                        candidates=cands,
                    )
                )
                i += len(matched_word)
                continue

            # Otherwise group up to 2 consecutive unmatched CJK chars (without swallowing a lexicon prefix)
            if i + 1 < n and "\u4e00" <= text[i + 1] <= "\u9fff":
                next_starts_lex = any(
                    text.startswith(cand_key, i + 1)
                    for cand_key in zh_first_char_map.get(text[i + 1], ())
                )
                if not next_starts_lex:
                    tokens.append(
                        TokenSpan(
                            text=text[i : i + 2],
                            is_word=True,
                            lang="zh",
                            entropy_weight=0.1,
                            candidates=None,
                        )
                    )
                    i += 2
                    continue

            tokens.append(TokenSpan(text=ch, is_word=True, lang="zh", entropy_weight=0.1, candidates=None))
            i += 1
            continue

        # 6. Punctuation or symbol
        tokens.append(TokenSpan(text=ch, is_word=False, lang="punct", entropy_weight=0.0))
        i += 1

    return tokens


# Helper index for Chinese functional connectors
zh_FUNCTIONAL_FIRST_CHAR_MAP: Dict[str, List[str]] = {}
for _k in ZH_FUNCTIONAL_CONNECTORS:
    zh_FUNCTIONAL_FIRST_CHAR_MAP.setdefault(_k[0], []).append(_k)


def _match_case(original: str, replacement: str) -> str:
    """Preserve capitalization style when replacing English words."""
    if not original or not replacement:
        return replacement
    if original.isupper() and len(original) > 1:
        return replacement.upper()
    if original[0].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


class EntropyCascadeDisruptor:
    """Disrupts statistical token watermarks by targeting high-entropy pivot sites."""

    @classmethod
    def disrupt(cls, text: str, config: PipelineConfig) -> Tuple[str, DisruptionStats]:
        stats = DisruptionStats()
        if not config.enable_entropy_disruptor or not text:
            return text, stats

        rng = random.Random(config.seed) if config.seed is not None else random.Random()
        working = text

        # Step 1: Scrub AI multi-word clichés
        if config.scrub_ai_cliches:
            working, cliche_count, cliche_logs = cls._scrub_cliches(working, rng)
            stats.cliches_replaced = cliche_count
            stats.replacements_log.extend(cliche_logs)

        # Step 2: Apply clause-level syntactic shifts
        if config.enable_syntactic_shift and config.target_edit_rate >= 0.15:
            working, reordered_count, syntax_logs = cls._apply_syntactic_shifts(working)
            stats.clauses_reordered = reordered_count
            stats.replacements_log.extend(syntax_logs)

        # Step 3: Tokenize & identify high-entropy perturbation candidates
        tokens = tokenize_bilingual(working)
        word_indices = [idx for idx, t in enumerate(tokens) if t.is_word]
        stats.total_tokens = len(word_indices)

        if not word_indices:
            return working, stats

        # Map each word position (0..W-1) to its index in `tokens`
        candidate_word_positions: List[int] = []
        for w_pos, tok_idx in enumerate(word_indices):
            tok = tokens[tok_idx]
            if tok.candidates:
                candidate_word_positions.append(w_pos)

        stats.high_entropy_candidates = len(candidate_word_positions)

        # Step 4: Interval-Optimized Context-Window Set Cover
        # In textGrain / SynthID, perturbing word w_pos invalidates h-gram windows
        # covering [w_pos, w_pos + h]. We select positions to maximize broken windows
        # while staying near `config.target_edit_rate`.
        h = max(2, config.context_window_size)
        num_words = len(word_indices)
        raw_budget = max(1, int(round(num_words * config.target_edit_rate)))
        cand_scale = min(1.0, config.target_edit_rate * 3.1)
        cand_budget = max(1, int(round(len(candidate_word_positions) * cand_scale)))
        target_edits = min(raw_budget, cand_budget)

        selected_word_positions = cls._schedule_optimal_pivots(
            candidate_positions=candidate_word_positions,
            tokens=tokens,
            word_indices=word_indices,
            total_words=num_words,
            window_size=h,
            max_edits=target_edits,
        )

        # Step 5: Execute synonym substitutions with context-hash divergence
        broken_windows: Set[int] = set()
        for w_pos in sorted(selected_word_positions):
            tok_idx = word_indices[w_pos]
            tok = tokens[tok_idx]
            if not tok.candidates:
                continue

            # Deterministically or pseudo-randomly pick a synonym that maximizes token distance
            chosen = cls._choose_divergent_synonym(tok.text, tok.candidates, w_pos, rng)
            if tok.lang == "en":
                chosen = _match_case(tok.text, chosen)

            if chosen != tok.text:
                stats.replacements_log.append(
                    {
                        "original": tok.text,
                        "replacement": chosen,
                        "type": "high_entropy_pivot",
                    }
                )
                tok.text = chosen
                stats.tokens_perturbed += 1
                for win_idx in range(max(0, w_pos - h + 1), min(num_words, w_pos + h)):
                    broken_windows.add(win_idx)

        reconstructed = "".join(t.text for t in tokens)

        total_changes = stats.tokens_perturbed + stats.cliches_replaced * 2 + stats.clauses_reordered * 3
        stats.effective_edit_rate = round(min(1.0, total_changes / max(1, stats.total_tokens)), 4)
        stats.ngram_windows_broken_ratio = round(
            min(1.0, (len(broken_windows) + stats.cliches_replaced * h + stats.clauses_reordered * h) / max(1, num_words)),
            4,
        )

        return reconstructed, stats

    @staticmethod
    def _scrub_cliches(
        text: str, rng: random.Random
    ) -> Tuple[str, int, List[Dict[str, str]]]:
        count = 0
        logs: List[Dict[str, str]] = []
        working = text

        # Chinese AI clichés
        for cliche, replacements in ZH_AI_CLICHES.items():
            if cliche in working:
                chosen = rng.choice(replacements)
                working = working.replace(cliche, chosen, 1)
                count += 1
                logs.append({"original": cliche, "replacement": chosen, "type": "ai_cliche_zh"})

        # English AI clichés (case-insensitive match, case-preserving replace)
        for cliche, replacements in EN_AI_CLICHES.items():
            pattern = re.compile(re.escape(cliche), re.IGNORECASE)
            match = pattern.search(working)
            if match:
                orig_span = match.group(0)
                chosen = _match_case(orig_span, rng.choice(replacements))
                working = working[: match.start()] + chosen + working[match.end() :]
                count += 1
                logs.append({"original": orig_span, "replacement": chosen, "type": "ai_cliche_en"})

        return working, count, logs

    @staticmethod
    def _apply_syntactic_shifts(text: str) -> Tuple[str, int, List[Dict[str, str]]]:
        count = 0
        logs: List[Dict[str, str]] = []
        working = text

        for pat_str, repl_str, desc in ZH_SYNTACTIC_PATTERNS:
            pat = re.compile(pat_str)
            m = pat.search(working)
            if m and not MarkdownGuard.is_placeholder(m.group(0)):
                new_text, n_subs = pat.subn(repl_str, working, count=1)
                if n_subs > 0 and new_text != working:
                    logs.append(
                        {
                            "original": m.group(0),
                            "replacement": desc,
                            "type": "syntactic_shift_zh",
                        }
                    )
                    working = new_text
                    count += n_subs

        for pat_str, repl_str, desc in EN_SYNTACTIC_PATTERNS:
            pat = re.compile(pat_str, re.IGNORECASE)
            m = pat.search(working)
            if m and not MarkdownGuard.is_placeholder(m.group(0)):
                new_text, n_subs = pat.subn(repl_str, working, count=1)
                if n_subs > 0 and new_text != working:
                    logs.append(
                        {
                            "original": m.group(0),
                            "replacement": desc,
                            "type": "syntactic_shift_en",
                        }
                    )
                    working = new_text
                    count += n_subs

        return working, count, logs

    @staticmethod
    def _schedule_optimal_pivots(
        candidate_positions: List[int],
        tokens: List[TokenSpan],
        word_indices: List[int],
        total_words: int,
        window_size: int,
        max_edits: int,
    ) -> List[int]:
        """Greedy Maximum-Coverage Interval Scheduler over sliding h-gram windows."""
        if not candidate_positions or max_edits <= 0:
            return []

        covered_windows: Set[int] = set()
        selected: List[int] = []
        remaining = set(candidate_positions)

        while remaining and len(selected) < max_edits:
            best_pos: Optional[int] = None
            best_score = -1.0

            for w_pos in remaining:
                tok = tokens[word_indices[w_pos]]
                # Windows affected by changing token at w_pos: [w_pos, w_pos + window_size - 1]
                affected = range(w_pos, min(total_words, w_pos + window_size))
                uncovered_gain = sum(1 for win in affected if win not in covered_windows)

                # Combine uncovered window gain with token's intrinsic entropy weight
                score = uncovered_gain * 1.5 + tok.entropy_weight
                if score > best_score:
                    best_score = score
                    best_pos = w_pos

            if best_pos is None:
                break

            selected.append(best_pos)
            remaining.remove(best_pos)
            for win in range(best_pos, min(total_words, best_pos + window_size)):
                covered_windows.add(win)

        return selected

    @staticmethod
    def _choose_divergent_synonym(
        original: str,
        candidates: List[str],
        position: int,
        rng: random.Random,
    ) -> str:
        """Select a synonym that alters hash/character structure while varying across positions."""
        if not candidates:
            return original
        if len(candidates) == 1:
            return candidates[0]

        # Score candidates by character difference from original so BPE tokenization shifts
        scored: List[Tuple[int, str]] = []
        orig_chars = set(original.lower())
        for idx, cand in enumerate(candidates):
            cand_chars = set(cand.lower())
            overlap = len(orig_chars & cand_chars)
            # Lower character overlap = higher BPE token divergence
            divergence = len(cand) - overlap
            # Mix position index to avoid repeating the same synonym in a paragraph
            tie_breaker = int(hashlib.md5(f"{cand}:{position}".encode("utf-8")).hexdigest()[:6], 16) % 5
            scored.append((divergence * 3 + tie_breaker + rng.randint(0, 2), cand))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]
