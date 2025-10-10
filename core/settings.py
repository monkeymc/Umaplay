from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    """Return environment variable (Umaplay_* has priority), else default."""
    return os.getenv(f"Umaplay_{name}", os.getenv(name, default))


def _env_bool(name: str, default: bool) -> bool:
    v = _env(name)
    if v is None:
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    v = _env(name)
    try:
        return int(v) if v is not None else default
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    v = _env(name)
    try:
        return float(v) if v is not None else default
    except Exception:
        return default


class Settings:
    """
    Class-style config holder (easy to import as `Settings.*` without instantiation).
    Adjust values below or override via environment variables prefixed with Umaplay_.
    """

    HOTKEY = "F2"
    DEBUG = _env_bool("DEBUG", default=True)
    HOST = "127.0.0.1"
    PORT = 8000

    _ROOT_DIR = Path(__file__).resolve().parents[1]  # repo root (parent of /core)
    RACE_DATA_PATH = _ROOT_DIR / "datasets" / "in_game" / "races.json"

    # --------- Training Configuration ---------
    # Undertrain threshold as a percentage (e.g., 6.0 for 6%)
    UNDERTRAIN_THRESHOLD: float = _env_float("UNDERTRAIN_THRESHOLD", default=6.0)
    # Number of top stats to focus on for undertraining
    TOP_STATS_FOCUS: int = _env_int("TOP_STATS_FOCUS", default=3)
    # Race if no good training options are available (default: False = skip race if no good training)
    RACE_IF_NO_GOOD_VALUE: bool = _env_bool("RACE_IF_NO_GOOD_VALUE", default=False)

    # --------- Project roots & paths ---------
    CORE_DIR: Path = Path(__file__).resolve().parent
    ROOT_DIR: Path = CORE_DIR.parent

    # Common directories
    ASSETS_DIR: Path = Path(_env("ASSETS_DIR") or (ROOT_DIR / "web/public"))
    MODELS_DIR: Path = Path(_env("MODELS_DIR") or (ROOT_DIR / "models"))
    DEBUG_DIR: Path = Path(_env("DEBUG_DIR") or (ROOT_DIR / "debug"))

    # Models & weights
    YOLO_WEIGHTS: Path = Path(_env("YOLO_WEIGHTS") or (MODELS_DIR / "uma.pt"))
    YOLO_WEIGHTS_NAV: Path = Path(
        _env("YOLO_WEIGHTS_NAV") or (MODELS_DIR / "uma_nav.pt")
    )
    IS_BUTTON_ACTIVE_CLF_PATH: Path = Path(
        _env("IS_BUTTON_ACTIVE_CLF_PATH") or (MODELS_DIR / "active_button_clf.joblib")
    )

    MODE: str = _env("MODE", "steam")

    # --------- Detection (YOLO) ---------
    YOLO_IMGSZ: int = _env_int("YOLO_IMGSZ", default=832)
    YOLO_CONF: float = _env_float("YOLO_CONF", default=0.65)  # should be 0.7 in general
    YOLO_IOU: float = _env_float("YOLO_IOU", default=0.45)

    # --------- Logging ---------
    LOG_LEVEL: str = _env("LOG_LEVEL", "DEBUG" if DEBUG else "INFO")
    FAST_MODE = True
    USE_FAST_OCR = True
    USE_GPU = True
    HINT_IS_IMPORTANT = False
    MAX_FAILURE = 20  # integer, no pct

    STORE_FOR_TRAINING = True
    STORE_FOR_TRAINING_THRESHOLD = 0.71  # YOLO baseline to say is accurate will be 0.7

    ANDROID_WINDOW_TITLE = "23117RA68G"
    WINDOW_TITLE = "Umamusume"
    USE_EXTERNAL_PROCESSOR = False
    EXTERNAL_PROCESSOR_URL = "http://127.0.0.1:8001"

    REFERENCE_STATS = {
        "SPD": 1150,
        "STA": 900,
        "PWR": 700,
        "GUTS": 300,
        "WIT": 400,
    }

    MINIMUM_SKILL_PTS = 700
    # Skills optimization (interval/delta gates)
    SKILL_CHECK_INTERVAL: int = 3  # only check skills every N turns (1 = every turn)
    SKILL_PTS_DELTA: int = (
        60  # open Skills if points increased by at least this much since last check
    )
    ACCEPT_CONSECUTIVE_RACE = True
    TRY_AGAIN_ON_FAILED_GOAL = True
    AUTO_REST_MINIMUM = 20

    PRIORITY_STATS = ["SPD", "STA", "WIT", "PWR", "GUTS"]

    MINIMAL_MOOD = "normal"

    # Keep the last applied config so other modules can extract runtime preset safely
    _last_config: dict | None = None

    @classmethod
    def resolve_window_title(cls, mode: str) -> str:
        if mode == "steam":
            return "Umamusume"
        elif mode == "bluestack":
            return "BlueStacks App Player"
        else:  # scrcpy
            return cls.ANDROID_WINDOW_TITLE

    @classmethod
    def apply_config(cls, cfg: dict) -> None:
        """
        Apply values coming from the web UI config.json into process Settings.
        Only the keys we care about on the Python side are mapped here.
        """
        # Persist a copy for later retrieval (e.g., training policy runtime extraction)
        try:
            cls._last_config = dict(cfg or {})
        except Exception:
            cls._last_config = None

        g = (cfg or {}).get("general", {}) or {}
        adv = g.get("advanced", {}) or {}

        # General
        cls.MODE = g.get("mode", cls.MODE)
        # One windowTitle for both Steam and scrcpy (Steam still uses it)
        wt = g.get("windowTitle")
        if wt:
            cls.WINDOW_TITLE = wt
            cls.ANDROID_WINDOW_TITLE = wt
        cls.FAST_MODE = bool(g.get("fastMode", cls.FAST_MODE))
        cls.TRY_AGAIN_ON_FAILED_GOAL = bool(
            g.get("tryAgainOnFailedGoal", cls.TRY_AGAIN_ON_FAILED_GOAL)
        )
        cls.HINT_IS_IMPORTANT = bool(g.get("prioritizeHint", cls.HINT_IS_IMPORTANT))
        cls.MAX_FAILURE = int(g.get("maxFailure", cls.MAX_FAILURE))
        cls.MINIMUM_SKILL_PTS = int(g.get("skillPtsCheck", cls.MINIMUM_SKILL_PTS))
        cls.ACCEPT_CONSECUTIVE_RACE = bool(
            g.get("acceptConsecutiveRace", cls.ACCEPT_CONSECUTIVE_RACE)
        )

        presets = (cfg or {}).get("presets") or []
        active_id = (cfg or {}).get("activePresetId")
        preset = next((p for p in presets if p.get("id") == active_id), None) or (
            presets[0] if presets else None
        )

        cls.MINIMAL_MOOD = str(preset.get("minimalMood", cls.MINIMAL_MOOD))
        cls.REFERENCE_STATS = preset.get("targetStats", cls.REFERENCE_STATS)
        cls.PRIORITY_STATS = preset.get("priorityStats", cls.PRIORITY_STATS)
        # Prefer per-preset hint toggle; fallback to general for backward compatibility
        try:
            cls.HINT_IS_IMPORTANT = bool(
                preset.get(
                    "prioritizeHint", g.get("prioritizeHint", cls.HINT_IS_IMPORTANT)
                )
            )
        except Exception:
            cls.HINT_IS_IMPORTANT = bool(g.get("prioritizeHint", cls.HINT_IS_IMPORTANT))
        # Advanced
        hk = adv.get("hotkey")
        if hk:
            cls.HOTKEY = hk
        cls.DEBUG = bool(adv.get("debugMode", cls.DEBUG))
        cls.USE_EXTERNAL_PROCESSOR = bool(
            adv.get("useExternalProcessor", cls.USE_EXTERNAL_PROCESSOR)
        )
        url = adv.get("externalProcessorUrl")
        if url:
            cls.EXTERNAL_PROCESSOR_URL = url
        # Match UI/schema key: 'autoRestMinimum'
        cls.AUTO_REST_MINIMUM = int(adv.get("autoRestMinimum", cls.AUTO_REST_MINIMUM))
        # Update training configuration
        undertrain_threshold = float(
            adv.get("undertrainThreshold", cls.UNDERTRAIN_THRESHOLD)
        )
        cls.UNDERTRAIN_THRESHOLD = max(
            1.0, min(20.0, undertrain_threshold)
        )  # Clamp between 1% and 20%

        # Update top stats focus setting
        top_stats_focus = int(adv.get("topStatsFocus", cls.TOP_STATS_FOCUS))
        cls.TOP_STATS_FOCUS = max(1, min(5, top_stats_focus))  # Clamp between 1 and 5

        # Skills optimization gates
        try:
            interval = int(adv.get("skillCheckInterval", cls.SKILL_CHECK_INTERVAL))
        except Exception:
            interval = cls.SKILL_CHECK_INTERVAL
        cls.SKILL_CHECK_INTERVAL = max(1, min(12, interval))  # 1..12 half-months

        try:
            delta = int(adv.get("skillPtsDelta", cls.SKILL_PTS_DELTA))
        except Exception:
            delta = cls.SKILL_PTS_DELTA
        cls.SKILL_PTS_DELTA = max(0, min(2000, delta))

    @classmethod
    def extract_runtime_preset(cls, cfg: dict) -> dict:
        """
        Pick the active preset (or first), and return a slim dict with things
        the Python runtime cares about: plan_races, select_style, skill_list, and other settings.
        """
        presets = (cfg or {}).get("presets") or []
        active_id = (cfg or {}).get("activePresetId")
        preset = next((p for p in presets if p.get("id") == active_id), None) or (
            presets[0] if presets else None
        )
        if not preset:
            return {
                "plan_races": {},
                "skill_list": [],
                "select_style": None,
                "raceIfNoGoodValue": cls.RACE_IF_NO_GOOD_VALUE,
            }

        plan_races = preset.get("plannedRaces", {}) or {}
        # skillsToBuy may be array of names or objects with {name}
        raw_skills = preset.get("skillsToBuy", []) or []
        skill_list = [s["name"] if isinstance(s, dict) else s for s in raw_skills]
        select_style = (
            preset.get("selectStyle") or preset.get("juniorStyle") or None
        )  # 'end'|'late'|'pace'|'front'|null

        # Get the race if no good value setting from preset or use the global default
        race_if_no_good_value = preset.get(
            "raceIfNoGoodValue", cls.RACE_IF_NO_GOOD_VALUE
        )

        return {
            "plan_races": plan_races,
            "skill_list": skill_list,
            "select_style": select_style,
            "raceIfNoGoodValue": race_if_no_good_value,
        }


class Constants:
    map_tile_idx_to_type = {0: "SPD", 1: "STA", 2: "PWR", 3: "GUTS", 4: "WIT"}
