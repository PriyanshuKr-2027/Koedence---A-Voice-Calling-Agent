"""Speech evaluation package for VoCall.

Includes text normalization, transliteration routines, telephony simulation,
and WER/CER speech evaluation pipelines.
"""

from eval.speech.normalize import normalize_text

__all__ = ["normalize_text"]
