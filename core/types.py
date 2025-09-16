"""
Shared lightweight types and constants used across the project.

Keep this file small and focused on:
- Structural types (TypedDict / dataclasses) for detections, scans, and enrichments.
- Small enums/aliases and cross-module constants (e.g., mood map).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal, Optional, Tuple, TypedDict, Set


# ---------- Basic geometric aliases ----------

XYXY = Tuple[float, float, float, float]       # (x1, y1, x2, y2)
XYWH = Tuple[int, int, int, int]               # (x, y, w, h) integers (screen/client coords)
DetectionDict = Dict[str, object]

# ---------- Detection & screen classification ----------

class DetectionDict(TypedDict):
    """Normalized YOLO detection for a single box in last-screenshot coordinates."""
    idx: int
    name: str
    conf: float
    xyxy: XYXY


ScreenName = Literal["Raceday", "Inspiration", "Lobby", "LobbySummer", "Event", "Training", "Unknown"]

class ScreenInfo(TypedDict, total=False):
    """
    Optional diagnostic payload returned with ScreenName.
    Example keys:
      - training_buttons: int
      - tazuna: bool
      - infirmary: bool
      - counts: {class_name: count}
    """
    training_buttons: int
    tazuna: bool
    infirmary: bool
    counts: Dict[str, int]


# ---------- Training scan structures ----------

@dataclass(frozen=True)
class TileScanEntry:
    """
    Result of scanning a single training tile after click/raise.
    - tile_xyxy is in the same coordinate system as the last screenshot (left half capture).
    - supports is a list of raw detections (support_* classes) for that tile's overlay.
    """
    tile_idx: int
    tile_xyxy: XYXY
    tile_center_x: float
    supports: List[DetectionDict]


# ---------- Analyzers / support attributes ----------

FriendshipColor = Literal["gray", "blue", "green", "yellow", "pink", "unknown"]

@dataclass(frozen=True)
class FriendshipBarInfo:
    color: FriendshipColor
    progress_pct: int         # 0..100
    fill_ratio: float         # 0.0..1.0
    is_max: bool


@dataclass(frozen=True)
class SupportAttributes:
    """
    Attributes extracted for a single support crop via analyzers.
    """
    support_type: str
    support_type_score: float
    friendship_bar: FriendshipBarInfo
    has_hint: bool
    has_rainbow: bool


@dataclass(frozen=True)
class ScanTileEnriched:
    """
    Enriched tile entry after analyzers and ROI-based OCR:
      - supports_enriched mirrors 'supports' but with semantic attributes.
      - failure_pct is the parsed integer (0..100) for the “Failure XX%” bubble, or -1 if not found.
      - has_any_rainbow is a convenience flag aggregated from supports_enriched.
      - skipped_click tells whether we reused a pre-raised tile and avoided clicking.
    """
    tile_idx: int
    tile_xyxy: XYXY
    tile_center_x: float
    supports_enriched: List[SupportAttributes]
    has_any_rainbow: bool
    failure_pct: int
    skipped_click: bool


# ---------- Domain constants ----------

# Official names used by the detector for frequently accessed classes.
CLASS_TRAINING_BUTTON: str = "training_button"
CLASS_UI_STATS: str = "ui_stats"
CLASS_UI_TURNS: str = "ui_turns"
CLASS_UI_MOOD: str = "ui_mood"
CLASS_UI_GOAL: str = "ui_goal"
CLASS_UI_SKILLS_PTS: str = "ui_skills_pts"
CLASS_LOBBY_TAZUNA: str = "lobby_tazuna"
CLASS_LOBBY_INFIRMARY: str = "lobby_infirmary"

SUPPORT_CLASS_NAMES: Set[str] = {
    "support_card",
    "support_card_rainbow",
    "support_etsuko",
    "support_director",
}

# Mood categories and a simple numeric mapping used for downstream logic.
MoodName = Literal["AWFUL", "BAD", "NORMAL", "GOOD", "GREAT", "UNKNOWN"]
MOOD_MAP: Dict[MoodName, int] = {
    "AWFUL": 1,
    "BAD": 2,
    "NORMAL": 3,
    "GOOD": 4,
    "GREAT": 5,
    "UNKNOWN": -1,
}
