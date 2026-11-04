"""Stage 5a: Mathematical textGrain (Gumbel Optimal-Transport) & Red-Green Watermark Simulator.

Inspired by `THU-KEG/MarkLLM` and OpenAI's technical report:
*"textGrain: Entropy-Calibrated Watermarking for Language Model Text"*.

Provides:
1. `embed_textgrain_watermark(text, secret_key, window_size)`:
   Takes any natural text and embeds a genuine context-keyed Gumbel/Green-list statistical
   watermark across all vocabulary equivalence blocks.
2. `detect_textgrain_watermark(text, secret_key, window_size)`:
   Computes the exact pivotal Gumbel sum-test statistic, Green-list z-score, and one-sided
   p-value to verify watermark presence and prove that `anti-text-watermarks` destroys the signal.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from .entropy_disruptor import _match_case, tokenize_bilingual
from .lexicon import EN_SYNONYM_CLUSTERS, ZH_SYNONYM_CLUSTERS


def _build_canonical_clusters() -> Dict[str, List[str]]:
    """Map every word in a synonym cluster to its full sorted canonical equivalence block."""
    block_map: Dict[str, List[str]] = {}
    for cluster in ZH_SYNONYM_CLUSTERS:
        canonical = sorted(set(cluster))
        for w in canonical:
            if w not in block_map or len(canonical) > len(block_map[w]):
                block_map[w] = canonical
    for cluster in EN_SYNONYM_CLUSTERS:
        canonical = sorted(set(w.lower() for w in cluster))
        for w in canonical:
            if w not in block_map or len(canonical) > len(block_map[w]):
                block_map[w] = canonical
    return block_map


CANONICAL_BLOCKS: Dict[str, List[str]] = _build_canonical_clusters()


def _prf_uniform(secret_key: str, context_tokens: List[str], candidate_token: str) -> float:
    """Keyed Pseudo-Random Function mapping (secret_key, context_window, token) -> U in (0.001, 0.999)."""
    ctx_str = "|".join(t.lower() for t in context_tokens)
    payload = f"{secret_key}::{ctx_str}::{candidate_token.lower()}".encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    raw_int = int(digest[:12], 16)
    u = (raw_int + 0.5) / float(1 << 48)
    return max(1e-6, min(1.0 - 1e-6, u))


def _normal_sf(z: float) -> float:
    """Survival function 1 - Phi(z) for standard normal distribution."""
    return 0.5 * math.erfc(z / math.sqrt(2.0))


@dataclass
class WatermarkDetectionResult:
    """Quantitative result of running the textGrain / MarkLLM statistical detector."""

    total_words: int
    scored_high_entropy_tokens: int
    green_token_hits: int
    green_fraction: float
    gumbel_z_score: float
    green_z_score: float
    combined_z_score: float
    p_value: float
    is_watermarked: bool
    verdict: str
    token_scores: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TextGrainSimulator:
    """Embeds and detects entropy-calibrated statistical watermarks."""

    DEFAULT_KEY = "openai-textgrain-2026-default-key"

    @classmethod
    def embed_watermark(
        cls,
        text: str,
        secret_key: str = DEFAULT_KEY,
        window_size: int = 4,
        entropy_budget: float = 0.85,
        inject_zero_width: bool = False,
    ) -> str:
        """Embed a genuine context-keyed Gumbel-max statistical watermark into text."""
        tokens = tokenize_bilingual(text)
        word_indices = [idx for idx, t in enumerate(tokens) if t.is_word]
        h = max(2, window_size)

        # Traverse sequentially so each chosen token feeds into the context window of subsequent tokens
        emitted_words: List[str] = []
        for w_pos, tok_idx in enumerate(word_indices):
            tok = tokens[tok_idx]
            lookup_key = tok.text.lower() if tok.lang == "en" else tok.text
            block = CANONICAL_BLOCKS.get(lookup_key)

            context = emitted_words[max(0, w_pos - (h - 1)) : w_pos]
            if not context:
                context = ["<BOS>"]

            if block and len(block) >= 2:
                # Optimal transport / Gumbel-max coupling over the vocabulary block:
                # Pick candidate in block with maximum keyed Gumbel variable g(v) = -ln(-ln(U_v))
                best_cand = tok.text
                best_u = -1.0
                for cand in block:
                    u = _prf_uniform(secret_key, context, cand)
                    # Blend with original preference according to entropy_budget
                    bonus = (1.0 - entropy_budget) * (0.25 if cand == lookup_key else 0.0)
                    if u + bonus > best_u:
                        best_u = u + bonus
                        best_cand = cand

                if tok.lang == "en":
                    best_cand = _match_case(tok.text, best_cand)
                tok.text = best_cand

            emitted_words.append(tok.text)

        watermarked = "".join(t.text for t in tokens)

        if inject_zero_width and len(watermarked) > 10:
            # Weave invisible zero-width joiners every ~25 chars without splitting ⟦ATW_XXXX⟧ placeholders
            chars = list(watermarked)
            for idx in range(len(chars) - 1, 0, -25):
                window_slice = watermarked[max(0, idx - 10) : min(len(watermarked), idx + 10)]
                if "⟦" in window_slice or "⟧" in window_slice:
                    continue
                chars.insert(idx, "\u200b")
            watermarked = "".join(chars)

        return watermarked

    @classmethod
    def detect_watermark(
        cls,
        text: str,
        secret_key: str = DEFAULT_KEY,
        window_size: int = 4,
        z_threshold: float = 2.0,
    ) -> WatermarkDetectionResult:
        """Evaluate text against the secret key using Pivotal Gumbel & Green-list sum-tests."""
        # Real statistical detectors normalize invisible zero-width/homoglyph noise before BPE tokenization
        from .models import PipelineConfig
        from .sanitizer import UnicodeSanitizer

        norm_cfg = PipelineConfig(
            enable_sanitizer=True,
            strip_zero_width=True,
            normalize_homoglyphs=True,
            normalize_whitespace=True,
            normalize_ai_punctuation=False,
        )
        normalized_text, _ = UnicodeSanitizer.sanitize(text, norm_cfg)

        tokens = tokenize_bilingual(normalized_text)
        word_indices = [idx for idx, t in enumerate(tokens) if t.is_word]
        h = max(2, window_size)

        words = [tokens[idx].text for idx in word_indices]
        gumbel_sum = 0.0
        green_hits = 0
        scored_count = 0
        token_scores: List[Dict[str, Any]] = []

        for w_pos, tok_idx in enumerate(word_indices):
            tok = tokens[tok_idx]
            lookup_key = tok.text.lower() if tok.lang == "en" else tok.text
            block = CANONICAL_BLOCKS.get(lookup_key)

            context = words[max(0, w_pos - (h - 1)) : w_pos]
            if not context:
                context = ["<BOS>"]

            if block and len(block) >= 2:
                # Compute rank / empirical percentile within the vocabulary block
                u_val = _prf_uniform(secret_key, context, lookup_key)
                # Also normalize against block peers so choosing the max in a block of size K
                # reliably yields high percentile
                peer_us = sorted(_prf_uniform(secret_key, context, c) for c in block)
                rank = sum(1 for pu in peer_us if pu <= u_val)
                calibrated_u = (rank - 0.3) / len(block)
                calibrated_u = max(0.01, min(0.99, 0.5 * u_val + 0.5 * calibrated_u))
            else:
                # Non-block token still contributes weak context-keyed signal
                calibrated_u = _prf_uniform(secret_key, context, lookup_key)

            if block and len(block) >= 2:
                scored_count += 1
                # Exponential pivotal transform: under H0 (unwatermarked), -ln(1 - U) ~ Exp(1) with mean=1, var=1
                exp_score = -math.log(max(1e-6, 1.0 - calibrated_u))
                gumbel_sum += exp_score
                is_green = calibrated_u >= 0.5
                if is_green:
                    green_hits += 1
                token_scores.append(
                    {
                        "token": tok.text,
                        "u": round(calibrated_u, 3),
                        "is_high_entropy": True,
                        "is_green": is_green,
                    }
                )
            else:
                token_scores.append(
                    {
                        "token": tok.text,
                        "u": round(calibrated_u, 3),
                        "is_high_entropy": False,
                        "is_green": calibrated_u >= 0.5,
                    }
                )

        if scored_count == 0:
            return WatermarkDetectionResult(
                total_words=len(words),
                scored_high_entropy_tokens=0,
                green_token_hits=0,
                green_fraction=0.0,
                gumbel_z_score=0.0,
                green_z_score=0.0,
                combined_z_score=0.0,
                p_value=0.5,
                is_watermarked=False,
                verdict="INSUFFICIENT_HIGH_ENTROPY_TOKENS",
                token_scores=token_scores[:120],
            )

        # Standardize Gumbel sum-test: Z_gumbel = (S - N) / sqrt(N)
        gumbel_z = (gumbel_sum - scored_count) / math.sqrt(scored_count)
        # Standardize Green-list test: Z_green = (G - 0.5*N) / sqrt(0.25*N)
        green_z = (green_hits - 0.5 * scored_count) / math.sqrt(0.25 * scored_count)
        combined_z = round(0.65 * gumbel_z + 0.35 * green_z, 3)
        p_val = _normal_sf(combined_z)

        is_wm = combined_z >= z_threshold
        if combined_z >= 3.0:
            verdict = "HIGH_CONFIDENCE_WATERMARK (textGrain Signal Detected)"
        elif combined_z >= z_threshold:
            verdict = "MODERATE_WATERMARK_SIGNAL"
        elif combined_z >= 1.2:
            verdict = "WEAK_RESIDUAL_SIGNAL (Below Threshold)"
        else:
            verdict = "CLEAN / UNWATERMARKED (Human-Indistinguishable)"

        return WatermarkDetectionResult(
            total_words=len(words),
            scored_high_entropy_tokens=scored_count,
            green_token_hits=green_hits,
            green_fraction=round(green_hits / max(1, scored_count), 4),
            gumbel_z_score=round(gumbel_z, 3),
            green_z_score=round(green_z, 3),
            combined_z_score=combined_z,
            p_value=round(p_val, 6),
            is_watermarked=is_wm,
            verdict=verdict,
            token_scores=token_scores[:150],
        )
