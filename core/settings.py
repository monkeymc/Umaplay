"""
Central runtime configuration for the bot.

- Single source of truth: paths, thresholds, timings, feature flags.
- Small, explicit surface: class-level constants for easy import/use.
- Environment overrides supported via the UMABOT_* prefix (see notes below).

USAGE EXAMPLES
--------------
from core.settings import Settings

if Settings.MODE == "steam":
    ...

model = YOLO(Settings.YOLO_WEIGHTS)
left_img, res, dets = detect_objects_single(
    ctrl, imgsz=Settings.YOLO_IMGSZ, conf=Settings.YOLO_CONF, iou=Settings.YOLO_IOU
)

NOTES
-----
• No directories are created on import. Call `Settings.ensure_dirs()` in your launcher if desired.
• Environment overrides:
    UMABOT_MODE=steam
    UMABOT_YOLO_WEIGHTS=/abs/path/to/best.pt
    UMABOT_DEBUG_SAVE_OVERLAYS=true
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    """Return environment variable (UMABOT_* has priority), else default."""
    return os.getenv(f"UMABOT_{name}", os.getenv(name, default))


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
    Adjust values below or override via environment variables prefixed with UMABOT_.
    """
    HOTKEY = "F4"
    DEBUG = _env_bool("DEBUG", default=True)
    HOST = "127.0.0.1"
    PORT = 8000

    _ROOT_DIR = Path(__file__).resolve().parents[1]  # repo root (parent of /core)
    RACE_DATA_PATH = _ROOT_DIR / "datasets" / "in_game" / "races.json"

    # --------- Project roots & paths ---------
    CORE_DIR: Path = Path(__file__).resolve().parent
    ROOT_DIR: Path = CORE_DIR.parent

    # Common directories
    ASSETS_DIR: Path = Path(_env("ASSETS_DIR") or (ROOT_DIR / "assets"))
    MODELS_DIR: Path = Path(_env("MODELS_DIR") or (ROOT_DIR / "models"))
    DATA_DIR: Path = Path(_env("DATA_DIR") or (CORE_DIR / "data"))
    TEMP_DIR: Path = Path(_env("TEMP_DIR") or (ROOT_DIR / "temp"))
    LOGS_DIR: Path = Path(_env("LOGS_DIR") or (ROOT_DIR / "logs"))
    DEBUG_DIR: Path = Path(_env("DEBUG_DIR") or (ROOT_DIR / "debug"))

    # Assets
    ICONS_DIR: Path = Path(_env("ICONS_DIR") or (ASSETS_DIR / "icons"))

    # Models & weights
    YOLO_WEIGHTS: Path = Path(
        _env("YOLO_WEIGHTS") or (MODELS_DIR / "uma.pt")
    )
    IS_BUTTON_ACTIVE_CLF_PATH: Path = Path(
        _env("IS_BUTTON_ACTIVE_CLF_PATH") or (MODELS_DIR / "active_button_clf.joblib")
    )

    # --------- Modes & feature flags ---------
    # Primary runtime mode (currently "steam"; future-proof for others like "android")
    MODE: str = _env("MODE", "steam")

    # Use trained infirmary classifier if the file exists (can be hard-disabled via env)
    USE_INFIRMARY_CLF: bool = _env_bool(
        "USE_INFIRMARY_CLF",
        default=IS_BUTTON_ACTIVE_CLF_PATH.exists(),
    )

    # --------- Detection (YOLO) ---------
    YOLO_IMGSZ: int = _env_int("YOLO_IMGSZ", default=832)
    YOLO_CONF: float = _env_float("YOLO_CONF", default=0.6)  # should be 0.7 in general
    YOLO_IOU: float = _env_float("YOLO_IOU", default=0.45)

    # --------- Screen classification thresholds ---------
    LOBBY_CONF_MIN: float = _env_float("LOBBY_CONF_MIN", default=0.80)
    REQUIRE_INFIRMARY_FOR_LOBBY: bool = _env_bool("REQUIRE_INFIRMARY_FOR_LOBBY", default=True)
    TRAINING_BTN_CONF_MIN: float = _env_float("TRAINING_BTN_CONF_MIN", default=0.50)

    # --------- Controller timings ---------
    CLICK_MOVE_DURATION_SEC: float = _env_float("CLICK_MOVE_DURATION_SEC", default=0.15)
    PAUSE_AFTER_CLICK_SEC: float = _env_float("PAUSE_AFTER_CLICK_SEC", default=0.18)
    RECAPTURE_DELAY_SEC: float = _env_float("RECAPTURE_DELAY_SEC", default=0.15)

    # --------- OCR (minimal engine) ---------
    OCR_LANG: str = _env("OCR_LANG", "en")
    OCR_DEBUG_OVERLAY_NAME: str = _env("OCR_DEBUG_OVERLAY_NAME", "dbg_ocr_overlay.png")

    # Upscale factor for tiny UI text when debugging (used by helpers/tests; not passed to Paddle directly)
    OCR_DEBUG_UPSCALE: float = _env_float("OCR_DEBUG_UPSCALE", default=2.0)

    # --------- Analyzer defaults ---------
    # Friendship bar analyzer
    FBA_ROI_HEIGHT_FRAC: float = _env_float("FBA_ROI_HEIGHT_FRAC", default=0.18)
    FBA_H_TOLERANCE: int = _env_int("FBA_H_TOLERANCE", default=12)
    FBA_VOTE_MARGIN: float = _env_float("FBA_VOTE_MARGIN", default=0.03)

    # Hint detector (strict & wide HSV gates, ROI fraction of tile)
    HINT_ROI_X_LO: float = _env_float("HINT_ROI_X_LO", default=0.60)
    HINT_ROI_X_HI: float = _env_float("HINT_ROI_X_HI", default=1.00)
    HINT_ROI_Y_LO: float = _env_float("HINT_ROI_Y_LO", default=0.00)
    HINT_ROI_Y_HI: float = _env_float("HINT_ROI_Y_HI", default=0.40)
    HINT_H_TOL_STRICT: int = _env_int("HINT_H_TOL_STRICT", default=8)
    HINT_H_TOL_WIDE: int = _env_int("HINT_H_TOL_WIDE", default=16)
    HINT_S_MIN_STRICT: int = _env_int("HINT_S_MIN_STRICT", default=140)
    HINT_V_MIN_STRICT: int = _env_int("HINT_V_MIN_STRICT", default=140)
    HINT_S_MIN_WIDE: int = _env_int("HINT_S_MIN_WIDE", default=100)
    HINT_V_MIN_WIDE: int = _env_int("HINT_V_MIN_WIDE", default=110)
    HINT_MIN_COVERAGE_FRAC: float = _env_float("HINT_MIN_COVERAGE_FRAC", default=0.25)
    HINT_MIN_PURITY: float = _env_float("HINT_MIN_PURITY", default=0.60)

    # --------- Logging ---------
    LOG_LEVEL: str = _env("LOG_LEVEL", "DEBUG" if DEBUG else "INFO")
    GREEDY_MODE = True
    USE_FAST_OCR = True
    USE_GPU = True
    TRY_AGAIN_ON_FAILED_GOAL = True
    HINT_IS_IMPORTANT = True

    MAX_FAILURE = 20  # integer, no pct
    # --------- Helpers ---------

    STORE_FOR_TRAINING = True
    STORE_FOR_TRAINING_THRESHOLD = 0.71  # YOLO baseline to say is accurate will be 0.7

    @classmethod
    def ensure_dirs(cls) -> None:
        """Create commonly used output directories if they don't exist."""
        for p in (cls.TEMP_DIR, cls.LOGS_DIR, cls.DEBUG_DIR):
            try:
                p.mkdir(parents=True, exist_ok=True)
            except Exception:
                # Avoid raising during import; let the caller handle filesystem permissions.
                pass


class Constants:
    map_tile_idx_to_type = {
        0: "SPD",
        1: "STA",
        2: "PWR",
        3: "GUTS",
        4: "WIT"
    }