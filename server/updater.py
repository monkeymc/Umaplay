from __future__ import annotations
import json
import urllib.request
from packaging.version import Version, InvalidVersion
from core.version import __version__, __repo_owner__, __repo_name__

GH_LATEST = f"https://api.github.com/repos/{__repo_owner__}/{__repo_name__}/releases/latest"

def fetch_latest_release() -> dict:
    req = urllib.request.Request(GH_LATEST, headers={"User-Agent": "Umaplay-Updater"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))

def compare_versions(current: str, latest_tag: str) -> int:
    try:
        c, l = Version(current.lstrip("v")), Version(latest_tag.lstrip("v"))
        if c < l: return -1
        if c > l: return 1
        return 0
    except InvalidVersion:
        # fallback: string compare
        return -1 if current != latest_tag else 0

def latest_info() -> dict:
    try:
        rel = fetch_latest_release()
        tag = rel.get("tag_name") or rel.get("name") or ""
        cmp = compare_versions(__version__, tag)
        assets = rel.get("assets", [])
        # Optional: find a Windows zip asset by name
        win_asset = next((a for a in assets if a.get("name","").lower().endswith(".zip")), None)
        return {
            "ok": True,
            "current": __version__,
            "latest": tag,
            "is_update_available": (cmp == -1),
            "html_url": rel.get("html_url"),
            "asset": {
                "name": (win_asset or {}).get("name"),
                "browser_download_url": (win_asset or {}).get("browser_download_url"),
                "size": (win_asset or {}).get("size"),
            } if win_asset else None,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "current": __version__}
