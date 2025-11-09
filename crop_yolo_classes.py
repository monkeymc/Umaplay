#!/usr/bin/env python3
"""
Crop target classes from a YOLO dataset (normalized XYWH, 0-indexed).

Inputs
------
--dataset-dir: path to a folder with structure:
    <dataset-dir>/
      images/
      labels/
      classes.txt
--classes: comma-separated list of class *names* (as in classes.txt) or numeric indices.
--output-dir: where to write crops; subfolders per class will be created.

Optional
--------
--padding: relative padding around each box (e.g., 0.04 = 4% of box size).
--exts: comma-separated list of image extensions to probe (default: .jpg,.jpeg,.png,.bmp,.webp).
--min-side: discard crops where min(width,height) < this many pixels (after padding). Default: 1.

Outputs
-------
- <output-dir>/<class_name>/*.png  (crops)
- <output-dir>/manifest.csv        (crop_path, class_name, class_id, source_image, xmin, ymin, xmax, ymax, w, h)

Notes
-----
- classes.txt is assumed 0-indexed (line order = class id).
- Label lines are expected as: "<cls> <xc> <yc> <w> <h>" in [0,1] normalized coords (YOLO format).
"""

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from PIL import Image

def read_classes(classes_path: Path) -> List[str]:
    if not classes_path.exists():
        raise FileNotFoundError(f"classes.txt not found at: {classes_path}")
    names = []
    with classes_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                names.append(line)
    if not names:
        raise ValueError("classes.txt is empty.")
    return names

def parse_target_classes(arg_classes: str, class_names: List[str]) -> Dict[int, str]:
    """Return {class_id: class_name} for targets. Accepts names or numeric ids."""
    name_to_id = {n: i for i, n in enumerate(class_names)}
    targets: Dict[int, str] = {}
    for token in [t.strip() for t in arg_classes.split(",") if t.strip()]:
        # Try numeric id first
        if token.isdigit():
            cid = int(token)
            if cid < 0 or cid >= len(class_names):
                raise ValueError(f"Class id {cid} out of range [0..{len(class_names)-1}]")
            targets[cid] = class_names[cid]
        else:
            if token not in name_to_id:
                raise ValueError(f"Class name '{token}' not found in classes.txt")
            cid = name_to_id[token]
            targets[cid] = token
    if not targets:
        raise ValueError("No valid target classes parsed.")
    return targets

def find_image_for_label(images_dir: Path, stem: str, exts: List[str]) -> Optional[Path]:
    for ext in exts:
        p = images_dir / f"{stem}{ext}"
        if p.exists():
            return p
        # case-insensitive fallback
        for cand in images_dir.glob(f"{stem}.*"):
            if cand.suffix.lower() == ext:
                return cand
    return None

def yolo_norm_to_xyxy(xc, yc, w, h, W, H) -> Tuple[int, int, int, int]:
    x = xc * W
    y = yc * H
    bw = w * W
    bh = h * H
    xmin = int(round(x - bw / 2))
    ymin = int(round(y - bh / 2))
    xmax = int(round(x + bw / 2))
    ymax = int(round(y + bh / 2))
    # clamp
    xmin = max(0, xmin); ymin = max(0, ymin)
    xmax = min(W - 1, xmax); ymax = min(H - 1, ymax)
    return xmin, ymin, xmax, ymax

def apply_padding(xmin, ymin, xmax, ymax, W, H, pad_ratio: float):
    if pad_ratio <= 0:
        return xmin, ymin, xmax, ymax
    w = xmax - xmin + 1
    h = ymax - ymin + 1
    px = int(round(w * pad_ratio))
    py = int(round(h * pad_ratio))
    xmin = max(0, xmin - px)
    ymin = max(0, ymin - py)
    xmax = min(W - 1, xmax + px)
    ymax = min(H - 1, ymax + py)
    return xmin, ymin, xmax, ymax

def load_yolo_lines(label_path: Path) -> List[List[float]]:
    lines = []
    with label_path.open("r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            parts = raw.split()
            # Expect at least 5 tokens: class xc yc w h
            if len(parts) < 5:
                # skip malformed
                continue
            try:
                cls = int(float(parts[0]))
                xc, yc, w, h = map(float, parts[1:5])
                lines.append([cls, xc, yc, w, h])
            except Exception:
                # skip malformed rows
                continue
    return lines

def main():
    ap = argparse.ArgumentParser(description="Crop selected YOLO classes to build a classification dataset.")
    ap.add_argument("--dataset-dir", required=True, type=Path, help="Path to YOLO dataset root (contains images/, labels/, classes.txt)")
    ap.add_argument("--classes", required=True, type=str, help="Comma-separated class names or ids (as in classes.txt). Example: 'unity_spirit' or '50' or 'unity_spirit,unity_flame'")
    ap.add_argument("--output-dir", required=True, type=Path, help="Where to save crops and manifest.csv")
    ap.add_argument("--padding", type=float, default=0.0, help="Relative padding around bbox (e.g., 0.04 for +4%% each side)")
    ap.add_argument("--exts", type=str, default=".jpg,.jpeg,.png,.bmp,.webp", help="Comma-separated image extensions to probe (lowercase)")
    ap.add_argument("--min-side", type=int, default=1, help="Discard crops with min(width,height) < this many pixels after padding")
    args = ap.parse_args()

    root = args.dataset_dir
    images_dir = root / "images"
    labels_dir = root / "labels"
    classes_path = root / "classes.txt"

    if not images_dir.exists() or not labels_dir.exists():
        sys.exit(f"Expected 'images/' and 'labels/' inside {root}. Found images={images_dir.exists()} labels={labels_dir.exists()}")

    class_names = read_classes(classes_path)
    targets = parse_target_classes(args.classes, class_names)
    exts = [e.strip().lower() if e.strip().startswith(".") else "." + e.strip().lower()
            for e in args.exts.split(",") if e.strip()]

    # Prepare output
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for cname in set(targets.values()):
        (args.output_dir / cname).mkdir(parents=True, exist_ok=True)
    manifest_path = args.output_dir / "manifest.csv"

    total_labels = 0
    total_crops = 0
    skipped_small = 0
    missing_images = 0

    with manifest_path.open("w", newline="", encoding="utf-8") as mf:
        writer = csv.writer(mf)
        writer.writerow(["crop_path", "class_name", "class_id", "source_image", "xmin", "ymin", "xmax", "ymax", "w", "h"])

        for label_path in sorted(labels_dir.glob("*.txt")):
            stem = label_path.stem
            img_path = find_image_for_label(images_dir, stem, exts)
            if img_path is None:
                missing_images += 1
                continue

            anns = load_yolo_lines(label_path)
            if not anns:
                continue

            try:
                img = Image.open(img_path).convert("RGB")
            except Exception:
                # unreadable image
                continue

            W, H = img.size
            hit = False
            idx_in_image = 0

            for cls, xc, yc, w, h in anns:
                if cls not in targets:
                    continue
                hit = True
                xmin, ymin, xmax, ymax = yolo_norm_to_xyxy(xc, yc, w, h, W, H)
                xmin, ymin, xmax, ymax = apply_padding(xmin, ymin, xmax, ymax, W, H, args.padding)

                ww = xmax - xmin + 1
                hh = ymax - ymin + 1
                if min(ww, hh) < args.min_side:
                    skipped_small += 1
                    continue

                crop = img.crop((xmin, ymin, xmax + 1, ymax + 1))
                cname = targets[cls]
                crop_name = f"{stem}_{idx_in_image}_{cname}_{xmin}_{ymin}_{xmax}_{ymax}.png"
                out_path = args.output_dir / cname / crop_name
                crop.save(out_path, format="PNG", optimize=True)

                writer.writerow([str(out_path), cname, cls, str(img_path), xmin, ymin, xmax, ymax, ww, hh])
                total_crops += 1
                idx_in_image += 1

            if hit:
                total_labels += 1

    print(f"[DONE] Source label files with at least one target: {total_labels}")
    print(f"[DONE] Crops written: {total_crops}")
    if skipped_small:
        print(f"[INFO] Skipped (too small): {skipped_small}")
    if missing_images:
        print(f"[WARN] Missing image for {missing_images} label files (check extensions).")
    print(f"Manifest: {manifest_path}")

if __name__ == "__main__":
    main()
