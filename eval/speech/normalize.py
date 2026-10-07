"""Speech transcript normalisation and transliteration for ASR scoring.

Transliteration Library Documentation:
    This module uses `indic-transliteration` (specifically `indic_transliteration.sanscript`)
    for script conversions between Devanagari and Roman text.
    
    Why indic-transliteration:
    `indic-transliteration` maps Devanagari syllabary to Roman phonetic schemes
    (such as ITRANS and IAST) and vice-versa. For code-switched Hinglish and Hindi,
    the ITRANS scheme (`sanscript.ITRANS`) converts Devanagari phonemes into standard
    Latin characters without introducing Unicode diacritics (like macrons or underdots).
    This allows direct edit-distance calculation against Romanised reference transcripts.
    Furthermore, `sanscript.transliterate` preserves characters belonging to the target
    script; ASCII English words remain untouched during Devanagari-to-Roman conversion,
    and existing Devanagari words stay intact during Roman-to-Devanagari conversion.

Scoring Modes:
    1. 'raw': Standard text clean-up without script conversion.
    2. 'roman': Converts all Devanagari text to Roman script via ITRANS.
    3. 'devanagari': Converts all Roman text to Devanagari script via ITRANS.

Normalisation pipeline:
    - Unicode NFC normalization
    - Script transliteration (in 'roman' or 'devanagari' mode)
    - Lowercase conversion
    - Devanagari digit to ASCII digit mapping (०-९ -> 0-9)
    - Punctuation and symbol removal (dandas, brackets, quotes, currency marks)
    - Expansion of spelling variants and compound verb spacing
    - Collapsing consecutive whitespace
"""

from __future__ import annotations

import re
import string
import unicodedata
from typing import Dict, Optional

from indic_transliteration import sanscript

# Mapping of Devanagari numerals (U+0966..U+096F) to standard ASCII digits (0..9)
DEV_TO_ASCII_DIGITS: dict[int, str] = str.maketrans("०१२३४५६७८९", "0123456789")

# Default dictionary of common conversational Hinglish & Hindi spelling variants.
# Focuses on compound verb spacing, colloquial chat spellings, and frequent ASR alternates.
DEFAULT_SPELLING_VARIANTS: Dict[str, str] = {
    # Hinglish compound verb contractions
    "kardo": "kar do",
    "kardena": "kar dena",
    "kardi": "kar di",
    "karlo": "kar lo",
    "karlena": "kar lena",
    "karwao": "karwao",
    "karta": "karta",
    "hoga": "hoga",
    "raha": "raha",
    # Common conversational contractions & phonetic spellings
    "nahin": "nahi",
    "haan": "haan",
    "han": "haan",
    "hnn": "haan",
    "thik": "theek",
    "bohot": "bahut",
    "bht": "bahut",
    "plz": "please",
    "plez": "please",
    "plse": "please",
    "kyu": "kyun",
    "kyon": "kyun",
    "accha": "achha",
    "acha": "achha",
    # Devanagari compound verbs & variant spellings
    "करदो": "कर दो",
    "करदेना": "कर देना",
    "करदी": "कर दी",
    "करलो": "कर लो",
    "हॉ": "हाँ",
    "नही": "नहीं",
    "ठीख": "ठीक",
    "थैंक्स": "थैंक्यू",
}


def normalize_text(
    text: str,
    mode: str = "raw",
    spelling_variants: Optional[Dict[str, str]] = None,
) -> str:
    """Normalises speech transcripts for reproducible Word and Character Error Rate evaluation.

    Args:
        text: Input transcript string.
        mode: Script handling mode ('raw', 'roman', or 'devanagari').
        spelling_variants: Optional custom dictionary mapping variant spellings to standard forms.
            Extends and overrides DEFAULT_SPELLING_VARIANTS.

    Returns:
        Cleaned, normalized string ready for jiwer scoring.

    Raises:
        ValueError: If mode is not one of ('raw', 'roman', 'devanagari').
    """
    if not text:
        return ""

    norm_mode = (mode or "raw").lower().strip()
    if norm_mode not in ("raw", "roman", "devanagari"):
        raise ValueError(
            f"Unsupported scoring mode: '{mode}'. Expected one of: 'raw', 'roman', 'devanagari'."
        )

    # Step 1: Unicode NFC normalisation
    cleaned = unicodedata.normalize("NFC", text)

    # Step 2: Transliteration according to mode
    if norm_mode == "roman":
        # Convert any Devanagari text to Roman via ITRANS
        cleaned = sanscript.transliterate(cleaned, sanscript.DEVANAGARI, sanscript.ITRANS)
    elif norm_mode == "devanagari":
        # Convert any Roman characters to Devanagari via ITRANS
        cleaned = sanscript.transliterate(cleaned, sanscript.ITRANS, sanscript.DEVANAGARI)

    # Step 3: Lowercase conversion
    cleaned = cleaned.lower()

    # Step 4: Map Devanagari digits to ASCII digits (०-९ -> 0-9)
    cleaned = cleaned.translate(DEV_TO_ASCII_DIGITS)

    # Step 5: Strip punctuation and symbols (Unicode categories P* and S*, plus ASCII punctuation)
    # Replaces matching characters with space so hyphenated words or slash-separated terms don't stick.
    char_list: list[str] = []
    for ch in cleaned:
        cat = unicodedata.category(ch)
        if cat.startswith(("P", "S")) or ch in string.punctuation:
            char_list.append(" ")
        else:
            char_list.append(ch)
    cleaned = "".join(char_list)

    # Step 6: Expand spelling variants using whitespace-delimited word boundaries
    # Merge default variants with any caller overrides
    variants_map = dict(DEFAULT_SPELLING_VARIANTS)
    if spelling_variants:
        variants_map.update(spelling_variants)

    # Apply variant replacements
    for target, replacement in variants_map.items():
        pattern = r"(?<!\S)" + re.escape(target.lower()) + r"(?!\S)"
        cleaned = re.sub(pattern, replacement, cleaned)

    # Step 7: Collapse consecutive whitespace and strip edges
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned
