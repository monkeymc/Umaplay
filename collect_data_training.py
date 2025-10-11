#!/usr/bin/env python3
"""
Collect the worst-confidence images PER FOLDER for labeling.

It scans:   <SRC>/[folder]/raw/*.{png,jpg,jpeg,bmp,webp}
…parses a confidence score from each filename (robust trailing parse),
sorts ascending (worst→best), and selects the bottom <percentile>% per folder.

Selected files are copied (default), moved, or symlinked into:
    <DEST_BASE>/<SET_NAME>/<folder>/

Typical usage:
  python collect_data_training.py --set-name set_2025-10-11
  python collect_data_training.py --percentile 10 --exclude general agenda_screen --set-name set_oct11
  python collect_data_training.py --percentile 5 --action move --set-name set_low5 --dry-run
  python collect_data_training.py --set-name set_low5 --percentile 5 --min-per-folder 3 --action move
  python collect_data_training.py --set-name set_2025-10-11 --exclude general agenda* race_view_btn
Notes:
- Only scans subfolders named exactly 'raw' and ignores 'overlay'.
- Confidence is expected at the END of the filename stem, e.g.:
    foo_bar_0.66.png, menu-0.42.jpg, anything_conf=0.15.webp
  Robust rules:
    1) Prefer a trailing score in [0..1] (e.g., *_0.34, *-0.7, *_1, *-1.0).
    2) Else look for 'conf=' or 'score=' patterns.
    3) Else (optional) try last 0.x/1(.0) found in stem.
- Files without a parseable score are skipped by default; pass --treat-unscored as 0.0 to include them.

Author: you 💙
"""

from __future__ import annotations

import argparse
import fnmatch
import math
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

# Allowed image extensions (lowercase)
EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

# Regexes to extract confidence
# 1) Trailing _0.66 / -0.66 / _1 / -1.0  at end of STEM (before extension)
RE_TRAIL_01 = re.compile(r"[_-]((?:0(?:\.\d+)?|1(?:\.0+)?))$", re.IGNORECASE)

# 2) Named patterns: conf=0.42 / score:0.37 anywhere
RE_NAMED_01 = re.compile(r"(?:conf|score)\s*[:=]\s*((?:0(?:\.\d+)?|1(?:\.0+)?))", re.IGNORECASE)

# 3) Fallback: any 0.x / 1(.0) number in stem; use the LAST match
RE_ANY_01 = re.compile(r"(?<!\d)((?:0(?:\.\d+)?|1(?:\.0+)?))(?!\d)")

@dataclass
class Pick:
    path: Path
    conf: float


def parse_confidence_from_name(path: Path, *, allow_fallback: bool = True) -> Optional[float]:
    """
    Extract a confidence in [0..1] from filename robustly.
    Priority:
      (A) Trailing pattern  *_<0..1>  or  *-<0..1>
      (B) Named pattern:    conf=<0..1> | score=<0..1>
      (C) Fallback last 0..1 in stem (if allow_fallback=True)
    Returns None if nothing parseable.
    """
    stem = path.stem

    m = RE_TRAIL_01.search(stem)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass

    m = RE_NAMED_01.search(stem)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass

    if allow_fallback:
        matches = RE_ANY_01.findall(stem)
        if matches:
            try:
                return float(matches[-1])
            except ValueError:
                pass

    return None


def list_top_level_folders(src_root: Path) -> List[Path]:
    """Return immediate subfolders under src_root (only directories)."""
    return [p for p in src_root.iterdir() if p.is_dir()]


def folder_is_included(name: str, *, include_patterns: Sequence[str] | None, exclude_patterns: Sequence[str] | None) -> bool:
    """Filter folder names using optional include/exclude glob patterns (match on the folder name only)."""
    if include_patterns:
        ok = any(fnmatch.fnmatch(name, pat) for pat in include_patterns)
        if not ok:
            return False
    if exclude_patterns:
        if any(fnmatch.fnmatch(name, pat) for pat in exclude_patterns):
            return False
    return True


def iter_raw_images(folder: Path) -> Iterable[Path]:
    """
    Yield images from a '[folder]/raw' subdir only (ignores 'overlay' and others).
    """
    raw = folder / "raw"
    if not raw.is_dir():
        return
    for p in raw.iterdir():
        if p.is_file() and p.suffix.lower() in EXTS:
            yield p


def safe_transfer(src: Path, dest_dir: Path, *, action: str) -> Path:
    """
    Transfer a file using the chosen action: 'copy' (default), 'move', or 'link' (symlink).
    Never overwrite—append __1, __2, ... if needed.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if dest.exists():
        stem, suffix = dest.stem, dest.suffix
        i = 1
        while True:
            candidate = dest_dir / f"{stem}__{i}{suffix}"
            if not candidate.exists():
                dest = candidate
                break
            i += 1

    if action == "move":
        shutil.move(str(src), str(dest))
    elif action == "link":
        try:
            dest.symlink_to(src.resolve())
        except OSError:
            # Fallback to copy if symlink not permitted (Windows without admin, etc.)
            shutil.copy2(str(src), str(dest))
    else:
        shutil.copy2(str(src), str(dest))
    return dest


def percentile_count(n: int, pct: float, *, min_count: int = 0, max_count: Optional[int] = None) -> int:
    """
    Compute how many items to pick given a percentile.
    Uses ceil for at-least-one behavior when pct>0.
    Applies min_count and optional max_count.
    """
    if n <= 0 or pct <= 0:
        return 0
    k = math.ceil(n * (pct / 100.0))
    k = max(k, min_count)
    if max_count is not None:
        k = min(k, max_count)
    return k


def main() -> None:
    ap = argparse.ArgumentParser(description="Collect lowest-confidence images PER FOLDER from 'debug/training/*/raw'.")
    ap.add_argument("--src", default="debug/training", help="Root folder to scan (default: debug/training).")
    ap.add_argument("--dest-base", default="datasets/uma/raw", help="Destination base (default: datasets/uma/raw).")
    ap.add_argument("--set-name", required=True, help="Set name to create under dest-base (e.g., set_2025-10-11).")

    ap.add_argument("--percentile", type=float, default=10.0, help="Bottom percentile to pick per folder (default: 10).")
    ap.add_argument("--min-per-folder", type=int, default=0, help="Minimum picks per folder (default: 0).")
    ap.add_argument("--max-per-folder", "--max-files", type=int, default=30,
                    dest="max_per_folder", help="Cap picks per folder (default: 30).")

    ap.add_argument("--exclude", nargs="*", default=None, help="Glob folder names to exclude (space-separated).")
    ap.add_argument("--include", nargs="*", default=None, help="Glob filter to include only matching folders (space-separated).")

    ap.add_argument("--action", choices=["copy", "move", "link"], default="copy",
                    help="Transfer action for selected files (default: copy).")
    ap.add_argument("--dry-run", action="store_true", help="Preview actions without writing.")
    ap.add_argument("--treat-unscored", type=float, default=None,
                    help="If set (e.g., 0.0), include files without a parseable score using this fallback value. Default: skip unscored.")

    args = ap.parse_args()

    src_root = Path(args.src)
    if not src_root.exists():
        ap.error(f"Source not found: {src_root}")

    dest_root = Path(args.dest_base) / args.set_name

    include_pats = args.include or None
    exclude_pats = args.exclude or None

    folders = list_top_level_folders(src_root)
    folders = [f for f in folders if folder_is_included(f.name, include_patterns=include_pats, exclude_patterns=exclude_pats)]

    if not folders:
        print("No folders to scan (after include/exclude filters).")
        return

    grand_total_seen = 0
    grand_total_selected = 0
    per_folder_counts: List[Tuple[str, int, int]] = []

    for folder in sorted(folders, key=lambda p: p.name.lower()):
        # Gather scored files
        picks: List[Pick] = []
        unscored: List[Path] = []

        for img in iter_raw_images(folder):
            conf = parse_confidence_from_name(img, allow_fallback=True)
            if conf is None:
                if args.treat_unscored is None:
                    unscored.append(img)
                    continue
                conf = float(args.treat_unscored)
            # Clamp to [0,1] just in case
            conf = max(0.0, min(1.0, conf))
            picks.append(Pick(path=img, conf=conf))

        grand_total_seen += len(picks)

        if not picks and not unscored:
            per_folder_counts.append((folder.name, 0, 0))
            continue

        # Sort worst→best by confidence
        picks.sort(key=lambda x: x.conf)

        k = percentile_count(
            n=len(picks),
            pct=args.percentile,
            min_count=args.min_per_folder,
            max_count=args.max_per_folder,
        )
        chosen = picks[:k]

        grand_total_selected += len(chosen)
        per_folder_counts.append((folder.name, len(picks), len(chosen)))

        # Show a concise preview
        print(f"[{folder.name}] scored={len(picks)} unscored_skipped={len(unscored)} → pick {len(chosen)} ({args.percentile}% bottom)")

        if args.dry_run:
            dry_dest = dest_root if args.action == "move" else dest_root / folder.name
            for sample in chosen[:10]:
                print(f"  [DRY] {sample.path}  conf={sample.conf:.3f}  →  {dry_dest}")
            if len(chosen) > 10:
                print(f"  ... and {len(chosen) - 10} more")
            continue

        # Transfer to <dest>/<set-name>/<folder>/
        out_dir = dest_root if args.action == "move" else dest_root / folder.name
        for sample in chosen:
            safe_transfer(sample.path, out_dir, action=args.action)

    # Summary
    print("\n=== SUMMARY ===")
    for name, seen, picked in per_folder_counts:
        print(f"{name:>28}:  seen={seen:4d}  picked={picked:4d}")
    print(f"TOTAL scored images: {grand_total_seen}")
    print(f"TOTAL selected     : {grand_total_selected}")
    print(f"Destination root   : {dest_root}")
    if args.dry_run:
        print("Dry-run mode: no files were written.")


if __name__ == "__main__":
    main()
