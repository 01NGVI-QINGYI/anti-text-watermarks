"""Unified Orchestrator for the anti-text-watermarks multi-stage adversarial pipeline."""

from __future__ import annotations

from typing import Any, Optional

from .backtranslate import BackTranslationEngine
from .dipper_engine import DipperParaphraseEngine
from .entropy_disruptor import EntropyCascadeDisruptor
from .evaluator import ForensicsEvaluator
from .markdown_guard import MarkdownGuard
from .models import (
    DisruptionStats,
    PipelineConfig,
    PipelineResult,
    SanitizerStats,
)
from .sanitizer import UnicodeSanitizer


class AntiWatermarkPipeline:
    """Fuses Unicode sanitization, Entropy-Calibrated Context-Window Disruption,
    DIPPER-style controlled paraphrasing, and Round-Trip Back-Translation.
    """

    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        self.config = config or PipelineConfig.from_preset("balanced")

    def process(self, text: str, config: Optional[PipelineConfig] = None) -> PipelineResult:
        """Execute the full anti-watermark pipeline and compute forensic metrics."""
        cfg = config or self.config
        stages_executed: list[str] = []
        warnings: list[str] = []

        if not text:
            empty_forensics, _ = ForensicsEvaluator.evaluate("", "")
            return PipelineResult(
                original_text="",
                output_text="",
                config=cfg,
                sanitizer_stats=SanitizerStats(),
                disruption_stats=DisruptionStats(),
                forensics=empty_forensics,
            )

        working = text

        # Stage 1: Unicode & Typography Sanitizer
        if cfg.enable_sanitizer:
            working, sanitizer_stats = UnicodeSanitizer.sanitize(working, cfg)
            stages_executed.append("Stage 1: Multi-Vendor Unicode & Typography Sanitizer")
        else:
            sanitizer_stats = SanitizerStats()

        # Protect code blocks, inline code, LaTeX formulas, and URLs before lexical/syntactic mutation
        protected_doc = MarkdownGuard.protect(working, enabled=cfg.protect_markdown)
        sanitizer_stats.protected_spans_count = protected_doc.count
        working = protected_doc.masked_text

        # Stage 2: Entropy-Calibrated Context-Window Cascade Disruptor (Offline)
        if cfg.enable_entropy_disruptor:
            working, disruption_stats = EntropyCascadeDisruptor.disrupt(working, cfg)
            stages_executed.append(
                f"Stage 2: Entropy-Calibrated Context-Window Disruptor (h={cfg.context_window_size}, target={int(cfg.target_edit_rate * 100)}%)"
            )
        else:
            disruption_stats = DisruptionStats()

        # Stage 3: DIPPER-Style Controlled LLM Paraphraser (Optional)
        if cfg.enable_dipper_llm:
            working, dipper_warn = DipperParaphraseEngine.paraphrase(working, cfg)
            stages_executed.append(
                f"Stage 3: DIPPER Controlled Paraphraser (lex={cfg.lex_diversity}, order={cfg.order_diversity})"
            )
            if dipper_warn:
                warnings.append(dipper_warn)

        # Stage 4: Multi-Pivot Round-Trip Back-Translation (Optional)
        if cfg.enable_backtranslate:
            working, bt_warn = BackTranslationEngine.run_roundtrip(working, cfg)
            stages_executed.append(
                f"Stage 4: Multi-Pivot Round-Trip Translation ({' -> '.join(cfg.pivot_languages)})"
            )
            if bt_warn:
                warnings.append(bt_warn)

        # Restore protected Markdown, code, math, and URLs
        restored = MarkdownGuard.restore(protected_doc, working)

        # Stage 5: Forensics & Survival Curve Evaluation
        forensics, diff_segments = ForensicsEvaluator.evaluate(
            original_text=text,
            processed_text=restored,
            window_size=cfg.context_window_size,
        )
        stages_executed.append("Stage 5: MarkLLM / textGrain Forensics & Survival Evaluator")

        return PipelineResult(
            original_text=text,
            output_text=restored,
            config=cfg,
            sanitizer_stats=sanitizer_stats,
            disruption_stats=disruption_stats,
            forensics=forensics,
            stages_executed=stages_executed,
            diff_segments=diff_segments,
            warnings=warnings,
        )


def remove_watermarks(
    text: str,
    preset: str = "balanced",
    **config_overrides: Any,
) -> PipelineResult:
    """High-level convenience function to strip statistical & Unicode watermarks from text."""
    cfg = PipelineConfig.from_preset(preset, **config_overrides)
    pipeline = AntiWatermarkPipeline(cfg)
    return pipeline.process(text, cfg)
