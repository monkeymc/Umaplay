import re
from typing import Optional, Sequence, Tuple
import unicodedata
from difflib import SequenceMatcher

# --- lightweight normalization for OCR-y text ---
def _normalize_ocr(s: str) -> str:
    if not s:
        return ""
    # strip accents
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))

    # unify look-alikes that OCR often confuses
    # roman numeral I (U+2160..216F), fullwidth digits/letters, etc.
    trans = str.maketrans({
        "Ⅰ": "1", "Ⅱ": "2", "Ⅲ": "3", "Ⅳ": "4", "Ⅴ": "5",
        "Ｉ": "1", "ｌ": "1", "l": "1", "I": "1", "|": "1", "!": "1",
        "０": "0", "Ｏ": "0", "○": "0", "o": "0", "O": "0", "0": "0",
        "５": "5", "Ｓ": "s", "s": "s", "S": "s", "5": "s", 
        "８": "8", "Ｂ": "b", "b": "b", "B": "b", "8": "b",
    })
    s = s.translate(trans)

    s = s.lower()
    # keep only letters/digits and collapse spaces
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def fuzzy_contains(haystack: str, needle: str, threshold: float = 0.80, return_ratio=False):
    """
    Return True if `needle` is (approximately) contained in `haystack`.
    1) direct substring after normalization
    2) sliding-window similarity using difflib.SequenceMatcher
    """
    hs = _normalize_ocr(haystack)
    nd = _normalize_ocr(needle)
    if not nd:
        if return_ratio:
            return False, 0
        return False

    # direct substring after normalization
    if nd in hs:
        if return_ratio:
            return True, 1
        return True

    # character-level sliding window around the same length
    n = len(nd)
    if n == 0 or len(hs) < n:
        swap = hs
        hs = nd
        nd = swap

    sm = SequenceMatcher()
    sm.set_seq2(nd)
    # try windows of length n and n+1 (helps when OCR inserts/drops a char)
    for win_len in (n, n + 1):
        if win_len > len(hs):
            continue
        for i in range(0, len(hs) - win_len + 1):
            window = hs[i:i + win_len]
            sm.set_seq1(window)
            ratio = sm.ratio()
            if  ratio >= threshold:

                if return_ratio:
                    return True, ratio
            
    if return_ratio:
        return False, 0
    return False

def fuzzy_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()

def fuzzy_best_match(text: str, targets: Sequence[str]) -> Tuple[Optional[str], float]:
    best, score = None, 0.0
    for t in targets:
        r = fuzzy_ratio(text, t)
        if r > score:
            best, score = t, r
    return best, score
