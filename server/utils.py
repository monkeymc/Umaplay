import json
from pathlib import Path
import subprocess
from typing import Any, Dict, Tuple, List, Optional

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

PREFS_DIR = Path(__file__).resolve().parent.parent / "prefs"
CONFIG_PATH = PREFS_DIR / "config.json"
SAMPLE_CONFIG_PATH = PREFS_DIR / "config.sample.json"
NAV_PATH = PREFS_DIR / "nav.json"
SAMPLE_NAV_PATH = PREFS_DIR / "nav.sample.json"

_DATASET_CACHE: Dict[str, Tuple[float, object]] = {}


def _repo_root() -> Path:
    # server/utils.py -> server/ -> repo root is parent
    return Path(__file__).resolve().parent.parent


def _dataset_path(*parts: str) -> Path:
    return _repo_root() / "datasets" / "in_game" / Path(*parts)


def load_dataset_json(*rel_parts: str):
    """
    Load a dataset JSON with simple mtime-based caching.
    Example: load_dataset_json("skills.json")
             load_dataset_json("races.json")
    """
    path = _dataset_path(*rel_parts)
    key = str(path)
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return None

    cached = _DATASET_CACHE.get(key)
    if cached and cached[0] == mtime:
        return cached[1]

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    _DATASET_CACHE[key] = (mtime, data)
    return data

def _normalize_reward_priority(raw: Any, fallback: Optional[List[str]] = None) -> List[str]:
    allowed = ["skill_pts", "stats", "hints"]
    aliases = {
        "skill_points": "skill_pts",
        "skillpts": "skill_pts",
        "hint": "hints",
        "stat": "stats",
    }
    seen: List[str] = []
    if isinstance(raw, (list, tuple)):
        for item in raw:
            if not isinstance(item, str):
                continue
            key = item.strip().lower()
            if not key:
                continue
            mapped = aliases.get(key, key)
            if mapped in allowed and mapped not in seen:
                seen.append(mapped)
    baseline = fallback if fallback else allowed
    for fb in baseline:
        if fb not in seen and fb in allowed:
            seen.append(fb)
    return seen[: len(allowed)]

def _ensure_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return default

def _normalize_support(entry: Any, slot: int, fallback_priority: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    if not isinstance(entry, dict):
        return None
    name = entry.get("name")
    rarity = entry.get("rarity")
    attribute = entry.get("attribute")
    if not (isinstance(name, str) and isinstance(rarity, str) and isinstance(attribute, str)):
        return None
    result = {
        "slot": slot,
        "name": name,
        "rarity": rarity,
        "attribute": attribute,
    }
    if "priority" in entry and isinstance(entry["priority"], dict):
        result["priority"] = entry["priority"]
    reward_priority = _normalize_reward_priority(
        entry.get("rewardPriority", entry.get("reward_priority")),
        fallback_priority,
    )
    result["rewardPriority"] = reward_priority
    result["avoidEnergyOverflow"] = _ensure_bool(
        entry.get("avoidEnergyOverflow", entry.get("avoid_energy_overflow")), True
    )
    return result

def _normalize_entity(entry: Any, fallback_priority: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    if not isinstance(entry, dict):
        return None
    name = entry.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    return {
        "name": name,
        "avoidEnergyOverflow": _ensure_bool(
            entry.get("avoidEnergyOverflow", entry.get("avoid_energy_overflow")), True
        ),
        "rewardPriority": _normalize_reward_priority(
            entry.get("rewardPriority", entry.get("reward_priority")),
            fallback_priority,
        ),
    }

def load_event_setup_defaults(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}

    prefs_raw = raw.get("prefs")
    prefs_in = prefs_raw if isinstance(prefs_raw, dict) else {}
    global_reward_priority = _normalize_reward_priority(
        prefs_in.get("rewardPriority", prefs_in.get("reward_priority"))
    )

    supports_out: List[Optional[Dict[str, Any]]] = []
    supports_raw = raw.get("supports")
    supports_in = supports_raw if isinstance(supports_raw, list) else []
    for idx in range(6):
        entry = supports_in[idx] if idx < len(supports_in) else None
        supports_out.append(_normalize_support(entry, idx, global_reward_priority))

    scenario_out = _normalize_entity(raw.get("scenario"), global_reward_priority)
    trainee_out = _normalize_entity(raw.get("trainee"), global_reward_priority)
    overrides_raw = prefs_in.get("overrides")
    overrides = overrides_raw if isinstance(overrides_raw, dict) else {}
    patterns_raw = prefs_in.get("patterns")
    if isinstance(patterns_raw, list):
        safe_patterns = [p for p in patterns_raw if isinstance(p, dict)]
    else:
        safe_patterns = []
    defaults_raw = prefs_in.get("defaults")
    defaults = defaults_raw if isinstance(defaults_raw, dict) else {}
    prefs_out = {
        "overrides": overrides,
        "patterns": safe_patterns,
        "defaults": {
            "support": int(defaults.get("support", 1) or 1),
            "trainee": int(defaults.get("trainee", 1) or 1),
            "scenario": int(defaults.get("scenario", 1) or 1),
        },
        "rewardPriority": global_reward_priority,
    }

    return {
        "supports": supports_out,
        "scenario": scenario_out,
        "trainee": trainee_out,
        "prefs": prefs_out,
    }


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    return {}


def save_config(data: dict):
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)


def load_nav_prefs() -> Dict[str, Dict[str, Any]]:
    ensure_nav_exists()
    try:
        with open(NAV_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
            if isinstance(raw, dict):
                return raw
    except Exception:
        pass
    return json.loads(json.dumps(_DEFAULT_NAV_PREFS))


def save_nav_prefs(data: Dict[str, Dict[str, Any]]):
    with open(NAV_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# -----------------------------
# Datasets helpers (skills/races)
# -----------------------------
def ensure_config_exists() -> bool:
    """
    Ensure config.json exists. If it doesn't, try to seed it with
    config.sample.json; otherwise write an empty JSON object.
    Returns True if we created it now, False if it already existed.
    """
    if CONFIG_PATH.exists():
        return False
    try:
        if SAMPLE_CONFIG_PATH.exists():
            with open(SAMPLE_CONFIG_PATH, "r") as sf:
                sample = json.load(sf)
            save_config(sample)
        else:
            save_config({})
        return True
    except Exception:
        # As a last resort, write {}
        try:
            save_config({})
            return True
        except Exception:
            return False


def ensure_nav_exists() -> bool:
    """Ensure nav.json exists; seed from sample or defaults when missing."""
    if NAV_PATH.exists():
        return False
    try:
        if SAMPLE_NAV_PATH.exists():
            with open(SAMPLE_NAV_PATH, "r", encoding="utf-8") as sf:
                sample = json.load(sf)
            save_nav_prefs(sample)
        else:
            save_nav_prefs(_DEFAULT_NAV_PREFS)
        return True
    except Exception:
        try:
            save_nav_prefs(_DEFAULT_NAV_PREFS)
            return True
        except Exception:
            return False


def run_cmd(args: list[str], cwd: Path, timeout: int = 30) -> Tuple[int, str, str]:
    """Run a command and return (code, stdout, stderr)."""
    proc = subprocess.Popen(
        args, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
    return proc.returncode, out, err


def repo_root() -> Path:
    # repo root is parent of /core (same logic as Settings.ROOT_DIR)
    return Path(__file__).resolve().parent.parent
