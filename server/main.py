from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException, Request
from fastapi.staticfiles import StaticFiles
import os
from typing import Any, Dict
from server.utils import (
    load_dataset_json,
    load_config,
    save_config,
    run_cmd,
    repo_root,
    load_nav_prefs,
    save_nav_prefs,
    ensure_nav_exists,
    load_event_setup_defaults,
)
from server.updater import latest_info
from core.version import __version__

ensure_nav_exists()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/config")
def get_config():
    return load_config()


@app.post("/config")
def update_config(new_config: dict):
    save_config(new_config)
    return {"status": "success", "data": new_config}


@app.get("/nav")
def get_nav():
    return load_nav_prefs()


@app.post("/nav")
def update_nav(new_nav: Dict[str, Any]):
    data = new_nav or {}
    save_nav_prefs(data)
    return {"status": "success", "data": load_nav_prefs()}


PATH = "web/dist"
BUILD_DIR = Path(__file__).resolve().parent.parent / "web" / "dist"

# -----------------------------------------------------------------------------
# Static mounts (production build)
# - Vite copies everything in web/public → web/dist (preserving folders).
# - Our images live under /events/... at runtime, so serve that folder directly.
# -----------------------------------------------------------------------------
events_dir = BUILD_DIR / "events"
icons_dir = BUILD_DIR / "icons"
badges_dir = BUILD_DIR / "badges"
mood_dir = BUILD_DIR / "mood"
race_dir = BUILD_DIR / "race"

if events_dir.exists():
    app.mount("/events", StaticFiles(directory=str(events_dir)), name="events")
if icons_dir.exists():
    app.mount("/icons", StaticFiles(directory=str(icons_dir)), name="icons")
if badges_dir.exists():
    app.mount("/badges", StaticFiles(directory=str(badges_dir)), name="badges")
if mood_dir.exists():
    app.mount("/mood", StaticFiles(directory=str(mood_dir)), name="mood")
if race_dir.exists():
    app.mount("/race", StaticFiles(directory=str(race_dir)), name="race")


# -----------------------------
# Datasets API
# -----------------------------
@app.get("/api/skills")
def api_skills():
    """Return skills enriched with derived category, filtering out unreleased/obsolete."""
    data = load_dataset_json("skills.json")
    if not isinstance(data, list):
        return []

    icons_dir = repo_root() / "web" / "public" / "icons" / "skills"
    try:
        available_icons = {
            entry.name for entry in icons_dir.iterdir() if entry.is_file()
        }
    except FileNotFoundError:
        available_icons = set()

    def derive_category(icon_filename: str | None) -> str:
        if not icon_filename:
            return "unknown"
        base = icon_filename.rsplit("/", 1)[-1]
        if base.endswith(".png"):
            base = base[:-4]
        parts = base.split("_")
        if len(parts) >= 4:
            cat_id = parts[3]
            # Normalize category by removing rarity suffix (last digit for 4+ digit IDs)
            # e.g., 10011/10012/10013 -> 1001, 20041/20042 -> 2004
            if len(cat_id) >= 4 and cat_id.isdigit():
                return cat_id[:-1]
            return cat_id
        if len(parts) >= 3:
            return parts[2]
        return "unknown"

    enriched = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        # Skip skills without icon (not in game yet)
        icon_filename = entry.get("icon_filename")
        if not icon_filename or not isinstance(icon_filename, str):
            continue
        if icon_filename.lower() == "utx_ico_skill_9999.png":
            continue
        if icon_filename not in available_icons:
            continue
        # Skip obsolete skills
        name = entry.get("name", "")
        if "obsolete" in name.lower():
            continue
        enriched.append(
            {
                **entry,
                "category": derive_category(icon_filename),
            }
        )
    return enriched


@app.get("/api/races")
def api_races():
    """
    Returns: dict[str, list[RaceInstance]]
    Source: datasets/in_game/races.json
    """
    data = load_dataset_json("races.json")
    if data is None:
        return {}
    if isinstance(data, dict):
        return data
    return {}


@app.get("/api/events")
def api_events():
    """
    Returns: list[RawEventSet]
    Source: datasets/in_game/events.json
    """
    data = load_dataset_json("events.json")
    if data is None:
        return []
    if isinstance(data, list):
        return data
    return []


# -----------------------------
# Event setup per preset (focused endpoints)
# -----------------------------
def _find_preset_in_config(cfg: dict, preset_id: str) -> tuple[dict | None, str | None]:
    """
    Search for preset by ID across all scenario branches.
    Returns (preset_dict, scenario_key) or (None, None) if not found.
    """
    scenarios = cfg.get("scenarios") or {}
    for scenario_key, branch in scenarios.items():
        if not isinstance(branch, dict):
            continue
        presets = branch.get("presets") or []
        for p in presets:
            if p.get("id") == preset_id:
                return p, scenario_key
    # Fallback: check legacy top-level presets (shouldn't exist after migration but be safe)
    legacy_presets = cfg.get("presets") or []
    for p in legacy_presets:
        if p.get("id") == preset_id:
            return p, None
    return None, None

@app.get("/api/presets/{preset_id}/event_setup")
def get_preset_event_setup(preset_id: str) -> Dict[str, Any]:
    """
    Return the event_setup object stored in the given preset.
    If not present, return schema-backed defaults.
    """
    cfg = load_config() or {}
    preset, _ = _find_preset_in_config(cfg, preset_id)
    if preset:
        setup = preset.get("event_setup")
        return load_event_setup_defaults(setup)
    raise HTTPException(status_code=404, detail="Preset not found")


@app.post("/api/presets/{preset_id}/event_setup")
def put_preset_event_setup(preset_id: str, payload: Dict[str, Any]):
    """
    Upsert the `event_setup` object inside a matching preset,
    normalizing via schema defaults without touching the rest of the config.
    """
    cfg = load_config() or {}
    preset, _ = _find_preset_in_config(cfg, preset_id)
    if preset:
        normalized = load_event_setup_defaults(payload)
        preset["event_setup"] = normalized
        save_config(cfg)
        return {"status": "ok", "preset_id": preset_id}
    raise HTTPException(status_code=404, detail="Preset not found")


@app.get("/")
async def root_index():
    return FileResponse(
        os.path.join(PATH, "index.html"),
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


# ----------------------------
# Admin: Update from GitHub
# ----------------------------
@app.post("/admin/update")
async def update_from_github(request: Request):
    # Safety: allow only local calls
    client = request.client.host if request.client else ""
    if client not in ("127.0.0.1", "localhost", "::1"):
        raise HTTPException(status_code=403, detail="Local requests only")

    root = repo_root()
    if not (root / ".git").exists():
        raise HTTPException(status_code=400, detail="Not a git repository")

    # Ensure clean working tree
    code, out, err = run_cmd(["git", "status", "--porcelain"], cwd=root)
    if code != 0:
        raise HTTPException(status_code=500, detail=f"git status failed: {err or out}")
    if out.strip():
        raise HTTPException(
            status_code=400,
            detail="Working tree is not clean. Commit or stash changes first.",
        )

    # Ensure we are on main
    code, out, err = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root)
    if code != 0:
        raise HTTPException(
            status_code=500, detail=f"git rev-parse failed: {err or out}"
        )
    branch = (out or "").strip()
    if branch != "main":
        raise HTTPException(
            status_code=400,
            detail=f"Updates allowed only on 'main' (current: '{branch}')",
        )

    # Fetch & fast-forward pull
    steps = []
    for args in (["git", "fetch", "--all", "--prune"], ["git", "pull", "--ff-only"]):
        code, out, err = run_cmd(args, cwd=root, timeout=120)
        steps.append(
            {"cmd": " ".join(args), "code": code, "stdout": out, "stderr": err}
        )
        if code != 0:
            raise HTTPException(
                status_code=500, detail={"message": "Update failed", "steps": steps}
            )

    return {"status": "ok", "branch": branch, "steps": steps}


# ----------------------------
# Admin: Force update (HARD RESET)
# ----------------------------
@app.post("/admin/force_update")
async def force_update(request: Request):
    # Safety: allow only local calls
    client = request.client.host if request.client else ""
    if client not in ("127.0.0.1", "localhost", "::1"):
        raise HTTPException(status_code=403, detail="Local requests only")

    root = repo_root()
    if not (root / ".git").exists():
        raise HTTPException(status_code=400, detail="Not a git repository")

    # Determine current branch
    code, out, err = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root)
    if code != 0:
        raise HTTPException(
            status_code=500, detail=f"git rev-parse failed: {err or out}"
        )
    branch = (out or "").strip()

    steps = []
    sequence = [
        ["git", "fetch", "--all", "--prune"],
        ["git", "reset", "--hard", f"origin/{branch}"],
        ["git", "clean", "-fd"],
        ["git", "pull"],
    ]
    for args in sequence:
        code, out, err = run_cmd(args, cwd=root, timeout=120)
        steps.append(
            {"cmd": " ".join(args), "code": code, "stdout": out, "stderr": err}
        )
        if code != 0:
            raise HTTPException(
                status_code=500,
                detail={"message": "Force update failed", "steps": steps},
            )

    return {"status": "ok", "branch": branch, "steps": steps}


# ----------------------------
# Version & update info
# ----------------------------
@app.get("/admin/version")
def get_version():
    return {"version": __version__}


@app.get("/admin/check_update")
def check_update():
    return latest_info()


@app.get("/{path:path}")
async def fallback(path: str):
    file_path = os.path.join(PATH, path)
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }

    if os.path.isfile(file_path):
        media_type = (
            "application/javascript" if file_path.endswith((".js", ".mjs")) else None
        )
        return FileResponse(file_path, media_type=media_type, headers=headers)

    return FileResponse(os.path.join(PATH, "index.html"), headers=headers)
