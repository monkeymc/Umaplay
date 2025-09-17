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
    HOTKEY = "F2"
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
    DEBUG_DIR: Path = Path(_env("DEBUG_DIR") or (ROOT_DIR / "debug"))

    # Models & weights
    YOLO_WEIGHTS: Path = Path(
        _env("YOLO_WEIGHTS") or (MODELS_DIR / "uma.pt")
    )
    IS_BUTTON_ACTIVE_CLF_PATH: Path = Path(
        _env("IS_BUTTON_ACTIVE_CLF_PATH") or (MODELS_DIR / "active_button_clf.joblib")
    )

    MODE: str = _env("MODE", "steam")

    # --------- Detection (YOLO) ---------
    YOLO_IMGSZ: int = _env_int("YOLO_IMGSZ", default=832)
    YOLO_CONF: float = _env_float("YOLO_CONF", default=0.6)  # should be 0.7 in general
    YOLO_IOU: float = _env_float("YOLO_IOU", default=0.45)

    # --------- Logging ---------
    LOG_LEVEL: str = _env("LOG_LEVEL", "DEBUG" if DEBUG else "INFO")
    FAST_MODE = True
    USE_FAST_OCR = True
    USE_GPU = True
    TRY_AGAIN_ON_FAILED_GOAL = True
    HINT_IS_IMPORTANT = False
    MAX_FAILURE = 20  # integer, no pct

    STORE_FOR_TRAINING = True
    STORE_FOR_TRAINING_THRESHOLD = 0.71  # YOLO baseline to say is accurate will be 0.7

    ANDROID_WINDOW_TITLE = "23117RA68G"

class Constants:
    map_tile_idx_to_type = {
        0: "SPD",
        1: "STA",
        2: "PWR",
        3: "GUTS",
        4: "WIT"
    }