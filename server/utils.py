import json
from pathlib import Path
import subprocess
from typing import Tuple

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"
SAMPLE_CONFIG_PATH = CONFIG_PATH.with_name("config.sample.json")

def load_config() -> dict:
  if CONFIG_PATH.exists():
    with open(CONFIG_PATH, "r") as f:
      return json.load(f)
  return {}

def save_config(data: dict):
  with open(CONFIG_PATH, "w") as f:
    json.dump(data, f, indent=2)

# -----------------------------
# Datasets helpers (skills/races)
# -----------------------------
_DATASET_CACHE: dict[str, tuple[float, object]] = {}

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

def run_cmd(args: list[str], cwd: Path, timeout: int = 30) -> Tuple[int, str, str]:
  """Run a command and return (code, stdout, stderr)."""
  proc = subprocess.Popen(args, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
  try:
    out, err = proc.communicate(timeout=timeout)
  except subprocess.TimeoutExpired:
    proc.kill()
    out, err = proc.communicate()
  return proc.returncode, out, err

def repo_root() -> Path:
  # repo root is parent of /core (same logic as Settings.ROOT_DIR)
  return Path(__file__).resolve().parent.parent