"""Stage 1: Multi-Vendor Steganographic Unicode & Typography Sanitizer.

Integrates techniques from `guillaumemeyer/watermarks-remover` and
`wiltodelta/remove-ai-watermarks` to strip:
1. Zero-width characters, joiners, soft hyphens, and invisible separators.
2. Unicode Tag block (U+E0000..U+E007F) and Variation Selectors (U+FE00..U+FE0F, U+E0100..U+E01EF).
3. Cyrillic/Greek homoglyph substitutions disguised as Latin characters.
4. Atypical Unicode carrier spaces (NBSP, thin space, hair space, ideographic space in ASCII).
5. AI-signature typographic footprints (e.g. overuse of isolated em-dashes).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, Set, Tuple

from .models import PipelineConfig, SanitizerStats


# Zero-width and invisible format characters
ZERO_WIDTH_CODEPOINTS: Set[int] = {
    0x00AD,  # Soft Hyphen
    0x034F,  # Combining Grapheme Joiner
    0x061C,  # Arabic Letter Mark
    0x115F,  # Hangul Choseong Filler
    0x1160,  # Hangul Jungseong Filler
    0x17B4,  # Khmer Vowel Inherent Aq
    0x17B5,  # Khmer Vowel Inherent Aa
    0x180B,  # Mongolian Free Variation Selector One
    0x180C,  # Mongolian Free Variation Selector Two
    0x180D,  # Mongolian Free Variation Selector Three
    0x180E,  # Mongolian Vowel Separator
    0x200B,  # Zero Width Space
    0x200C,  # Zero Width Non-Joiner
    0x200D,  # Zero Width Joiner
    0x200E,  # Left-to-Right Mark
    0x200F,  # Right-to-Left Mark
    0x202A,  # Left-to-Right Embedding
    0x202B,  # Right-to-Left Embedding
    0x202C,  # Pop Directional Formatting
    0x202D,  # Left-to-Right Override
    0x202E,  # Right-to-Left Override
    0x2060,  # Word Joiner
    0x2061,  # Function Application
    0x2062,  # Invisible Times
    0x2063,  # Invisible Separator
    0x2064,  # Invisible Plus
    0x2066,  # Left-to-Right Isolate
    0x2067,  # Right-to-Left Isolate
    0x2068,  # First Strong Isolate
    0x2069,  # Pop Directional Isolate
    0x206A,  # Inhibit Symmetric Swapping
    0x206B,  # Activate Symmetric Swapping
    0x206C,  # Inhibit Arabic Form Shaping
    0x206D,  # Activate Arabic Form Shaping
    0x206E,  # National Digit Shapes
    0x206F,  # Nominal Digit Shapes
    0xFEFF,  # Zero Width No-Break Space / BOM
    0xFFF9,  # Interlinear Annotation Anchor
    0xFFFA,  # Interlinear Annotation Separator
    0xFFFB,  # Interlinear Annotation Terminator
}

# Variation selectors (U+FE00..U+FE0F and U+E0100..U+E01EF)
VARIATION_SELECTOR_RANGES: Tuple[Tuple[int, int], ...] = (
    (0xFE00, 0xFE0F),
    (0xE0100, 0xE01EF),
)

# Unicode Tag Characters (U+E0000..U+E007F) used for invisible ASCII steganography
TAG_CHAR_RANGE: Tuple[int, int] = (0xE0000, 0xE007F)

# Atypical Unicode spaces used as carrier channels
ATYPICAL_SPACE_CODEPOINTS: Set[int] = {
    0x00A0,  # No-Break Space
    0x1680,  # Ogham Space Mark
    0x2000,  # En Quad
    0x2001,  # Em Quad
    0x2002,  # En Space
    0x2003,  # Em Space
    0x2004,  # Three-Per-Em Space
    0x2005,  # Four-Per-Em Space
    0x2006,  # Six-Per-Em Space
    0x2007,  # Figure Space
    0x2008,  # Punctuation Space
    0x2009,  # Thin Space
    0x200A,  # Hair Space
    0x202F,  # Narrow No-Break Space
    0x205F,  # Medium Mathematical Space
}

# Confusable Cyrillic & Greek homoglyphs commonly swapped for Latin characters
HOMOGLYPH_MAP: Dict[str, str] = {
    "\u0430": "a",  # Cyrillic small a
    "\u0435": "e",  # Cyrillic small ie
    "\u043e": "o",  # Cyrillic small o
    "\u0440": "p",  # Cyrillic small er
    "\u0441": "c",  # Cyrillic small es
    "\u0443": "y",  # Cyrillic small u
    "\u0445": "x",  # Cyrillic small ha
    "\u0456": "i",  # Cyrillic small byelorussian-ukrainian i
    "\u0458": "j",  # Cyrillic small je
    "\u04bb": "h",  # Cyrillic small shha
    "\u0455": "s",  # Cyrillic small dze
    "\u0410": "A",  # Cyrillic capital A
    "\u0412": "B",  # Cyrillic capital VE
    "\u0415": "E",  # Cyrillic capital IE
    "\u041a": "K",  # Cyrillic capital KA
    "\u041c": "M",  # Cyrillic capital EM
    "\u041d": "H",  # Cyrillic capital EN
    "\u041e": "O",  # Cyrillic capital O
    "\u0420": "P",  # Cyrillic capital ER
    "\u0421": "C",  # Cyrillic capital ES
    "\u0422": "T",  # Cyrillic capital TE
    "\u0425": "X",  # Cyrillic capital HA
    "\u03b1": "a",  # Greek small alpha (when isolated in Latin)
    "\u03bf": "o",  # Greek small omicron
    "\u03c1": "p",  # Greek small rho
    "\u03bd": "v",  # Greek small nu
    "\u0391": "A",  # Greek capital Alpha
    "\u0392": "B",  # Greek capital Beta
    "\u0395": "E",  # Greek capital Epsilon
    "\u0397": "H",  # Greek capital Eta
    "\u0399": "I",  # Greek capital Iota
    "\u039a": "K",  # Greek capital Kappa
    "\u039c": "M",  # Greek capital Mu
    "\u039d": "N",  # Greek capital Nu
    "\u039f": "O",  # Greek capital Omicron
    "\u03a1": "P",  # Greek capital Rho
    "\u03a4": "T",  # Greek capital Tau
    "\u03a7": "X",  # Greek capital Chi
    "\u03a5": "Y",  # Greek capital Upsilon
    "\u0396": "Z",  # Greek capital Zeta
}


def _is_variation_selector(cp: int) -> bool:
    for lo, hi in VARIATION_SELECTOR_RANGES:
        if lo <= cp <= hi:
            return True
    return False


def _is_tag_char(cp: int) -> bool:
    return TAG_CHAR_RANGE[0] <= cp <= TAG_CHAR_RANGE[1]


def count_hidden_unicode(text: str) -> int:
    """Count total invisible, tag, atypical space, and homoglyph characters."""
    count = 0
    for ch in text:
        cp = ord(ch)
        if (
            cp in ZERO_WIDTH_CODEPOINTS
            or _is_variation_selector(cp)
            or _is_tag_char(cp)
            or cp in ATYPICAL_SPACE_CODEPOINTS
            or ch in HOMOGLYPH_MAP
        ):
            count += 1
    return count


class UnicodeSanitizer:
    """Cleans steganographic Unicode watermarks and AI typographic footprints."""

    @classmethod
    def sanitize(cls, text: str, config: PipelineConfig) -> Tuple[str, SanitizerStats]:
        stats = SanitizerStats()
        if not config.enable_sanitizer or not text:
            return text, stats

        out_chars: list[str] = []
        n = len(text)

        for idx, ch in enumerate(text):
            cp = ord(ch)

            # 1. Strip zero-width & variation selectors
            if config.strip_zero_width and (
                cp in ZERO_WIDTH_CODEPOINTS or _is_variation_selector(cp)
            ):
                stats.zero_width_removed += 1
                continue

            # 2. Strip Unicode Tag characters (U+E0000..U+E007F)
            if config.strip_zero_width and _is_tag_char(cp):
                stats.tag_chars_removed += 1
                continue

            # 3. Normalize atypical carrier spaces
            if config.normalize_whitespace and cp in ATYPICAL_SPACE_CODEPOINTS:
                stats.atypical_spaces_normalized += 1
                out_chars.append(" ")
                continue

            # 4. Context-aware homoglyph normalization (only when adjacent to ASCII Latin)
            if config.normalize_homoglyphs and ch in HOMOGLYPH_MAP:
                prev_ch = text[idx - 1] if idx > 0 else ""
                next_ch = text[idx + 1] if idx + 1 < n else ""
                prev_is_latin = bool(prev_ch and ("a" <= prev_ch.lower() <= "z"))
                next_is_latin = bool(next_ch and ("a" <= next_ch.lower() <= "z"))
                if prev_is_latin or next_is_latin or (not prev_ch and not next_ch):
                    stats.homoglyphs_normalized += 1
                    out_chars.append(HOMOGLYPH_MAP[ch])
                    continue

            out_chars.append(ch)

        cleaned = "".join(out_chars)

        # 5. Normalize AI-typical punctuation footprints
        if config.normalize_ai_punctuation:
            cleaned, punct_fixes = cls._normalize_ai_typography(cleaned)
            stats.ai_punctuation_fixed = punct_fixes

        # 6. Normalize NFC composition for consistent token boundaries
        cleaned = unicodedata.normalize("NFC", cleaned)

        if stats.zero_width_removed:
            stats.details.append(f"Removed {stats.zero_width_removed} zero-width/invisible characters")
        if stats.tag_chars_removed:
            stats.details.append(f"Removed {stats.tag_chars_removed} Unicode Tag steganography characters")
        if stats.homoglyphs_normalized:
            stats.details.append(f"Normalized {stats.homoglyphs_normalized} confusable homoglyphs")
        if stats.atypical_spaces_normalized:
            stats.details.append(f"Normalized {stats.atypical_spaces_normalized} atypical carrier spaces")
        if stats.ai_punctuation_fixed:
            stats.details.append(f"Normalized {stats.ai_punctuation_fixed} AI-signature punctuation marks")

        return cleaned, stats

    @staticmethod
    def _normalize_ai_typography(text: str) -> Tuple[str, int]:
        """Replace telltale AI punctuation habits without harming meaning."""
        fixes = 0

        # English prose: convert excessive isolated em-dashes (word — word or word—word)
        # into natural comma/parenthetical or spaced en-dash / semicolon variation
        def _em_dash_replacer(match: re.Match[str]) -> str:
            nonlocal fixes
            left = match.group(1)
            right = match.group(2)
            fixes += 1
            # Alternate between comma-space and spaced hyphen/semicolon based on position
            if fixes % 2 == 1:
                return f"{left}, {right}"
            return f"{left} - {right}"

        text = re.sub(r"([A-Za-z0-9])\s*—\s*([a-z0-9])", _em_dash_replacer, text)

        # Chinese prose: normalize half-width or broken破折号 (`—` single vs `——` or comma)
        def _zh_dash_replacer(match: re.Match[str]) -> str:
            nonlocal fixes
            left = match.group(1)
            right = match.group(2)
            fixes += 1
            return f"{left}，{right}"

        text = re.sub(r"([\u4e00-\u9fff])\s*——\s*([\u4e00-\u9fff])", _zh_dash_replacer, text)

        # Curly quotes in ASCII context -> standard straight quotes
        curly_Pattern = re.compile(r"(?<=[A-Za-z0-9\s])[“”](?=[A-Za-z0-9\s.,!?;:])")
        curly_matches = len(curly_Pattern.findall(text))
        if curly_matches > 0:
            fixes += curly_matches
            text = curly_Pattern.sub('"', text)

        return text, fixes
