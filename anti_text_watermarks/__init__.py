"""anti-text-watermarks: Unified Adversarial Toolkit against Statistical & Unicode Text Watermarks."""

from .evaluator import ForensicsEvaluator
from .markdown_guard import MarkdownGuard
from .models import (
    DisruptionStats,
    ForensicsMetrics,
    PipelineConfig,
    PipelineResult,
    SanitizerStats,
)
from .pipeline import AntiWatermarkPipeline, remove_watermarks
from .sanitizer import UnicodeSanitizer
from .simulator import TextGrainSimulator, WatermarkDetectionResult

__version__ = "1.0.0"

__all__ = [
    "AntiWatermarkPipeline",
    "DisruptionStats",
    "ForensicsEvaluator",
    "ForensicsMetrics",
    "MarkdownGuard",
    "PipelineConfig",
    "PipelineResult",
    "SanitizerStats",
    "TextGrainSimulator",
    "UnicodeSanitizer",
    "WatermarkDetectionResult",
    "remove_watermarks",
]
