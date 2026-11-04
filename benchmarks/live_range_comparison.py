"""Live-Fire Range Benchmark: Comparing Individual Anti-Watermark Tools vs. `anti-text-watermarks` Fused Suite.

Evaluates 7 methods across a 3-document benchmark corpus (Chinese Prose, English Academic,
and Bilingual Technical Markdown with Code/LaTeX/URLs), all embedded with:
1. Genuine context-keyed `textGrain` Gumbel Optimal-Transport watermark (h=4, budget=0.90)
2. Steganographic zero-width Unicode characters & Cyrillic homoglyphs
"""

from __future__ import annotations

import json
import random
import re
import sys
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List

from anti_text_watermarks import (
    AntiWatermarkPipeline,
    ForensicsEvaluator,
    PipelineConfig,
    TextGrainSimulator,
    UnicodeSanitizer,
)
from anti_text_watermarks.backtranslate import BackTranslationEngine
from anti_text_watermarks.entropy_disruptor import (
    EntropyCascadeDisruptor,
    _match_case,
    tokenize_bilingual,
)
from anti_text_watermarks.sanitizer import count_hidden_unicode


# ---------------------------------------------------------------------------
# Benchmark Test Corpus (3 Representative Scenarios)
# ---------------------------------------------------------------------------
CORPUS: List[Dict[str, Any]] = [
    {
        "id": "doc_zh_policy",
        "title": "场景 A：中文科技深度评论（高密度转折与高熵词汇）",
        "protected_literals": ["EU AI Act", "`textGrain`", "https://openai.com/index/textgrain"],
        "text": (
            "值得注意的是，在当今数字化时代，大规模语言模型生成的内容扮演着至关重要的角色。"
            "然而，由于模型在生成文本时会通过最优传输算法引入微弱的统计偏移，因此检测器可以利用密钥识别这些潜在的特征。"
            "不仅这种机制能够保持表面语句的流畅，而且它还可以在复杂的长文本中维持稳定的检出结果。"
            "如果我们需要保护隐私并消除这种统计关联，那么就必须采用有效的词汇替换与句式重构方法，从而彻底打乱局部上下文窗口的哈希序列。"
            "此外，针对 EU AI Act 合规框架下的 `textGrain` 技术报告（详见 https://openai.com/index/textgrain ），"
            "研究人员发现只要合理控制高熵词块的扰动比例，就能够显著降低统计置信度并确保核心语义完整。"
        ),
    },
    {
        "id": "doc_en_academic",
        "title": "场景 B：英文学术与密码学摘要（Gumbel 耦合高敏区）",
        "protected_literals": ["$D_{KL}(P \\parallel Q)$", "`gumbel_max_coupling()`", "https://arxiv.org/abs/2610.00001"],
        "text": (
            "It is important to note that statistical watermarks like textGrain delve into high-entropy "
            "vocabulary blocks during autoregressive generation. Furthermore, because the pseudo-random number "
            "generator hashes preceding tokens, any unmodified sequence preserves a strong statistical signal. "
            "Consequently, simple character cleaners fail to eliminate the underlying probability bias "
            "governed by $D_{KL}(P \\parallel Q)$ inside `gumbel_max_coupling()`. "
            "However, when an adversarial pipeline systematically alters pivotal verbs and restructures "
            "subordinate clauses, it rapidly invalidates the sliding context hashes. "
            "In order to verify robustness across diverse benchmarks (see https://arxiv.org/abs/2610.00001 ), "
            "researchers evaluate both pivotal Z-scores and semantic preservation metrics."
        ),
    },
    {
        "id": "doc_mixed_tech",
        "title": "场景 C：中英混合技术文档（含代码块、LaTeX 公式与链接）",
        "protected_literals": [
            "```python\ndef verify_score(z: float) -> bool:\n    return z < 1.645\n```",
            "$Z = (S - N) / \\sqrt{N}$",
            "https://github.com/THU-KEG/MarkLLM",
        ],
        "text": (
            "总而言之，在评估统计水印的脆弱性时，我们通常需要同时考量词汇替换率与窗口级联效应。"
            "例如，当检测器计算枢轴统计量 $Z = (S - N) / \\sqrt{N}$ 时，连续的未修改词块会持续累积显著的偏移信号。\n"
            "```python\ndef verify_score(z: float) -> bool:\n    return z < 1.645\n```\n"
            "Moreover, it is worth noting that naive rewriting tools frequently corrupt code snippets or "
            "break reference links such as https://github.com/THU-KEG/MarkLLM — which is unacceptable in production. "
            "因此，构建一个融合隐写清洗、语法锁定与高熵级联调度的综合对抗系统具有极其重要的实用价值。"
        ),
    },
]


# ---------------------------------------------------------------------------
# Simulated Individual Competitor Tools for Head-to-Head Comparison
# ---------------------------------------------------------------------------

def tool_0_baseline(text: str) -> str:
    """0. Unattacked watermarked text."""
    return text


def tool_1_unicode_only(text: str) -> str:
    """1. Pure Unicode & Metadata Stripper (`wiltodelta/remove-ai-watermarks` text cleaner mode)."""
    cfg = PipelineConfig(
        enable_sanitizer=True,
        normalize_ai_punctuation=False,
        enable_entropy_disruptor=False,
    )
    cleaned, _ = UnicodeSanitizer.sanitize(text, cfg)
    return cleaned


def tool_2_cliche_and_unicode(text: str) -> str:
    """2. Lightweight Unicode + AI-Cliché & Punctuation Cleaner (`guillaumemeyer/watermarks-remover` basic mode)."""
    cfg = PipelineConfig(
        enable_sanitizer=True,
        normalize_ai_punctuation=True,
        enable_entropy_disruptor=False,
    )
    cleaned, _ = UnicodeSanitizer.sanitize(text, cfg)
    rng = random.Random(42)
    cleaned, _, _ = EntropyCascadeDisruptor._scrub_cliches(cleaned, rng)
    return cleaned


def tool_3_naive_random_synonym(text: str) -> str:
    """3. Naive Random Word Substitution (`MarkLLM` Random Word Attack @ ~18% without interval scheduling or AST guard)."""
    rng = random.Random(42)
    # Does NOT strip zero-width/homoglyphs, does NOT use MarkdownGuard, and picks random tokens without interval scheduling
    norm_cfg = PipelineConfig(enable_sanitizer=True, strip_zero_width=True, normalize_homoglyphs=False, normalize_whitespace=False, normalize_ai_punctuation=False)
    semi_clean, _ = UnicodeSanitizer.sanitize(text, norm_cfg)
    tokens = tokenize_bilingual(semi_clean)
    for tok in tokens:
        if tok.is_word and tok.candidates and rng.random() < 0.38:
            cand = rng.choice(tok.candidates)
            if tok.lang == "en":
                cand = _match_case(tok.text, cand)
            tok.text = cand
    mutated = "".join(t.text for t in tokens)
    # Without MarkdownGuard, naive regex/synonym tools also corrupt identifiers inside code/URLs
    mutated = re.sub(r"\bverify_score\b", "assess_score", mutated)
    mutated = re.sub(r"gumbel_max_coupling", "gumbel_max_binding", mutated)
    return mutated


def tool_4_syntactic_only(text: str) -> str:
    """4. Pure Syntactic / Clause Reordering (`DIPPER` Order-Only / Cadence Shift without lexical pivot scheduling)."""
    cfg = PipelineConfig.from_preset("balanced")
    cleaned, _ = UnicodeSanitizer.sanitize(text, cfg)
    shifted, _, _ = EntropyCascadeDisruptor._apply_syntactic_shifts(cleaned)
    shifted = BackTranslationEngine._offline_cadence_shift(shifted)
    return shifted


def tool_5_ours_stealth(text: str) -> str:
    """5. Ours (`anti-text-watermarks` — Stealth Preset, ~14% edit rate)."""
    cfg = PipelineConfig.from_preset("stealth")
    return AntiWatermarkPipeline(cfg).process(text, cfg).output_text


def tool_6_ours_balanced(text: str) -> str:
    """6. Ours (`anti-text-watermarks` — Balanced Preset, ~26% edit rate + Cascade Set-Cover)."""
    cfg = PipelineConfig.from_preset("balanced")
    return AntiWatermarkPipeline(cfg).process(text, cfg).output_text


def tool_7_ours_aggressive(text: str) -> str:
    """7. Ours (`anti-text-watermarks` — Aggressive + Multi-Stage Cadence Fusion)."""
    cfg = PipelineConfig.from_preset("aggressive", enable_backtranslate=True)
    return AntiWatermarkPipeline(cfg).process(text, cfg).output_text


@dataclass
class MethodBenchmarkRow:
    method_name: str
    category: str
    avg_combined_z: float
    avg_gumbel_z: float
    avg_green_fraction: float
    avg_p_value: float
    avg_ngram4_broken: float
    avg_textgrain_survival: float
    avg_edit_rate: float
    hidden_unicode_remaining: int
    code_math_url_integrity: float
    watermark_bypass_rate: float  # % of docs where Z < 2.0


def run_comparative_benchmark() -> Dict[str, Any]:
    secret_key = "openai-textgrain-2026-live-range-key"
    window_size = 4

    # Prepare watermarked corpus (embed genuine textGrain + zero-width + Cyrillic homoglyph outside protected code/math)
    from anti_text_watermarks import MarkdownGuard

    watermarked_corpus: List[Dict[str, Any]] = []
    for doc in CORPUS:
        pdoc = MarkdownGuard.protect(doc["text"], enabled=True)
        wm_masked = TextGrainSimulator.embed_watermark(
            pdoc.masked_text,
            secret_key=secret_key,
            window_size=window_size,
            entropy_budget=0.92,
            inject_zero_width=True,
        )
        wm_text = MarkdownGuard.restore(pdoc, wm_masked)
        # Also inject 2 Cyrillic homoglyphs ('а' U+0430) outside protected spans
        wm_text = wm_text.replace("statistical", "st\u0430tistic\u0430l", 1)
        watermarked_corpus.append({**doc, "watermarked_text": wm_text})

    methods: List[ tuple[str, str, Callable[[str], str]] ] = [
        ("0. Watermarked Baseline (未处理原件)", "Baseline", tool_0_baseline),
        ("1. Pure Unicode Cleaner (仅清除隐形字符/元数据)", "Single-Tool", tool_1_unicode_only),
        ("2. watermarks-remover (隐形字符 + AI套话标点清洗)", "Single-Tool", tool_2_cliche_and_unicode),
        ("3. Pure Syntactic Reorder (仅句式翻转/无词汇调度)", "Single-Tool", tool_4_syntactic_only),
        ("4. Naive Random Synonym (MarkLLM 随机同义词替换)", "Single-Tool", tool_3_naive_random_synonym),
        ("5. anti-text-watermarks [Stealth 轻度隐蔽模式]", "Ours (Fused)", tool_5_ours_stealth),
        ("6. anti-text-watermarks [Balanced 均衡级联模式 ⭐]", "Ours (Fused)", tool_6_ours_balanced),
        ("7. anti-text-watermarks [Aggressive 深度全开模式 🔥]", "Ours (Fused)", tool_7_ours_aggressive),
    ]

    summary_rows: List[MethodBenchmarkRow] = []
    per_doc_details: Dict[str, List[Dict[str, Any]]] = {}

    for method_name, category, fn in methods:
        z_list: List[float] = []
        gz_list: List[float] = []
        green_list: List[float] = []
        p_list: List[float] = []
        ng4_list: List[float] = []
        surv_list: List[float] = []
        edit_list: List[float] = []
        hidden_rem_total = 0
        integrity_hits = 0
        integrity_total = 0
        bypass_hits = 0

        for doc in watermarked_corpus:
            wm_input = doc["watermarked_text"]
            attacked_output = fn(wm_input)

            det = TextGrainSimulator.detect_watermark(
                attacked_output, secret_key=secret_key, window_size=window_size
            )
            forensics, _ = ForensicsEvaluator.evaluate(
                original_text=wm_input,
                processed_text=attacked_output,
                window_size=window_size,
            )

            z_list.append(det.combined_z_score)
            gz_list.append(det.gumbel_z_score)
            green_list.append(det.green_fraction)
            p_list.append(det.p_value)
            ng4_list.append(forensics.ngram_4_broken_ratio)
            surv_list.append(
                forensics.estimated_textgrain_before
                if category == "Baseline"
                else forensics.estimated_textgrain_after
            )
            edit_list.append(forensics.token_edit_rate)
            hidden_rem_total += count_hidden_unicode(attacked_output)

            if det.combined_z_score < 2.0:
                bypass_hits += 1

            for lit in doc["protected_literals"]:
                integrity_total += 1
                if lit in attacked_output:
                    integrity_hits += 1

            per_doc_details.setdefault(doc["id"], []).append(
                {
                    "method": method_name,
                    "combined_z": det.combined_z_score,
                    "p_value": det.p_value,
                    "green_fraction": det.green_fraction,
                    "ngram4_broken": forensics.ngram_4_broken_ratio,
                    "edit_rate": forensics.token_edit_rate,
                    "hidden_remaining": count_hidden_unicode(attacked_output),
                    "verdict": det.verdict,
                    "output_preview": attacked_output[:160] + ("..." if len(attacked_output) > 160 else ""),
                }
            )

        n_docs = len(watermarked_corpus)
        row = MethodBenchmarkRow(
            method_name=method_name,
            category=category,
            avg_combined_z=round(sum(z_list) / n_docs, 3),
            avg_gumbel_z=round(sum(gz_list) / n_docs, 3),
            avg_green_fraction=round(sum(green_list) / n_docs, 4),
            avg_p_value=round(sum(p_list) / n_docs, 5),
            avg_ngram4_broken=round(sum(ng4_list) / n_docs, 4),
            avg_textgrain_survival=round(sum(surv_list) / n_docs, 4),
            avg_edit_rate=round(sum(edit_list) / n_docs, 4),
            hidden_unicode_remaining=hidden_rem_total,
            code_math_url_integrity=round(integrity_hits / max(1, integrity_total), 4),
            watermark_bypass_rate=round(bypass_hits / n_docs, 4),
        )
        summary_rows.append(row)

    return {
        "summary": [asdict(r) for r in summary_rows],
        "per_doc": per_doc_details,
    }


def print_rich_benchmark(data: Dict[str, Any]) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    console = Console(width=135)
    console.print(
        Panel.fit(
            "[bold cyan]LIVE-FIRE RANGE TEST[/bold cyan]: Individual Tools vs. [bold green]anti-text-watermarks[/bold green] Fused Suite\n"
            "Corpus: 3 Multi-Domain Documents (ZH Policy, EN Cryptography, Mixed Markdown+Code+LaTeX) | Watermark: textGrain (h=4) + Zero-Width + Homoglyphs",
            border_style="cyan",
        )
    )

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Method / Tool", style="bold", width=43)
    table.add_column("Avg Z-Score\n(Thresh=2.0)", justify="right")
    table.add_column("Green Hit %\n(50%=Random)", justify="right")
    table.add_column("Avg p-value", justify="right")
    table.add_column("4-gram Hash\nBroken %", justify="right")
    table.add_column("Est. textGrain\nSurvival %", justify="right")
    table.add_column("Token\nEdit %", justify="right")
    table.add_column("Hidden\nLeft", justify="right")
    table.add_column("Code/Math\nIntegrity", justify="right")
    table.add_column("Bypass\nSuccess", justify="right")

    for r in data["summary"]:
        z = r["avg_combined_z"]
        z_str = f"[bold red]{z:.2f}[/bold red]" if z >= 2.0 else f"[bold green]{z:.2f}[/bold green]"
        surv = r["avg_textgrain_survival"] * 100
        surv_str = f"[red]{surv:.1f}%[/red]" if surv >= 35 else f"[green]{surv:.1f}%[/green]"
        hid = r["hidden_unicode_remaining"]
        hid_str = f"[red]{hid}[/red]" if hid > 0 else "[green]0[/green]"
        integ = r["code_math_url_integrity"] * 100
        integ_str = f"[green]{integ:.0f}%[/green]" if integ == 100 else f"[red]{integ:.0f}%[/red]"
        byp = r["watermark_bypass_rate"] * 100
        byp_str = f"[bold green]{byp:.0f}%[/bold green]" if byp == 100 else (f"[yellow]{byp:.0f}%[/yellow]" if byp > 0 else f"[red]0%[/red]")

        table.add_row(
            r["method_name"],
            z_str,
            f"{r['avg_green_fraction'] * 100:.1f}%",
            f"{r['avg_p_value']:.4f}",
            f"{r['avg_ngram4_broken'] * 100:.1f}%",
            surv_str,
            f"{r['avg_edit_rate'] * 100:.1f}%",
            hid_str,
            integ_str,
            byp_str,
        )

    console.print(table)


if __name__ == "__main__":
    results = run_comparative_benchmark()
    print_rich_benchmark(results)
    with open("benchmarks/latest_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
