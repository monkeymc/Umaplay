from typing import Dict, Set
from core.types import MoodName


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

MOOD_MAP: Dict[MoodName, int] = {
    "AWFUL": 1,
    "BAD": 2,
    "NORMAL": 3,
    "GOOD": 4,
    "GREAT": 5,
    "UNKNOWN": -1,
}

MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

DEFAULT_TILE_TO_TYPE = {0: "SPD", 1: "STA", 2: "PWR", 3: "GUTS", 4: "WIT"}
