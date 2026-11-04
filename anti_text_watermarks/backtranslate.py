"""Stage 4: Multi-Pivot Round-Trip Translation Attack (`THU-KEG/MarkLLM` Translation Pipeline).

Destroys token-level optimal transport coupling by translating text through one or
more pivot languages (e.g., Chinese -> German -> Chinese, or English -> Japanese -> English),
completely re-tokenizing across orthogonal vocabulary partitions.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from .dipper_engine import DipperParaphraseEngine
from .models import PipelineConfig


# Offline structural cadence transformations that mimic cross-lingual round-trip syntax
_ZH_ROUNDTRIP_CADENCE_PATTERNS: List[Tuple[str, str]] = [
    (r"我们可以看到，?", "从结果中不难观察到，"),
    (r"這表明|这表明", "这一现象反映出"),
    (r"在很大程度上", "在相当大的比重上"),
    (r"起到了([^，。]{2,8})的作用", r"发挥了\1的效能"),
    (r"对([^，。]{2,12})产生了([^，。]{2,8})影响", r"给\1带来了\2作用"),
    (r"具有([^，。]{2,8})的特点", r"呈现出\1的特征"),
    (r"随着([^，。]{2,12})的不断发展", r"伴随\1的持续演进"),
    (r"在([^，。]{2,10})的背景下", r"处于\1的语境之中"),
]

_EN_ROUNDTRIP_CADENCE_PATTERNS: List[Tuple[str, str]] = [
    (r"\bIt is evident that\b", "Clearly,"),
    (r"\bplays an important role in\b", "contributes substantially to"),
    (r"\bhas a significant impact on\b", "greatly influences"),
    (r"\bin the context of\b", "within the framework of"),
    (r"\bas a consequence of\b", "owing to"),
    (r"\bwith the rapid development of\b", "as"),
]


class BackTranslationEngine:
    """Multi-hop round-trip translation attack engine."""

    @classmethod
    def run_roundtrip(cls, text: str, config: PipelineConfig) -> Tuple[str, Optional[str]]:
        if not config.enable_backtranslate or not text.strip():
            return text, None

        pivots = config.pivot_languages or ["German"]
        source_lang = cls._detect_primary_language(text)

        try:
            current = text
            for pivot in pivots:
                current = DipperParaphraseEngine._call_chat_completion(
                    base_url=config.llm_base_url,
                    api_key=config.llm_api_key,
                    model=config.llm_model,
                    system_prompt=(
                        f"Translate the user's text accurately into {pivot}. "
                        "Keep any placeholder tokens like ⟦ATW_0000⟧ completely unchanged. "
                        "Output ONLY the translated text."
                    ),
                    user_prompt=current,
                    temperature=0.4,
                )
            restored = DipperParaphraseEngine._call_chat_completion(
                base_url=config.llm_base_url,
                api_key=config.llm_api_key,
                model=config.llm_model,
                system_prompt=(
                    f"Translate the user's text back into natural, idiomatic {source_lang}. "
                    "Keep any placeholder tokens like ⟦ATW_0000⟧ completely unchanged. "
                    "Output ONLY the translated text."
                ),
                user_prompt=current,
                temperature=0.5,
            )
            if restored and restored.strip():
                return restored.strip(), None
            return cls._offline_cadence_shift(text), "Round-trip LLM returned empty; applied offline cadence shift."
        except Exception as exc:
            shifted = cls._offline_cadence_shift(text)
            return (
                shifted,
                f"Round-trip translation endpoint ({config.llm_base_url}) unavailable ({exc}); "
                "applied offline cross-lingual structural cadence transformation.",
            )

    @staticmethod
    def _detect_primary_language(text: str) -> str:
        zh_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        return "Chinese" if zh_chars > len(text) * 0.12 else "English"

    @staticmethod
    def _offline_cadence_shift(text: str) -> str:
        out = text
        for pat, repl in _ZH_ROUNDTRIP_CADENCE_PATTERNS:
            out = re.sub(pat, repl, out)
        for pat, repl in _EN_ROUNDTRIP_CADENCE_PATTERNS:
            out = re.sub(pat, repl, out, flags=re.IGNORECASE)
        return out
