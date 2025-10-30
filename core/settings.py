from __future__ import annotations

import os
from pathlib import Path
import math
from typing import Any, Dict, List, Optional, Set, Tuple, Union


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


DEFAULT_SUPPORT_PRIORITY: Dict[str, Union[float, bool]] = {
    "enabled": True,
    "scoreBlueGreen": 0.75,
    "scoreOrangeMax": 0.5,
}


_DEFAULT_NAV_PREFS: Dict[str, Dict[str, Any]] = {
    "shop": {
        "alarm_clock": True,
        "star_pieces": False,
        "parfait": False,
    },
    "team_trials": {
        "preferred_banner": 2,
    },
}


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
    _YOLO_WEIGHTS_URA_ENV = _env("YOLO_WEIGHTS_URA") or _env("YOLO_WEIGHTS")
    YOLO_WEIGHTS_URA: Path = Path(_YOLO_WEIGHTS_URA_ENV or (MODELS_DIR / "uma_ura.pt"))
    YOLO_WEIGHTS_NAV: Path = Path(
        _env("YOLO_WEIGHTS_NAV") or (MODELS_DIR / "uma_nav.pt")
    )
    IS_BUTTON_ACTIVE_CLF_PATH: Path = Path(
        _env("IS_BUTTON_ACTIVE_CLF_PATH") or (MODELS_DIR / "active_button_clf.joblib")
    )

    MODE: str = _env("MODE", "steam") or "steam"

    # --------- Detection (YOLO) ---------
    YOLO_IMGSZ: int = _env_int("YOLO_IMGSZ", default=832)
    YOLO_CONF: float = _env_float("YOLO_CONF", default=0.60)  # should be 0.7 in general, but we are a little conservative here...
    YOLO_IOU: float = _env_float("YOLO_IOU", default=0.45)

    # --------- Logging ---------
    LOG_LEVEL: str = _env("LOG_LEVEL", "DEBUG" if DEBUG else "INFO") or (
        "DEBUG" if DEBUG else "INFO"
    )
    FAST_MODE = True
    USE_FAST_OCR = True
    USE_GPU = True
    HINT_IS_IMPORTANT = False
    MAX_FAILURE = 20  # integer, no pct

    STORE_FOR_TRAINING = True
    STORE_FOR_TRAINING_THRESHOLD = 0.71  # YOLO baseline to say is accurate will be 0.7

    ANDROID_WINDOW_TITLE = "23117RA68G"
    WINDOW_TITLE = "Umamusume"

    AGENT_NAME_URA: str = "ura"
    AGENT_NAME_NAV: str = "agent_nav"
    USE_EXTERNAL_PROCESSOR = False
    EXTERNAL_PROCESSOR_URL = "http://127.0.0.1:8001"
    TEMPLATE_MATCH_TIMEOUT: float = _env_float("TEMPLATE_MATCH_TIMEOUT", default=8.0)

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

    SUPPORT_PRIORITIES_HAVE_CUSTOMIZATION: bool = False
    SUPPORT_CUSTOM_PRIORITY_KEYS: Set[Tuple[str, str, str]] = set()
    SUPPORT_AVOID_ENERGY: Dict[Tuple[str, str, str], bool] = {}
    SHOW_PRESET_OVERLAY: bool = _env_bool("SHOW_PRESET_OVERLAY", True)
    PRESET_OVERLAY_DURATION: float = _env_float("PRESET_OVERLAY_DURATION", 5.0)
    NAV_PREFS: Dict[str, Dict[str, Any]] = {
        "shop": dict(_DEFAULT_NAV_PREFS["shop"]),
        "team_trials": dict(_DEFAULT_NAV_PREFS["team_trials"]),
    }

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

        preset_data = preset or {}

        deck, priorities, avoid_energy = cls._extract_support_priorities_from_preset(
            preset_data
        )
        cls.SUPPORT_DECK = deck
        cls.SUPPORT_CARD_PRIORITIES = priorities
        custom_keys = {
            key for key, p in priorities.items() if cls._priority_is_custom(p)
        }
        cls.SUPPORT_CUSTOM_PRIORITY_KEYS = custom_keys
        cls.SUPPORT_PRIORITIES_HAVE_CUSTOMIZATION = bool(custom_keys)
        cls.SUPPORT_AVOID_ENERGY = avoid_energy

        cls.MINIMAL_MOOD = str(preset_data.get("minimalMood", cls.MINIMAL_MOOD))
        cls.REFERENCE_STATS = preset_data.get("targetStats", cls.REFERENCE_STATS)
        cls.PRIORITY_STATS = preset_data.get("priorityStats", cls.PRIORITY_STATS)
        # Prefer per-preset hint toggle; fallback to general for backward compatibility
        try:
            cls.HINT_IS_IMPORTANT = bool(
                preset_data.get(
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
        if "showPresetOverlay" in adv:
            try:
                cls.SHOW_PRESET_OVERLAY = bool(adv.get("showPresetOverlay"))
            except Exception:
                pass
        if "presetOverlaySeconds" in adv:
            try:
                cls.PRESET_OVERLAY_DURATION = max(1.0, float(adv.get("presetOverlaySeconds")))
            except Exception:
                pass
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
    def apply_nav_preferences(cls, nav: Optional[dict]) -> None:
        nav = nav if isinstance(nav, dict) else {}
        shop = nav.get("shop") if isinstance(nav, dict) else None
        team = nav.get("team_trials") if isinstance(nav, dict) else None

        if not isinstance(shop, dict):
            shop = dict(_DEFAULT_NAV_PREFS["shop"])
        if not isinstance(team, dict):
            team = dict(_DEFAULT_NAV_PREFS["team_trials"])

        normalized_shop = {
            "alarm_clock": bool(shop.get("alarm_clock", True)),
            "star_pieces": bool(shop.get("star_pieces", False)),
            "parfait": bool(shop.get("parfait", False)),
        }

        try:
            preferred_banner = int(team.get("preferred_banner", 2))
        except Exception:
            preferred_banner = 2
        preferred_banner = max(1, min(3, preferred_banner))

        cls.NAV_PREFS = {
            "shop": normalized_shop,
            "team_trials": {"preferred_banner": preferred_banner},
        }

    @classmethod
    def get_active_preset_snapshot(cls) -> tuple[Optional[str], Optional[dict], dict]:
        cfg = cls._last_config or {}
        presets = (cfg.get("presets") or [])
        active_id = cfg.get("activePresetId")
        preset = next((p for p in presets if p.get("id") == active_id), None)
        if not preset and presets:
            preset = presets[0]
            active_id = preset.get("id")
        return active_id, preset, cfg

    @classmethod
    def get_shop_nav_prefs(cls) -> Dict[str, bool]:
        prefs = cls.NAV_PREFS.get("shop") or {}
        return {
            "alarm_clock": bool(prefs.get("alarm_clock", True)),
            "star_pieces": bool(prefs.get("star_pieces", False)),
            "parfait": bool(prefs.get("parfait", False)),
        }

    @classmethod
    def get_team_trials_banner_pref(cls) -> int:
        team = cls.NAV_PREFS.get("team_trials") or {}
        try:
            preferred = int(
                team.get(
                    "preferred_banner",
                    _DEFAULT_NAV_PREFS["team_trials"]["preferred_banner"],
                )
            )
        except Exception:
            preferred = _DEFAULT_NAV_PREFS["team_trials"]["preferred_banner"]
        return max(1, min(3, preferred))

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

        deck, priorities, avoid_energy = cls._extract_support_priorities_from_preset(
            preset
        )

        return {
            "plan_races": plan_races,
            "skill_list": skill_list,
            "select_style": select_style,
            "raceIfNoGoodValue": race_if_no_good_value,
            "support_deck": deck,
            "support_card_priorities": [
                {
                    "name": name,
                    "rarity": rarity,
                    "attribute": attribute,
                    "enabled": data["enabled"],
                    "scoreBlueGreen": data["scoreBlueGreen"],
                    "scoreOrangeMax": data["scoreOrangeMax"],
                }
                for (name, rarity, attribute), data in priorities.items()
            ],
            "support_avoid_energy": [
                {
                    "name": name,
                    "rarity": rarity,
                    "attribute": attribute,
                    "avoidEnergyOverflow": avoid_energy.get(
                        (name, rarity, attribute), True
                    ),
                }
                for (name, rarity, attribute) in avoid_energy.keys()
            ],
        }


    @staticmethod
    def _clamp(value: float, min_value: float, max_value: float) -> float:
        try:
            val = float(value)
        except (TypeError, ValueError):
            return min_value
        return max(min_value, min(max_value, val))

    @classmethod
    def default_support_priority(cls) -> Dict[str, Union[float, bool]]:
        base = DEFAULT_SUPPORT_PRIORITY
        return {
            "enabled": bool(base.get("enabled", True)),
            "scoreBlueGreen": float(base.get("scoreBlueGreen", 0.75)),
            "scoreOrangeMax": float(base.get("scoreOrangeMax", 0.5)),
        }

    @classmethod
    def _normalize_priority(cls, raw: Optional[dict]) -> Dict[str, Union[float, bool]]:
        if not raw or not isinstance(raw, dict):
            return cls.default_support_priority()
        enabled = bool(raw.get("enabled", True))
        score_bg = cls._clamp(raw.get("scoreBlueGreen", 0.75), 0.0, 10.0)
        score_om = cls._clamp(raw.get("scoreOrangeMax", 0.5), 0.0, 10.0)
        return {
            "enabled": enabled,
            "scoreBlueGreen": score_bg,
            "scoreOrangeMax": score_om,
        }

    @classmethod
    def _priority_is_custom(cls, priority: Dict[str, Union[float, bool]]) -> bool:
        if not isinstance(priority, dict):
            return False
        default = cls.default_support_priority()

        if bool(priority.get("enabled", True)) != bool(default.get("enabled", True)):
            return True

        default_bg = float(default.get("scoreBlueGreen", 0.75))
        default_om = float(default.get("scoreOrangeMax", 0.5))
        score_bg = float(priority.get("scoreBlueGreen", default_bg))
        score_om = float(priority.get("scoreOrangeMax", default_om))

        if not math.isclose(score_bg, default_bg, rel_tol=1e-6, abs_tol=1e-6):
            return True
        if not math.isclose(score_om, default_om, rel_tol=1e-6, abs_tol=1e-6):
            return True
        return False

    @classmethod
    def _extract_support_priorities_from_preset(
        cls, preset: Optional[dict]
    ) -> Tuple[
        List[dict],
        Dict[Tuple[str, str, str], Dict[str, Union[float, bool]]],
        Dict[Tuple[str, str, str], bool],
    ]:
        event_setup = (preset or {}).get("event_setup", {}) or {}
        supports = event_setup.get("supports", []) or []

        deck: List[dict] = []
        priorities: Dict[Tuple[str, str, str], Dict[str, Union[float, bool]]] = {}
        avoid_energy: Dict[Tuple[str, str, str], bool] = {}

        for entry in supports:
            if not entry:
                continue
            name = entry.get("name")
            rarity = entry.get("rarity")
            attribute = entry.get("attribute")
            slot = entry.get("slot")
            if not (name and rarity and attribute):
                continue

            try:
                slot_idx = int(slot) if slot is not None else len(deck)
            except (TypeError, ValueError):
                slot_idx = len(deck)

            raw_flag = entry.get("avoidEnergyOverflow")
            if raw_flag is None:
                raw_flag = entry.get("avoid_energy_overflow")
            avoid_flag = bool(raw_flag) if isinstance(raw_flag, bool) else True

            card_info = {
                "slot": slot_idx,
                "name": str(name),
                "rarity": str(rarity),
                "attribute": str(attribute),
                "avoidEnergyOverflow": avoid_flag,
            }
            deck.append(card_info)

            key = (card_info["name"], card_info["rarity"], card_info["attribute"])
            priorities[key] = cls._normalize_priority(entry.get("priority"))
            avoid_energy[key] = avoid_flag

        deck.sort(key=lambda c: c["slot"])
        return deck, priorities, avoid_energy

class Constants:
    map_tile_idx_to_type = {0: "SPD", 1: "STA", 2: "PWR", 3: "GUTS", 4: "WIT"}


    @classmethod
    def get_support_priority(
        cls, name: str, rarity: str, attribute: str
    ) -> Dict[str, Union[float, bool]]:
        key = (name, rarity, attribute)
        if key in Settings.SUPPORT_CARD_PRIORITIES:
            data = Settings.SUPPORT_CARD_PRIORITIES[key]
            return {
                "enabled": bool(data.get("enabled", True)),
                "scoreBlueGreen": float(data.get("scoreBlueGreen", 0.75)),
                "scoreOrangeMax": float(data.get("scoreOrangeMax", 0.5)),
            }
        return Settings.default_support_priority()
