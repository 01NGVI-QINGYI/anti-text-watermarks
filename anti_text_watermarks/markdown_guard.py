"""AST-like Markdown, Code, LaTeX Math, and URL Span Protector.

Ensures that statistical watermark disruption, synonym substitution, and clause
reordering never corrupt fenced code blocks, inline code, LaTeX formulas, or URLs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


# Ordered patterns from broadest block-level to inline spans
_PROTECTED_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    # Fenced code blocks: ```lang ... ``` or ~~~ ... ~~~
    ("fenced_code", re.compile(r"(```[\s\S]*?```|~~~[\s\S]*?~~~)", re.MULTILINE)),
    # Display math blocks: $$ ... $$ or \[ ... \]
    ("display_math", re.compile(r"(\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\])", re.MULTILINE)),
    # Inline code: `...`
    ("inline_code", re.compile(r"(`[^`\n]+`)")),
    # Inline math: $...$ (non-space boundary) or \( ... \)
    ("inline_math", re.compile(r"(\$(?!\s)[^$\n]+?(?<!\s)\$|\\\([^\n]+?\\\))")),
    # Markdown link destination part or full image tag: ![alt](url)
    ("markdown_image", re.compile(r"(!\[[^\]]*\]\([^)]+\))")),
    # Raw URLs: https://... or http://...
    ("raw_url", re.compile(r"(https?://[^\s)\]>\"']+)")),
    # HTML tags: <tag ...>
    ("html_tag", re.compile(r"(</?[a-zA-Z][a-zA-Z0-9_-]*(?:\s+[^<>]*)?>)")),
]


@dataclass
class ProtectedDocument:
    """Holds masked text and the mapping table to restore protected spans."""

    masked_text: str
    placeholders: Dict[str, str] = field(default_factory=dict)
    span_types: Dict[str, str] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.placeholders)


class MarkdownGuard:
    """Masks and restores code blocks, formulas, URLs, and HTML tags."""

    TOKEN_PREFIX = "⟦ATW_"
    TOKEN_SUFFIX = "⟧"

    @classmethod
    def protect(cls, text: str, enabled: bool = True) -> ProtectedDocument:
        """Replace protected spans with atomic non-mutating tokens."""
        if not enabled or not text:
            return ProtectedDocument(masked_text=text)

        placeholders: Dict[str, str] = {}
        span_types: Dict[str, str] = {}
        counter = 0
        working = text

        for kind, pattern in _PROTECTED_PATTERNS:
            def _replacer(match: re.Match[str]) -> str:
                nonlocal counter
                original = match.group(0)
                # Avoid double-wrapping existing placeholders
                if cls.TOKEN_PREFIX in original:
                    return original
                token = f"{cls.TOKEN_PREFIX}{counter:04d}{cls.TOKEN_SUFFIX}"
                counter += 1
                placeholders[token] = original
                span_types[token] = kind
                return token

            working = pattern.sub(_replacer, working)

        return ProtectedDocument(
            masked_text=working,
            placeholders=placeholders,
            span_types=span_types,
        )

    @classmethod
    def restore(cls, doc: ProtectedDocument, mutated_text: str) -> str:
        """Restore all protected spans back into the mutated text."""
        if not doc.placeholders:
            return mutated_text

        restored = mutated_text
        # Restore in reverse order in case nested tokens ever occurred
        for token in sorted(doc.placeholders.keys(), reverse=True):
            original = doc.placeholders[token]
            if token in restored:
                restored = restored.replace(token, original)
            else:
                # Fallback if spaces were inserted inside placeholder by an external LLM
                mangled_pattern = re.escape(cls.TOKEN_PREFIX) + r"\s*" + token[len(cls.TOKEN_PREFIX):-len(cls.TOKEN_SUFFIX)] + r"\s*" + re.escape(cls.TOKEN_SUFFIX)
                restored = re.sub(mangled_pattern, lambda _: original, restored)

        return restored

    @classmethod
    def is_placeholder(cls, token: str) -> bool:
        """Check whether a token contains or is a protected placeholder."""
        return cls.TOKEN_PREFIX in token
