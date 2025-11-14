import random
import re
from time import sleep
from typing import Any, Dict, List, Optional, Sequence, Tuple, cast

from core.constants import DEFAULT_TILE_TO_TYPE, MOOD_MAP
from core.types import MoodName
from core.utils.logger import logger_uma


# ---------- Date parsing & helpers ----------
def normalize_mood(mood: object) -> Tuple[str, int]:
    """
    Accepts either 'GOOD' or ('GOOD', 4) and returns ('GOOD', 4).
    """
    if isinstance(mood, (tuple, list)) and len(mood) >= 1:
        mtxt = str(mood[0]).upper()
    else:
        mtxt = str(mood).upper()

    if mtxt in MOOD_MAP:
        mood_key: MoodName = cast(MoodName, mtxt)
    else:
        mood_key = "UNKNOWN"
    return (mtxt, MOOD_MAP[mood_key])


# ---------- Tile selection utilities ----------
def best_tile(
    sv_rows: List[Dict],
    *,
    allowed_only: bool = True,
    min_sv: float = -1.0,
    prefer_types: Optional[Sequence[str]] = None,
    tile_to_type: Optional[Dict[int, str]] = None,
) -> Optional[int]:
    """
    Return the tile_idx with the highest SV (risk-allowed, if requested).
    Tie-break with prefer_types order if provided.
    """
    tile_to_type = tile_to_type or DEFAULT_TILE_TO_TYPE
    rows = [r for r in sv_rows if (r.get("sv_total", 0.0) >= min_sv)]
    if allowed_only:
        rows = [r for r in rows if r.get("allowed_by_risk", False)]

    if not rows:
        return None

    # Primary sort: SV desc; tie-break: by preference rank, then lowest failure
    def pref_rank(idx: int) -> int:
        if not prefer_types:
            return 999
        t = tile_to_type.get(idx, "zzz")
        return prefer_types.index(t) if t in prefer_types else 999

    rows_sorted = sorted(
        rows,
        key=lambda r: (
            -float(r.get("sv_total", 0.0)),
            pref_rank(int(r["tile_idx"])),
            float(r.get("failure_pct", 100)),
        ),
    )
    return int(rows_sorted[0]["tile_idx"])


def best_wit_tile(
    sv_rows: List[Dict],
    *,
    allowed_only: bool = True,
    min_sv: float = 0.0,
    tile_to_type: Optional[Dict[int, str]] = None,
) -> Optional[int]:
    tile_to_type = tile_to_type or DEFAULT_TILE_TO_TYPE
    rows = [r for r in sv_rows if tile_to_type.get(int(r["tile_idx"])) == "WIT"]
    if allowed_only:
        rows = [r for r in rows if r.get("allowed_by_risk", False)]
    rows = [r for r in rows if r.get("sv_total", 0.0) >= min_sv]
    if not rows:
        return None
    rows_sorted = sorted(
        rows,
        key=lambda r: (
            -float(r.get("sv_total", 0.0)),
            float(r.get("failure_pct", 100)),
        ),
    )
    return int(rows_sorted[0]["tile_idx"])


def any_wit_rainbow(
    sv_rows: List[Dict], tile_to_type: Optional[Dict[int, str]] = None
) -> bool:
    """
    Weak heuristic: look for 'rainbow:' in notes for WIT tile.
    (Works with the notes produced by your compute_support_values.)
    """
    tile_to_type = tile_to_type or DEFAULT_TILE_TO_TYPE
    for r in sv_rows:
        if tile_to_type.get(int(r["tile_idx"])) != "WIT":
            continue
        for note in r.get("notes") or []:
            if "rainbow" in note.lower():
                return True
    return False


def tiles_with_hint(sv_rows: List[Dict]) -> List[int]:
    out = []
    for r in sv_rows:
        sv_by_type = r.get("sv_by_type") or {}
        hint_value = float(sv_by_type.get("hint_bluegreen", 0.0)) + float(
            sv_by_type.get("hint_orange_max", 0.0)
        )
        if hint_value > 1e-6:
            out.append(int(r["tile_idx"]))
            continue

        notes = r.get("notes") or []
        if any(
            ("hint" in note.lower())
            and ("+0.00" not in note)
            and ("skipped" not in note.lower())
            for note in notes
        ):
            out.append(int(r["tile_idx"]))
    return out


def director_tile_and_color(
    sv_rows: List[Dict],
) -> Tuple[Optional[int], Optional[str]]:
    """
    Very light inference from notes: "Director (blue): +0.50" etc.
    Returns (tile_idx, color) or (None, None).
    """
    for r in sv_rows:
        for note in r.get("notes") or []:
            m = re.search(r"director\s*\((blue|green|orange|yellow|max)\)", note, re.I)
            if m:
                return int(r["tile_idx"]), m.group(1).lower()
    return None, None


def click_training_tile(
    ctrl,
    training_state: List[Dict],
    tile_idx: int,
    *,
    clicks_range: list = [3, 5],
    pause_after: Optional[float] = None,
) -> bool:
    """
    Click the center of the training tile at `tile_idx` using the controller.
    Expects `tile_xyxy` to be in last-screenshot coordinates (as produced by your scan).

    Returns True on success, False otherwise.
    """
    tile = None

    for t in training_state:
        if int(t.get("tile_idx", -1)) == int(tile_idx):
            tile = t
            break
    if not tile:
        logger_uma.error(
            "click_training_tile: tile_idx %s not found in training_state", tile_idx
        )
        return False

    xyxy = tile["tile_xyxy"]
    clicks = random.randint(clicks_range[0], clicks_range[1])

    # Click center in *screen* coords (helper translates last-screenshot -> screen)
    ctrl.click_xyxy_center(xyxy, clicks=clicks)

    sleep(pause_after or 0.2)
    return True
