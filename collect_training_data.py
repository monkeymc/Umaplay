#!/usr/bin/env python3
"""
Collect low-confidence images from ML debug output.

It searches all subfolders under --src that are named exactly 'raw', looks for images
whose filenames end with '_<confidence>.<ext>' (e.g., "foo_0.66.png"), and moves those
with confidence <= --threshold into datasets/uma/raw/<set-name>.

Usage example:
  python collect_training_data.py --threshold 0.60 --set-name set_2025-09-13z
  python collect_training_data.py --threshold 0.60 --set-name set_2025-XY-ZW --dry-run
"""

import argparse
import re
import shutil
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

# Match the trailing confidence number just before the extension:
# ..._0.66.png  | ..._1.0.JPG | ..._0.700.jpeg | case-insensitive
CONF_RE = re.compile(
    r"_([0-9]+(?:\.[0-9]+)?)\.(?:png|jpg|jpeg|bmp|webp)$", re.IGNORECASE
)

# Allowed image extensions (lowercase)
EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def extract_confidence(name: str) -> Optional[float]:
    """Return the trailing confidence parsed from filename, or None if not found."""
    m = CONF_RE.search(name)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def iter_raw_images(root: Path) -> Iterable[Path]:
    """Yield image files from every subfolder named exactly 'raw' under root."""
    for raw_dir in root.rglob("raw"):
        if not raw_dir.is_dir() or raw_dir.name != "raw":
            continue
        for p in raw_dir.iterdir():
            if p.is_file() and p.suffix.lower() in EXTS:
                yield p


def safe_move(src: Path, dest_dir: Path) -> Path:
    """
    Move src into dest_dir without overwriting.
    If a name collision occurs, append __1, __2, ... to the stem.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if not dest.exists():
        shutil.move(str(src), str(dest))
        return dest

    stem, suffix = dest.stem, dest.suffix
    i = 1
    while True:
        candidate = dest_dir / f"{stem}__{i}{suffix}"
        if not candidate.exists():
            shutil.move(str(src), str(candidate))
            return candidate
        i += 1


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Collect low-confidence images from 'raw' folders."
    )
    ap.add_argument(
        "--src",
        default="debug/training",
        help="Root folder to search (default: debug/training).",
    )
    ap.add_argument(
        "--dest-base",
        default="datasets/uma/raw",
        help="Base destination folder (default: datasets/uma/raw).",
    )
    ap.add_argument(
        "--set-name",
        required=True,
        help="Name of the destination set folder (e.g., set_2025-09-13 or set_2025-XY-ZW).",
    )
    ap.add_argument(
        "--threshold",
        type=float,
        required=True,
        help="Move files whose confidence is <= this value (e.g., 0.70).",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned moves without performing them.",
    )

    args = ap.parse_args()
    src_root = Path(args.src)
    dest_dir = Path(args.dest_base) / args.set_name

    if not src_root.exists():
        ap.error(f"Source folder not found: {src_root}")

    # Plan selection
    total_seen = 0
    selected: List[Tuple[Path, float]] = []
    for img in iter_raw_images(src_root):
        total_seen += 1
        conf = extract_confidence(img.name)
        if conf is None:
            continue
        if conf <= args.threshold:
            selected.append((img, conf))

    print(
        f"Scanned {total_seen} image(s) under '{src_root}' → {len(selected)} meet confidence <= {args.threshold:.2f}."
    )
    print(f"Destination: {dest_dir}")

    if args.dry_run:
        # Show a handful so output stays readable
        preview = 20
        for p, c in selected[:preview]:
            print(f"[DRY-RUN] Would move: {p}  (conf={c:.2f})  →  {dest_dir}")
        if len(selected) > preview:
            print(f"... and {len(selected) - preview} more.")
        return

    # Execute moves
    moved = 0
    for p, c in selected:
        safe_move(p, dest_dir)
        moved += 1

    print(f"Moved {moved} file(s). Done.")


if __name__ == "__main__":
    main()
