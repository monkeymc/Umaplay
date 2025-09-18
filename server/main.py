from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException, Request
import os

from server.utils import load_dataset_json
from server.utils import load_config, save_config, run_cmd, repo_root
from server.updater import latest_info
from core.version import __version__

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

PATH = "web/dist"


# -----------------------------
# Datasets API
# -----------------------------
@app.get("/api/skills")
def api_skills():
  """
  Returns: list[ { name: str, description?: str } ]
  Source: datasets/in_game/skills.json
  """
  data = load_dataset_json("skills.json")
  if data is None:
    return []  # frontend handles empty gracefully
  # Ensure consistent shape
  if isinstance(data, list):
    return data
  return []

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


@app.get("/")
async def root_index():
  return FileResponse(os.path.join(PATH, "index.html"), headers={
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0"
  })

@app.get("/{path:path}")
async def fallback(path: str):
  file_path = os.path.join(PATH, path)
  headers = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0"
  }

  if os.path.isfile(file_path):
    media_type = "application/javascript" if file_path.endswith((".js", ".mjs")) else None
    return FileResponse(file_path, media_type=media_type, headers=headers)

  return FileResponse(os.path.join(PATH, "index.html"), headers=headers)


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
    raise HTTPException(status_code=400, detail="Working tree is not clean. Commit or stash changes first.")

  # Ensure we are on main
  code, out, err = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root)
  if code != 0:
    raise HTTPException(status_code=500, detail=f"git rev-parse failed: {err or out}")
  branch = (out or "").strip()
  if branch != "main":
    raise HTTPException(status_code=400, detail=f"Updates allowed only on 'main' (current: '{branch}')")

  # Fetch & fast-forward pull
  steps = []
  for args in (["git", "fetch", "--all", "--prune"], ["git", "pull", "--ff-only"]):
    code, out, err = run_cmd(args, cwd=root, timeout=120)
    steps.append({"cmd": " ".join(args), "code": code, "stdout": out, "stderr": err})
    if code != 0:
      raise HTTPException(status_code=500, detail={"message": "Update failed", "steps": steps})

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