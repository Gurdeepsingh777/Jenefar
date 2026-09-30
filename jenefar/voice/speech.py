from __future__ import annotations

import re
import unicodedata

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_CODE_RE = re.compile(r"\x60\x60\x60.*?\x60\x60\x60", re.DOTALL)
_LINK_RE = re.compile(r"\[([^\]]+)\]\((?:[^()]|\([^)]*\))*\)")
_MD_MARKERS_RE = re.compile(r"[*_~\x60^#|]+")
_BULLET_RE = re.compile(r"(?m)^\s*(?:[-*•◦▪‣]|\d+[.)])\s+")
_SPACE_RE = re.compile(r"\s+")
_REPEAT_PUNCT_RE = re.compile(r"([!?.,])\1{2,}")

_LATIN1 = re.compile(r"[\\u0080-\\u00ff]")

def enforce_hinglish(text: str, *, max_chars: int = 950) -> str:
    """Normalize assistant speech/output to compact Roman-Hinglish."""
    value = clean_for_speech(text, max_chars=max_chars)
    replacements = {
        "हेलो": "Hello", "नमस्ते": "Namaste", "कैसे": "kaise",
        "मदद": "madad", "कर": "kar", "सकता": "sakta", "सकती": "sakti",
        "हूँ": "hoon", "है": "hai", "आप": "aap", "मैं": "main",
        "तुम": "tum", "क्या": "kya", "क्यों": "kyun", "कहाँ": "kahan",
        "अभी": "abhi", "बोलिए": "boliye", "बताइए": "bataiye",
        "धन्यवाद": "dhanyavaad",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    # Preserve normal English technical identifiers while removing Devanagari.
    value = re.sub(r"[\u0900-\u097f]+", " ", value)
    return _SPACE_RE.sub(" ", value).strip()[:max_chars].rstrip()

def clean_for_speech(text: str, *, max_chars: int = 950) -> str:
    """Turn rich LLM/markdown output into compact natural speech."""
    value = str(text or "").replace("\r", " ").replace("\n", " ")
    if _CODE_RE.search(value):
        value = _CODE_RE.sub(" code details screen par available hain. ", value)
    value = _LINK_RE.sub(r"\1", value)
    value = _URL_RE.sub("link", value)
    value = _BULLET_RE.sub("", value)
    value = _MD_MARKERS_RE.sub("", value)
    value = value.replace("{", " ").replace("}", " ")
    value = value.replace("[", " ").replace("]", " ")
    value = value.replace("<", " ").replace(">", " ")

    chars: list[str] = []
    for char in value:
        category = unicodedata.category(char)
        if category.startswith("S"):
            if char in "+-=/%₹$€£":
                chars.append(" ")
            continue
        chars.append(char)
    value = "".join(chars)
    value = _REPEAT_PUNCT_RE.sub(r"\1", value)
    value = _SPACE_RE.sub(" ", value).strip()

    if len(value) <= max_chars:
        return value

    pieces = re.split(r"(?<=[.!?।])\s+", value)
    summary: list[str] = []
    total = 0
    for piece in pieces:
        if not piece:
            continue
        extra = len(piece) + (1 if summary else 0)
        if total + extra > max_chars - 70 and summary:
            break
        summary.append(piece)
        total += extra
        if len(summary) >= 5:
            break

    if not summary:
        return value[:max_chars].rstrip() + "."
    return " ".join(summary).rstrip() + ". Full details screen par available hain."

__all__ = ["clean_for_speech"]
