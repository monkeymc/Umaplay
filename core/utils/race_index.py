# /core/utils/race_index.py
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import imagehash
from PIL import Image

from core.settings import Settings
from core.utils.logger import logger_uma
from core.utils.date_uma import DateInfo, date_index


_CANON_TRANSLATION = str.maketrans(
    {
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
    }
)
_CANON_NON_WORD = re.compile(r"[^a-z0-9]+")


def canonicalize_race_name(name: object) -> str:
    """Return a lowercase, punctuation-stripped key for race name matching."""

    if not name:
        return ""
    text = unicodedata.normalize("NFKC", str(name)).translate(_CANON_TRANSLATION)
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = _CANON_NON_WORD.sub(" ", text)
    return " ".join(text.split())

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
    cat = _abbr_distance_category(entry.get("distance_category"))
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


# --------------------------
# Unity Cup helpers
# --------------------------

# Fixed Unity Cup preseason schedule in career calendar
_UNITY_CUP_PRESEASON_DATES: Tuple[Tuple[int, int, int], ...] = (
    (1, 12, 2),  # Junior Late Dec
    (2, 6, 2),   # Classic Late Jun
    (2, 12, 2),  # Classic Late Dec
    (3, 6, 2),   # Senior Late Jun
)


def unity_cup_preseason_index(di: Optional[DateInfo]) -> Optional[int]:
    """Return 1..4 for the Unity Cup preseason stage inferred from this date.

    Instead of requiring an exact match on the scheduled date, this uses the
    linear date_index and picks the first scheduled preseason date whose index
    is >= the given date index. This lets us handle cases where our last known
    date is slightly earlier than the actual Unity Cup raceday, e.g. when the
    lobby date OCR lagged a bit.

    Returns None for dates after all preseasons, finals, or unknown/partial
    dates.
    """

    return unity_cup_next_preseason_index(di)


def unity_cup_next_preseason_index(di: Optional[DateInfo]) -> Optional[int]:
    """Return the next Unity Cup preseason index (1..4) on/after the given date.

    Uses the linear date_index to compare the current date against the fixed
    preseason schedule. Returns None if the date is unknown or all 4 preseasons
    are in the past.
    """

    if not isinstance(di, DateInfo):
        return None

    base_idx = date_index(di)
    if base_idx is None:
        return None

    for idx, (yy, mm, hh) in enumerate(_UNITY_CUP_PRESEASON_DATES, start=1):
        candidate = DateInfo(raw="", year_code=yy, month=mm, half=hh)
        cand_idx = date_index(candidate)
        if cand_idx is None:
            continue
        if cand_idx >= base_idx:
            return idx
    return None


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
    _banner_templates: Dict[str, Dict[str, object]] = {}
    _templates_loaded: bool = False

    @staticmethod
    def canonicalize(name: object) -> str:
        return canonicalize_race_name(name)

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
            canon_name = canonicalize_race_name(name)
            for oc in occs or []:
                try:
                    y = int(oc.get("year_int"))
                    m = int(oc.get("month"))
                    d = int(oc.get("day"))  # "half" in our policy
                    key = f"Y{y}-{m:02d}-{d:d}"
                    entry = {"name": name, **oc}
                    entry["canonical_name"] = canon_name
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
                    map_key = canon_name or canonicalize_race_name(name)
                    if map_key:
                        cls._name_to_dates.setdefault(map_key, []).append(key)
                        cls._name_to_entries.setdefault(map_key, []).append(entry)
                except Exception:
                    continue

        cls._load_banner_templates()
        cls._loaded = True
        logger_uma.debug(
            "[RaceIndex] Loaded races: %d dates, %d names",
            len(cls._date_to_entries),
            len(cls._name_to_dates),
        )

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
        canon = canonicalize_race_name(race_name)
        for e in cls._date_to_entries.get(key, []):
            stored = e.get("canonical_name") or canonicalize_race_name(e.get("name"))
            if stored == canon:
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
        canon = canonicalize_race_name(race_name)
        return key in cls._name_to_dates.get(canon, [])

    @classmethod
    def expected_titles_for_race(cls, race_name: str) -> List[Tuple[str, str]]:
        """
        Return a list of (display_title, rank) pairs across all occurrences of a race.
        Useful as a general fallback when date_key is unknown.
        """
        cls._ensure_loaded()
        canon = canonicalize_race_name(race_name)
        out: List[Tuple[str, str]] = []
        entries = cls._name_to_entries.get(canon, []) or []
        for e in entries:
            title = str(e.get("display_title") or "").strip()
            rank = str(e.get("rank") or "").strip().upper() or "UNK"
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

    @classmethod
    def _load_banner_templates(cls) -> None:
        if cls._templates_loaded:
            return

        idx_path = Settings.ROOT_DIR / "assets" / "races" / "templates" / "index.json"
        try:
            with open(idx_path, "r", encoding="utf-8") as f:
                mapping = json.load(f) or {}
        except Exception as e:
            logger_uma.warning("[RaceIndex] Could not load banner template index: %s", e)
            mapping = {}

        for race_name, rel_path in mapping.items():
            canon = canonicalize_race_name(race_name)
            if not canon:
                continue
            try:
                rel = str(rel_path or "").lstrip("/\\")
                template_path = Settings.ROOT_DIR / rel
                if not template_path.exists():
                    logger_uma.debug(
                        "[RaceIndex] Banner template missing on disk for '%s': %s",
                        race_name,
                        template_path,
                    )
                    continue

                with Image.open(template_path) as im:
                    if im.mode in {"P", "PA"}:
                        im = im.convert("RGBA")
                    rgb = im.convert("RGB")
                    ph = imagehash.phash(rgb)
                    width, height = rgb.size

                rel_norm = rel.replace("\\", "/")
                if rel_norm.startswith("web/public/"):
                    public_path = "/" + rel_norm[len("web/public/") :]
                else:
                    public_path = "/" + rel_norm

                cls._banner_templates[canon] = {
                    "name": race_name,
                    "path": str(template_path),
                    "public_path": public_path,
                    "hash_hex": str(ph),
                    "size": (width, height),
                }
            except Exception as e:
                logger_uma.debug(
                    "[RaceIndex] Failed to register banner template for '%s': %s",
                    race_name,
                    e,
                )

        cls._templates_loaded = True

    @classmethod
    def banner_template(cls, race_name: str) -> Optional[Dict[str, object]]:
        """Return banner template metadata (path, hash) for the given race name if known."""
        cls._ensure_loaded()
        canon = canonicalize_race_name(race_name)
        return cls._banner_templates.get(canon)

    @classmethod
    def all_banner_templates(cls) -> Dict[str, Dict[str, object]]:
        cls._ensure_loaded()
        return dict(cls._banner_templates)
