# /core/utils/race_index.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.settings import Settings
from core.utils.logger import logger_uma

DateKey = str  # "Y{year}-{MM}-{half}"

# ------------ helpers to build the in-game card title ------------
def _abbr_distance_category(cat: Optional[str]) -> str:
    """
    Game card shows '(Med)' for Medium. Other categories keep full word.
    """
    c = (cat or "").strip().lower()
    if c == "medium":
        return "Med"
    if c == "mile":
        return "Mile"
    if c == "sprint":
        return "Sprint"
    if c == "long":
        return "Long"
    if c == "short":
        return "Sprint"
    return (cat or "").title()

def _norm_distance(entry: Dict) -> str:
    """
    Prefer integer meters (e.g., 2000m). Fallback to distance_text with spaces removed.
    """
    dm = entry.get("distance_m")
    if isinstance(dm, (int, float)) and dm:
        try:
            return f"{int(dm)}m"
        except Exception:
            pass
    txt = str(entry.get("distance_text") or "")
    return txt.replace(" ", "").replace("ｍ", "m")

def build_display_title(entry: Dict) -> str:
    """
    What the race card prints on the left side, e.g.
      'Nakayama Turf 2000m (Med)'
    We intentionally omit 'Right/Left' and 'Inner/Outer' because the dataset
    doesn't provide them and OCR noise there is higher. The (rank) is validated
    separately via the badge color/ocr.
    """
    loc = str(entry.get("location") or "").strip()
    surf = str(entry.get("surface") or "").strip()
    dist = _norm_distance(entry)
    cat  = _abbr_distance_category(entry.get("distance_category"))
    base = f"{loc} {surf} {dist}"
    if cat:
        base += f" ({cat})"
    return base.strip()


def date_key_from_dateinfo(di) -> Optional[DateKey]:
    """
    Build a date key like 'Y2-12-2' from a DateInfo-like object.
    Returns None if month/half are missing or year_code not in {1,2,3}.
    """
    try:
        y = int(di.year_code)
        m = int(di.month)
        h = int(di.half)
    except Exception:
        return None
    if y not in (1, 2, 3):
        return None
    if m < 1 or m > 12 or h not in (1, 2):
        return None
    return f"Y{y}-{m:02d}-{h:d}"


class RaceIndex:
    """
    Lazy singleton index over datasets/in_game/races.json for:
      • date_key -> [ {name, rank, ...}, ... ]
      • race_name -> [date_key, ...]
    """
    _loaded: bool = False
    _date_to_entries: Dict[DateKey, List[Dict]] = {}
    _name_to_dates: Dict[str, List[DateKey]] = {}
    _name_to_entries: Dict[str, List[Dict]] = {}

    @classmethod
    def _ensure_loaded(cls) -> None:
        if cls._loaded:
            return
        path: Path = Settings.RACE_DATA_PATH
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger_uma.warning("[RaceIndex] Could not load races dataset: %s", e)
            data = {}

        # data is { race_name: [ {year_int, month, day, rank, order?, ...}, ... ], ... }
        for race_name, occs in (data or {}).items():
            name = str(race_name).strip()
            low = name.lower()
            for oc in occs or []:
                try:
                    y = int(oc.get("year_int"))
                    m = int(oc.get("month"))
                    d = int(oc.get("day"))  # "half" in our policy
                    key = f"Y{y}-{m:02d}-{d:d}"
                    entry = {"name": name, **oc}
                    # pre-compute display title used on the card
                    entry["display_title"] = build_display_title(entry)
                    # normalize optional order (1-based)
                    try:
                        entry["order"] = int(entry.get("order", 1)) or 1
                    except Exception:
                        entry["order"] = 1
                    # pre-compute display title used on the card
                    entry["display_title"] = build_display_title(entry)
                    cls._date_to_entries.setdefault(key, []).append(entry)
                    cls._name_to_dates.setdefault(low, []).append(key)
                    cls._name_to_entries.setdefault(low, []).append(entry)
                except Exception:
                    continue

        cls._loaded = True
        logger_uma.debug("[RaceIndex] Loaded races: %d dates, %d names",
                         len(cls._date_to_entries), len(cls._name_to_dates))

    @classmethod
    def by_date(cls, key: DateKey) -> List[Dict]:
        cls._ensure_loaded()
        return list(cls._date_to_entries.get(key, []))

    @classmethod
    def has_g1(cls, key: DateKey) -> bool:
        cls._ensure_loaded()
        return any((e.get("rank") == "G1") for e in cls._date_to_entries.get(key, []))

    @classmethod
    def pick_g1_name(cls, key: DateKey) -> Optional[str]:
        cls._ensure_loaded()
        for e in cls._date_to_entries.get(key, []):
            if e.get("rank") == "G1":
                return str(e.get("name"))
        return None

    @classmethod
    def entry_for_name_on_date(cls, race_name: str, key: DateKey) -> Optional[Dict]:
        """
        Return the single dataset entry for (race_name, date_key) if present.
        Includes pre-computed 'display_title', 'rank', and optional 'order' (default 1).
        """
        cls._ensure_loaded()
        low = (race_name or "").strip().lower()
        for e in cls._date_to_entries.get(key, []):
            if (e.get("name") or "").strip().lower() == low:
                return e
        return None

    @classmethod
    def order_for_name_on_date(cls, race_name: str, key: DateKey) -> int:
        e = cls.entry_for_name_on_date(race_name, key)
        if not e:
            return 1
        try:
            return int(e.get("order", 1)) or 1
        except Exception:
            return 1

    @classmethod
    def valid_date_for_race(cls, race_name: str, key: DateKey) -> bool:
        cls._ensure_loaded()
        return key in cls._name_to_dates.get((race_name or "").lower(), [])
    
    @classmethod
    def expected_titles_for_race(cls, race_name: str) -> List[Tuple[str, str]]:
        """
        Return a list of (display_title, rank) pairs across all occurrences of a race.
        Useful as a general fallback when date_key is unknown.
        """
        cls._ensure_loaded()
        low = (race_name or "").lower()
        out: List[Tuple[str, str]] = []
        for e in cls._name_to_entries.get(low, []) or []:
            title = str(e.get("display_title") or "").strip()
            rank  = str(e.get("rank") or "").strip().upper() or "UNK"
            if title:
                out.append((title, rank))
        # de-duplicate while keeping order
        seen = set()
        uniq = []
        for t in out:
            if t not in seen:
                uniq.append(t)
                seen.add(t)
        return uniq