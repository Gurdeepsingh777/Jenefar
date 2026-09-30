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



_INDEPENDENT_VOWELS = {
    "अ":"a","आ":"aa","इ":"i","ई":"ee","उ":"u","ऊ":"oo","ऋ":"ri",
    "ए":"e","ऐ":"ai","ओ":"o","औ":"au","अं":"an","अः":"ah",
}
_CONSONANTS = {
    "क":"k","ख":"kh","ग":"g","घ":"gh","ङ":"ng","च":"ch","छ":"chh","ज":"j","झ":"jh","ञ":"ny",
    "ट":"t","ठ":"th","ड":"d","ढ":"dh","ण":"n","त":"t","थ":"th","द":"d","ध":"dh","न":"n",
    "प":"p","फ":"ph","ब":"b","भ":"bh","म":"m","य":"y","र":"r","ल":"l","व":"v",
    "श":"sh","ष":"sh","स":"s","ह":"h","ळ":"l","क़":"q","ख़":"kh","ग़":"gh","ज़":"z","ड़":"r","ढ़":"rh",
}
_MATRAS = {
    "ा":"aa","ि":"i","ी":"ee","ु":"u","ू":"oo","ृ":"ri","े":"e","ै":"ai","ो":"o","ौ":"au",
}
_DIACRITICS = {"ं":"n","ँ":"n","ः":"h"}

def devanagari_to_roman(text: str) -> str:
    """Lightweight Hindi -> Roman transliteration with no external dependency."""
    output: list[str] = []
    chars = list(text)
    i = 0
    while i < len(chars):
        ch = chars[i]
        pair = ch + (chars[i + 1] if i + 1 < len(chars) else "")
        if pair in _INDEPENDENT_VOWELS:
            output.append(_INDEPENDENT_VOWELS[pair])
            i += 2
            continue
        if ch in _INDEPENDENT_VOWELS:
            output.append(_INDEPENDENT_VOWELS[ch])
            i += 1
            continue
        if ch in _CONSONANTS:
            base = _CONSONANTS[ch]
            next_ch = chars[i + 1] if i + 1 < len(chars) else ""
            if next_ch == "्":
                output.append(base)
                i += 2
                continue
            if next_ch in _MATRAS:
                output.append(base + _MATRAS[next_ch])
                i += 2
                continue
            output.append(base + "a")
            i += 1
            continue
        if ch in _MATRAS:
            output.append(_MATRAS[ch])
            i += 1
            continue
        if ch in _DIACRITICS:
            output.append(_DIACRITICS[ch])
            i += 1
            continue
        if "\u0900" <= ch <= "\u097f":
            # Unknown Devanagari symbol: keep the output readable rather than
            # leaking script into the Roman-Hinglish response.
            output.append(" ")
        else:
            output.append(ch)
        i += 1
    return _SPACE_RE.sub(" ", "".join(output)).strip()

def roman_hinglish_for_voice(text: str, *, max_chars: int = 700) -> str:
    """Create speech-friendly Roman-Hinglish for browser TTS."""
    value = enforce_hinglish(text, max_chars=max_chars)
    replacements = {
        "CPU": "C P U", "GPU": "G P U", "RAM": "ram",
        "AI": "A I", "UI": "U I", "URL": "U R L",
        "VRM": "V R M", "STT": "S T T", "TTS": "T T S",
        "HTTP": "H T T P", "GitHub": "GitHub",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    value = re.sub(r"[|*_#<>{}\\[\\]~^`]+", " ", value)
    value = re.sub(r"\\s+([,.;!?])", r"\\1", value)
    return _SPACE_RE.sub(" ", value).strip()[:max_chars].rstrip()

def enforce_hinglish(text: str, *, max_chars: int = 950) -> str:
    """Normalize assistant speech/output to compact Roman-Hinglish."""
    value = clean_for_speech(text, max_chars=max_chars)
    value = devanagari_to_roman(value)
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

__all__ = ["clean_for_speech", "enforce_hinglish", "roman_hinglish_for_voice", "devanagari_to_roman"]
