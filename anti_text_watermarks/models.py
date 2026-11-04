"""Data structures and configuration models for anti-text-watermarks."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PipelineConfig:
    """Configuration for the multi-stage anti-watermark pipeline."""

    # Preset mode: "stealth", "balanced", "aggressive", "dipper", "backtranslate", "custom"
    preset: str = "balanced"

    # Stage 1: Unicode & Typography Sanitizer
    enable_sanitizer: bool = True
    strip_zero_width: bool = True
    normalize_homoglyphs: bool = True
    normalize_whitespace: bool = True
    normalize_ai_punctuation: bool = True
    protect_markdown: bool = True

    # Stage 2: Entropy-Calibrated Context-Window Cascade Disruptor (Offline)
    enable_entropy_disruptor: bool = True
    # Context window h used by statistical watermarks like textGrain / SynthID (typically 3-5)
    context_window_size: int = 4
    # Target lexical perturbation ratio (0.0 to 1.0); OpenAI textGrain drops to 17% at ~0.25
    target_edit_rate: float = 0.26
    # Whether to apply clause reordering / voice inversion / structural particles
    enable_syntactic_shift: bool = True
    # Whether to scrub high-probability LLM stylistic clichés ("delve", "综上所述", etc.)
    scrub_ai_cliches: bool = True
    # Deterministic seed (None for randomized adversarial perturbation)
    seed: Optional[int] = 42

    # Stage 3: DIPPER-Style Controlled LLM Paraphraser (Optional Local Ollama / OpenAI API)
    enable_dipper_llm: bool = False
    # Lexical diversity dial (0, 20, 40, 60, 80, 100)
    lex_diversity: int = 40
    # Order/Syntactic diversity dial (0, 20, 40, 60, 80, 100)
    order_diversity: int = 40
    # Provider: "ollama" or "openai"
    llm_provider: str = "ollama"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = ""
    llm_model: str = "qwen2.5:7b"
    llm_temperature: float = 0.75

    # Stage 4: Multi-Pivot Round-Trip Back-Translation (Optional)
    enable_backtranslate: bool = False
    pivot_languages: List[str] = field(default_factory=lambda: ["German"])

    @classmethod
    def from_preset(cls, preset: str, **overrides: Any) -> "PipelineConfig":
        """Build a PipelineConfig from a named preset."""
        preset = (preset or "balanced").lower().strip()
        cfg = cls(preset=preset)
        if preset == "stealth":
            cfg.target_edit_rate = 0.14
            cfg.enable_syntactic_shift = False
            cfg.scrub_ai_cliches = True
            cfg.context_window_size = 5
        elif preset == "balanced":
            cfg.target_edit_rate = 0.26
            cfg.enable_syntactic_shift = True
            cfg.scrub_ai_cliches = True
            cfg.context_window_size = 4
        elif preset == "aggressive":
            cfg.target_edit_rate = 0.42
            cfg.enable_syntactic_shift = True
            cfg.scrub_ai_cliches = True
            cfg.context_window_size = 3
        elif preset == "dipper":
            cfg.target_edit_rate = 0.20
            cfg.enable_syntactic_shift = True
            cfg.enable_dipper_llm = True
            cfg.lex_diversity = 40
            cfg.order_diversity = 40
        elif preset == "backtranslate":
            cfg.target_edit_rate = 0.18
            cfg.enable_syntactic_shift = True
            cfg.enable_backtranslate = True
            cfg.pivot_languages = ["German", "Japanese"]

        for k, v in overrides.items():
            if hasattr(cfg, k) and v is not None:
                setattr(cfg, k, v)
        return cfg

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SanitizerStats:
    """Statistics from Stage 1 Unicode & Typography Sanitizer."""

    zero_width_removed: int = 0
    tag_chars_removed: int = 0
    homoglyphs_normalized: int = 0
    atypical_spaces_normalized: int = 0
    ai_punctuation_fixed: int = 0
    protected_spans_count: int = 0
    details: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DisruptionStats:
    """Statistics from Stage 2 Entropy-Calibrated Context-Window Disruptor."""

    total_tokens: int = 0
    high_entropy_candidates: int = 0
    tokens_perturbed: int = 0
    clauses_reordered: int = 0
    cliches_replaced: int = 0
    effective_edit_rate: float = 0.0
    ngram_windows_broken_ratio: float = 0.0
    replacements_log: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ForensicsMetrics:
    """Comprehensive watermark forensics and disruption evaluation metrics."""

    # Token & length metrics
    original_char_count: int = 0
    processed_char_count: int = 0
    original_token_count: int = 0
    processed_token_count: int = 0

    # Perturbation & context-hash breaking metrics
    token_edit_rate: float = 0.0
    ngram_3_broken_ratio: float = 0.0
    ngram_4_broken_ratio: float = 0.0
    ngram_5_broken_ratio: float = 0.0

    # Estimated textGrain survival probability (calibrated to OpenAI Technical Report curve)
    estimated_textgrain_before: float = 0.92
    estimated_textgrain_after: float = 0.12

    # Simulated Pivotal Z-Score & p-value (when secret key or blind entropy variance is tested)
    simulated_z_score_before: float = 0.0
    simulated_z_score_after: float = 0.0
    simulated_p_value_before: float = 1.0
    simulated_p_value_after: float = 1.0

    # Quality & Semantic preservation metrics
    semantic_similarity: float = 1.0
    ai_cliche_density_before: float = 0.0
    ai_cliche_density_after: float = 0.0
    hidden_unicode_count_before: int = 0
    hidden_unicode_count_after: int = 0

    # Per-token window heatmap for UI visualization (0 = intact window, 1 = broken window, 2 = directly modified token)
    token_heatmap: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PipelineResult:
    """Complete output of the anti-text-watermarks pipeline."""

    original_text: str
    output_text: str
    config: PipelineConfig
    sanitizer_stats: SanitizerStats
    disruption_stats: DisruptionStats
    forensics: ForensicsMetrics
    stages_executed: List[str] = field(default_factory=list)
    diff_segments: List[Dict[str, str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_text": self.original_text,
            "output_text": self.output_text,
            "config": self.config.to_dict(),
            "sanitizer_stats": self.sanitizer_stats.to_dict(),
            "disruption_stats": self.disruption_stats.to_dict(),
            "forensics": self.forensics.to_dict(),
            "stages_executed": self.stages_executed,
            "diff_segments": self.diff_segments,
            "warnings": self.warnings,
        }
