"""Tests for speech transcript normalisation and transliteration.

Tests the five required hand-written examples containing mixed-script,
Devanagari, and English utterances, alongside edge cases, scoring modes,
numeral mappings, and custom spelling variant dictionaries.
"""

from __future__ import annotations

import unicodedata
import pytest

from eval.speech.normalize import DEFAULT_SPELLING_VARIANTS, normalize_text


# Hand-written test cases representing conversational Indian English, Hindi, and Hinglish
EXAMPLE_1_MIXED_SCRIPT_COMPLAINT = (
    "Mera refund status check kardo, please! Ticket #१२३४५."
)
EXAMPLE_2_HINDI_TELEPHONY_SCHEDULE = (
    "हाँ, कल सुबह १० बजे कॉल शेड्यूल करदो।"
)
EXAMPLE_3_MIXED_SCRIPT_SUPPORT_DOWNTIME = (
    "Technician ne subah ka time diya tha aur ab shaam ke 5 baj gaye, koi update nahin mila... "
    "Wi-Fi router abhi tak replace nahi hua?!"
)
EXAMPLE_4_ENGLISH_ESCALATION = (
    "  PLEASE cancel my monthly subscription (ID: #98760) IMMEDIATELY!!  "
)
EXAMPLE_5_MIXED_SCRIPT_BILLING = (
    "Account balance ₹५००० hai aur call-center se koi help nahin mil rahi; plz call back ASAP."
)


def test_handwritten_example_1_mixed_script():
    """Example 1: Mixed-script with punctuation, compound verb 'kardo', and Devanagari digits."""
    raw = normalize_text(EXAMPLE_1_MIXED_SCRIPT_COMPLAINT, mode="raw")
    # Devanagari digits mapped to ASCII, 'kardo' expanded to 'kar do', punctuation stripped
    assert raw == "mera refund status check kar do please ticket 12345"

    roman = normalize_text(EXAMPLE_1_MIXED_SCRIPT_COMPLAINT, mode="roman")
    # All Romanized
    assert "12345" in roman
    assert "kar do" in roman
    assert "refund" in roman
    assert "status" in roman


def test_handwritten_example_2_hindi_schedule():
    """Example 2: Hindi dialogue with danda, Devanagari numerals 10, and compound verb 'करदो'."""
    raw = normalize_text(EXAMPLE_2_HINDI_TELEPHONY_SCHEDULE, mode="raw")
    # Danda stripped, १० -> 10, करदो -> कर दो
    assert raw == "हाँ कल सुबह 10 बजे कॉल शेड्यूल कर दो"

    # In Roman mode, transliterates to Roman text with 10
    roman = normalize_text(EXAMPLE_2_HINDI_TELEPHONY_SCHEDULE, mode="roman")
    assert "10" in roman
    assert "kara do" in roman or "kar do" in roman or "do" in roman


def test_handwritten_example_3_mixed_script_downtime():
    """Example 3: Mixed script with contractions ('nahin' -> 'nahi'), hyphens, and ellipsis."""
    raw = normalize_text(EXAMPLE_3_MIXED_SCRIPT_SUPPORT_DOWNTIME, mode="raw")
    expected = (
        "technician ne subah ka time diya tha aur ab shaam ke 5 baj gaye koi update nahi mila "
        "wi fi router abhi tak replace nahi hua"
    )
    assert raw == expected


def test_handwritten_example_4_english_escalation():
    """Example 4: English customer dialogue with excess padding, parentheses, symbols, uppercase."""
    raw = normalize_text(EXAMPLE_4_ENGLISH_ESCALATION, mode="raw")
    assert raw == "please cancel my monthly subscription id 98760 immediately"


def test_handwritten_example_5_mixed_script_billing():
    """Example 5: Mixed script with Indian Rupee symbol, Devanagari numerals, and chat slang."""
    raw = normalize_text(EXAMPLE_5_MIXED_SCRIPT_BILLING, mode="raw")
    expected = (
        "account balance 5000 hai aur call center se koi help nahi mil rahi please call back asap"
    )
    assert raw == expected


def test_unicode_nfc_normalisation():
    """Verifies decomposed Unicode characters are normalised into canonical composed NFC form."""
    # Latin decomposed: 'e' + combining acute accent (U+0301) vs 'é' (U+00E9)
    decomposed_latin = "telephon\u0065\u0301c"
    composed_latin = "telephonéc"

    norm_decomposed = normalize_text(decomposed_latin, mode="raw")
    norm_composed = normalize_text(composed_latin, mode="raw")
    assert norm_decomposed == norm_composed == "telephonéc"

    # Devanagari decomposed: 'क' (U+0915) + nukta (U+093C) vs composed 'क़' (U+0958)
    decomposed_indic = "\u0915\u093c"
    composed_indic = "\u0958"
    assert normalize_text(decomposed_indic, mode="raw") == normalize_text(composed_indic, mode="raw")


def test_devanagari_digit_mapping():
    """Ensures all Devanagari digits (० through ९) map cleanly to ASCII 0 through 9."""
    dev_digits = "० १ २ ३ ४ ५ ६ ७ ८ ९"
    assert normalize_text(dev_digits, mode="raw") == "0 1 2 3 4 5 6 7 8 9"


def test_scoring_modes_distinction():
    """Proves the three scoring modes (raw, roman, devanagari) behave distinctly."""
    sample = "नमस्ते aapka account number kya hai"

    res_raw = normalize_text(sample, mode="raw")
    res_roman = normalize_text(sample, mode="roman")
    res_dev = normalize_text(sample, mode="devanagari")

    # In raw mode, Devanagari and Latin coexist
    assert "नमस्ते" in res_raw
    assert "account" in res_raw

    # In roman mode, no Devanagari script remains
    assert "नमस्ते" not in res_roman
    assert "namaste" in res_roman

    # In devanagari mode, Latin letters are transliterated to Devanagari
    assert "नमस्ते" in res_dev
    assert "account" not in res_dev


def test_custom_spelling_variants_override():
    """Checks custom spelling variant dictionary override."""
    sample = "mera voice bot slow hai"
    # Custom rule mapping 'slow' to 'dheema'
    custom_variants = {"slow": "dheema"}
    res = normalize_text(sample, mode="raw", spelling_variants=custom_variants)
    assert res == "mera voice bot dheema hai"


def test_invalid_mode_raises():
    """Checks that invalid scoring mode raises a descriptive ValueError."""
    with pytest.raises(ValueError, match="Unsupported scoring mode"):
        normalize_text("test sentence", mode="phonetic")


def test_empty_string_handling():
    """Verifies that empty or whitespace-only inputs safely return an empty string."""
    assert normalize_text("", mode="raw") == ""
    assert normalize_text("   \t\n  ", mode="roman") == ""
