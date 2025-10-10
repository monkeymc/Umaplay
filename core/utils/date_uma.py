import re
from typing import Optional
from dataclasses import dataclass

from core.constants import MONTHS
from core.utils.text import fuzzy_ratio
from core.utils.logger import logger_uma


@dataclass(frozen=True)
class DateInfo:
    """Normalized career date information."""

    raw: str
    year_code: (
        int  # Y0..Y4 (0=Pre-debut, 1=Junior, 2=Classic, 3=Senior, 4=Final Season)
    )
    month: Optional[int]  # 1..12 or None (Final Season etc.)
    half: Optional[int]  # 1=Early, 2=Late, else None

    def as_key(self) -> str:
        """Human-readable compact key like 'Y3-Nov-2' or 'Y5'."""
        if self.month is None:
            return f"Y{self.year_code}"
        h = self.half if self.half in (1, 2) else 0
        m3 = {v: k for k, v in MONTHS.items()}.get(self.month, "???").title()
        return f"Y{self.year_code}-{m3}-{h}"


def date_is_terminal(di: Optional[DateInfo]) -> bool:
    """Final Season locks the timeline; Pre-debut is not terminal."""
    return bool(di and di.year_code == 4)  # 4 = Final Season in your parser


def date_is_pre_debut(di: Optional[DateInfo]) -> bool:
    return bool(di and di.year_code == 0)


def date_is_regular_year(di: Optional[DateInfo]) -> bool:
    return bool(di and di.year_code in (1, 2, 3))


def date_index(di: DateInfo) -> Optional[int]:
    """
    Map a date to a linear index for reasonableness checks.
    Pre-debut -> very small; Final -> very large.
    For Y1..Y3: step = (year-1)*24 + (month-1)*2 + (half-1)
    Returns None if month/half missing in Y1..Y3 (partial info).
    """
    if di.year_code == 0:  # Pre-debut
        return -10
    if di.year_code == 4:  # Final Season
        return 10_000
    if di.year_code in (1, 2, 3):
        if di.month is None or di.half not in (1, 2):
            return None
        return (di.year_code - 1) * 24 + (di.month - 1) * 2 + (di.half - 1)
    # Fallback
    return None


def date_cmp(a: DateInfo, b: DateInfo) -> int:
    """
    Compare dates with game semantics.
      return -1 if a < b (earlier), 0 if ~equal/undecidable, +1 if a > b (later).
    Rules:
      - Final(4) > any non-final; Pre(0) < any non-pre.
      - For Y1..Y3: compare year -> month -> half.
      - If some fields are None, only compare what’s known; if undecidable, return 0.
    """
    # handle terminals/pre-debut quickly
    if a.year_code == 4 and b.year_code != 4:
        return +1
    if b.year_code == 4 and a.year_code != 4:
        return -1
    if a.year_code == 0 and b.year_code != 0:
        return -1
    if b.year_code == 0 and a.year_code != 0:
        return +1

    # different years in Y1..Y3 vs others
    if a.year_code != b.year_code:
        return +1 if a.year_code > b.year_code else -1

    # same year
    if a.year_code in (1, 2, 3):
        # compare month if both known
        if a.month is not None and b.month is not None:
            if a.month != b.month:
                return +1 if a.month > b.month else -1
            # same month: compare half if both known
            if (a.half in (1, 2)) and (b.half in (1, 2)):
                if a.half != b.half:
                    return +1 if a.half > b.half else -1
                return 0
            # one half missing → undecidable; treat as equal (no backwards move)
            return 0
        # only one month known
        if a.month is not None and b.month is None:
            # new has more info; likely same-or-later but cannot prove ordering → equal
            return 0
        if a.month is None and b.month is not None:
            return 0
        # both months missing in a regular year → undecidable
        return 0

    # same year in {0,4}: already handled above
    return 0


def date_merge(prev: Optional[DateInfo], new: DateInfo) -> DateInfo:
    """
    If the new candidate lacks some detail (month/half) but is not earlier than prev,
    carry forward the known pieces from prev when they’re compatible.
    """
    if not prev:
        return new

    # If years differ and new is later/terminal, just use new as-is
    if new.year_code != prev.year_code:
        return new

    # Same year: fill missing month/half from prev only if month matches or new is missing it
    month = new.month if new.month is not None else prev.month
    half = (
        new.half
        if new.half in (1, 2)
        else (prev.half if (month == prev.month and prev.half in (1, 2)) else None)
    )

    return DateInfo(raw=new.raw, year_code=new.year_code, month=month, half=half)


def is_junior_year(di: DateInfo) -> bool:
    return di.year_code in (0, 1)


def is_pre_debut(di: DateInfo) -> bool:
    return di.year_code == 0


def is_final_season(di: DateInfo) -> bool:
    return di.year_code == 4


def is_summer(di: DateInfo) -> bool:
    """Jul/Aug in any regular year."""
    return (di.month in (7, 8)) and (di.year_code in (2, 3))


# Placeholder heuristics you can refine later
def is_summer_in_next_turn(di: DateInfo) -> bool:
    """
    For now: treat 'Late Jun' as 'summer in 1 turn' and 'Early Jul' as 'already summer'.
    """
    return di.month == 6 and di.half == 2 and di.year_code in (2, 3)


def is_summer_in_two_or_less_turns(di: DateInfo) -> bool:
    """
    TODO Danny: plug your real turn calendar.
    For now: treat 'Early/ Late Jun' as ≤2 turns to summer.
    """
    return di.month == 6 and di.year_code in (2, 3)


def near_mood_up_event(di: DateInfo) -> bool:
    """
    TODO: precise windows (early March / January early).
    For now: approximate those windows.
    """
    return (di.month == 3 and di.half == 1) or (di.month == 1 and di.half == 1)


def parse_career_date(s: str) -> DateInfo:
    """
    Robust parser for the career date banner.

    Examples:
      'Junior Year Early Nov'   -> Y1, Nov, Early(1)
      'Classic Year Late Mar'   -> Y2, Mar, Late(2)
      'Senior Year Early Dec'   -> Y3, Dec, Early(1)
      'Final Season'            -> Y4, month=None, half=None
      'Pre-Debut' / 'Pre Debut' -> Y0, month=None, half=None
    """
    if not isinstance(s, str):
        s = str(s)
        logger_uma.warning(f"Date is a tuple: {s}")
    raw = (s or "").strip()
    text = (
        raw.lower()
        .replace("career", "")
        .replace("career list", "")
        .lower()
        .replace("carcer", "")
    )

    text = re.sub(r"[^\w\s]", " ", text)  # kill punctuation/dashes
    text = re.sub(r"\s+", " ", text).strip()

    tokens = text.split()
    if text.startswith("car"):
        tokens = tokens[1:]
    if len(tokens) == 4:
        # e.g. "junior year early nov"
        text_year = f"{tokens[0]} {tokens[1]}"
        text_half = tokens[2]
        text_month = tokens[3]
    else:
        # fallback: use full text for each cluster
        text_year = text_half = text_month = text

    # thresholds for fuzzy acceptance
    THR_YEAR, THR_HALF, THR_MONTH = 0.51, 0.51, 0.51

    # ---- helpers ----
    def direct_pick(sval: str, aliases_map: dict) -> Optional[int]:
        for code, aliases in aliases_map.items():
            if sval in aliases:
                return code
        return None

    def best_from_aliases(sval: str, aliases_map: dict) -> tuple[Optional[int], float]:
        best_code, best_score = None, 0.0
        for code, aliases in aliases_map.items():
            score = max(fuzzy_ratio(sval, a) for a in aliases)
            if score > best_score:
                best_code, best_score = code, score
        return best_code, best_score

    # ---- YEAR / ERA ----
    YEAR_ALIASES = {
        0: ["pre debut", "pre-debut", "predebut"],
        4: ["final season", "final", "finale season", "finale"],
        1: ["junior year", "junior", "jr"],
        2: ["classic year", "classic", "clasic", "clossic"],
        3: ["senior year", "senior", "sr"],
    }

    y = direct_pick(text_year, YEAR_ALIASES)
    if y is None:
        best_y, best_y_score = best_from_aliases(text_year, YEAR_ALIASES)
        y = (
            best_y if (best_y is not None and best_y_score >= THR_YEAR) else 0
        )  # Y0 as default

    # short-circuit: for pre-debut/final season, month/half don't matter
    if y in (0, 4):
        return DateInfo(raw=raw, year_code=y, month=None, half=None)

    # ---- HALF (early/late) ----
    HALF_ALIASES = {
        1: ["early", "earIy", "ear1y"],  # tolerate OCR I/1
        2: ["late", "lafe"],
    }

    half = direct_pick(text_half, HALF_ALIASES)
    if half is None:
        best_h, best_h_score = best_from_aliases(text_half, HALF_ALIASES)
        half = best_h if (best_h is not None and best_h_score >= THR_HALF) else None

    # ---- MONTH ----
    # MONTHS should be defined in your module, e.g. {"jan":1, "feb":2, ...}
    MONTH_SYNONYMS = {
        "jan": ["jan", "january"],
        "feb": ["feb", "february"],
        "mar": ["mar", "march"],
        "apr": ["apr", "april"],
        "may": ["may"],
        "jun": ["jun", "june"],
        "jul": ["jul", "july"],
        "aug": ["aug", "august"],
        "sep": ["sep", "sept", "september"],
        "oct": ["oct", "october"],
        "nov": ["nov", "november"],
        "dec": ["dec", "december"],
    }

    # first try exact alias hit
    month = None
    for key, num in MONTHS.items():
        aliases = MONTH_SYNONYMS.get(key, [key])
        if text_month in aliases:
            month = num
            break

    # fuzzy fallback
    if month is None:
        best_m_num, best_m_score = None, 0.0
        for key, num in MONTHS.items():
            aliases = MONTH_SYNONYMS.get(key, [key])
            score = max(fuzzy_ratio(text_month, a) for a in aliases)
            if score > best_m_score:
                best_m_num, best_m_score = num, score
        month = best_m_num if best_m_score >= THR_MONTH else None

    return DateInfo(raw=raw, year_code=y, month=month, half=half)


def score_date_like(s: str) -> float:
    """
    Return a fuzzy score [0..1] expressing how much `s` looks like a valid career date.
    Used only to choose among multiple OCR variants.
    """
    t = (s or "").lower()
    # very permissive patterns
    keys_year = [
        "junior year",
        "classic year",
        "senior year",
        "final season",
        "finale season",
        "pre debut",
        "pre-debut",
    ]
    keys_half = ["early", "late"]
    keys_month = [
        "jan",
        "feb",
        "mar",
        "apr",
        "may",
        "jun",
        "jul",
        "aug",
        "sep",
        "oct",
        "nov",
        "dec",
        "january",
        "february",
        "march",
        "april",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    ]

    sy = max(fuzzy_ratio(t, k) for k in keys_year)
    sh = max(fuzzy_ratio(t, k) for k in keys_half)
    sm = max(fuzzy_ratio(t, k) for k in keys_month)

    # Final/Pre don't need half/month; regular years do.
    base = max(
        fuzzy_ratio(t, "final season"),
        fuzzy_ratio(t, "finale season"),
        fuzzy_ratio(t, "pre debut"),
        fuzzy_ratio(t, "pre-debut"),
    )
    if base >= 0.6:
        return max(base, sy)
    # Otherwise combine year + half + month (weights)
    return 0.5 * sy + 0.25 * sh + 0.25 * sm
