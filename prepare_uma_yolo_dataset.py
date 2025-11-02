#!/usr/bin/env python3
"""
# pip install iterative-stratification

Prepare YOLO dataset from a 'staging' export (Label Studio -> YOLO),
with stratified splitting and convenience files for smoke and warmup runs.

Input (staging):
  datasets/uma/staging/
    images/  (all images)
    labels/  (YOLO .txt labels, same stems as images)
    classes.txt  (one class name per line, in the intended YOLO order)
    notes.json   (optional metadata; { "categories": [{ "id": int, "name": str }, ...], ... })

Outputs (under --output-root, default: datasets/uma):
  images/{train,val[,test]}/...
  labels/{train,val[,test]}/...
  data.yaml
  smoke.txt, smoke.yaml
  data_warmup.txt, data_warmup.yaml
  split_report.json (counts per class per split)
  split_report.csv  (same in CSV)

Stratification:
- Uses iterative-stratification (MultilabelStratifiedShuffleSplit) when available.
- Falls back to a simple seeded random split that tries to preserve class presence.

python prepare_uma_yolo_dataset.py   --staging-root datasets/uma/staging   --output-root datasets/uma   --val-frac 0.2   --test-frac 0.0   --warmup-frac 0.2   --smoke-count 5   --use-symlinks false   --seed 42 --clean-output true
"""

import argparse
import csv
import json
import os
import random
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

# Optional imports for better stratification
_HAS_ITER_STRAT = False
try:
    from iterstrat.ml_stratifiers import MultilabelStratifiedShuffleSplit  # type: ignore
    _HAS_ITER_STRAT = True
except Exception:
    _HAS_ITER_STRAT = False

import numpy as np


# ---------- Helpers ----------

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


def read_classes_txt(p: Path) -> List[str]:
    if not p.exists():
        raise FileNotFoundError(f"classes.txt not found at {p}")
    names = [line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(names) == 0:
        raise ValueError("classes.txt is empty.")
    return names


def read_notes_json(p: Path) -> Optional[Dict]:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[warn] Could not parse notes.json: {e}")
        return None


def check_names_vs_notes(names: List[str], notes: Optional[Dict]) -> None:
    """Cross-check class order with notes.json (if available). Warn if mismatch."""
    if not notes:
        return
    cats = notes.get("categories", [])
    if not isinstance(cats, list) or not cats:
        return
    # build id->name per notes
    by_id = sorted([(c.get("id"), c.get("name")) for c in cats if "id" in c and "name" in c], key=lambda x: x[0])
    notes_names = [n for _, n in by_id]
    if len(notes_names) != len(names):
        print(f"[warn] classes.txt count ({len(names)}) != notes.json categories count ({len(notes_names)}).")
        return
    if notes_names != names:
        print("[warn] Class order mismatch between classes.txt and notes.json categories.")
        print("       Using the order from classes.txt for data.yaml. Ensure your labels' numeric IDs match this order.")


@dataclass
class Item:
    stem: str
    img_path: Path
    lbl_path: Path
    classes: List[int]  # unique class IDs in this image


def parse_label_file(p: Path) -> List[int]:
    """Return unique class IDs present in this YOLO label file."""
    ids: Set[int] = set()
    if not p.exists():
        return []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 5:
            # Malformed line; skip robustly
            continue
        try:
            cid = int(float(parts[0]))
        except Exception:
            continue
        ids.add(cid)
    return sorted(ids)


def collect_items(staging_root: Path) -> Tuple[List[Item], Dict[int, int]]:
    images_dir = staging_root / "images"
    labels_dir = staging_root / "labels"
    if not images_dir.exists() or not labels_dir.exists():
        raise FileNotFoundError(f"Expected 'images/' and 'labels/' under {staging_root}")

    items: List[Item] = []
    class_freq: Dict[int, int] = {}
    for img in sorted(images_dir.rglob("*")):
        if not img.is_file() or img.suffix.lower() not in IMAGE_EXTS:
            continue
        stem = img.stem
        lbl = labels_dir / f"{stem}.txt"
        if not lbl.exists():
            # skip unlabeled
            continue
        cls_ids = parse_label_file(lbl)
        if not cls_ids:
            # skip images with empty labels; YOLO will treat as background
            continue
        for cid in cls_ids:
            class_freq[cid] = class_freq.get(cid, 0) + 1
        items.append(Item(stem=stem, img_path=img, lbl_path=lbl, classes=cls_ids))
    if not items:
        raise ValueError("No labeled images found in staging (or labels are empty).")
    return items, class_freq


def multilabel_indicator(items: Sequence[Item], n_classes: int) -> np.ndarray:
    Y = np.zeros((len(items), n_classes), dtype=int)
    for i, it in enumerate(items):
        for cid in it.classes:
            if 0 <= cid < n_classes:
                Y[i, cid] = 1
    return Y


def iterative_stratified_split(
    items: List[Item],
    n_classes: int,
    val_frac: float,
    test_frac: float,
    seed: int,
) -> Tuple[List[Item], List[Item], List[Item]]:
    """Train/val[/test] split using MultilabelStratifiedShuffleSplit."""
    N = len(items)
    idx = np.arange(N)
    Y = multilabel_indicator(items, n_classes)

    if val_frac < 0 or test_frac < 0 or (val_frac + test_frac) >= 1.0:
        raise ValueError("Invalid val/test fractions. They must be >=0 and sum to < 1.0.")

    # First, hold out (val+test)
    hold_frac = val_frac + test_frac
    if hold_frac > 0:
        msss = MultilabelStratifiedShuffleSplit(n_splits=1, test_size=hold_frac, random_state=seed)
        train_idx, hold_idx = next(msss.split(idx.reshape(-1, 1), Y))
        train_items = [items[i] for i in train_idx]
        hold_items = [items[i] for i in hold_idx]
    else:
        train_items, hold_items = items[:], []

    # Then split hold into val/test according to proportions
    if test_frac == 0:
        val_items = hold_items
        test_items: List[Item] = []
    else:
        # proportion of test within hold
        if not hold_items:
            raise ValueError("Requested a test split but not enough data to create holdout.")
        rel_test = test_frac / (val_frac + test_frac)
        Y_hold = multilabel_indicator(hold_items, n_classes)
        msss2 = MultilabelStratifiedShuffleSplit(n_splits=1, test_size=rel_test, random_state=seed + 1)
        idx_hold = np.arange(len(hold_items))
        val_idx, test_idx = next(msss2.split(idx_hold.reshape(-1, 1), Y_hold))
        val_items = [hold_items[i] for i in val_idx]
        test_items = [hold_items[i] for i in test_idx]

    return train_items, val_items, test_items


def simple_seeded_split(
    items: List[Item],
    val_frac: float,
    test_frac: float,
    seed: int,
) -> Tuple[List[Item], List[Item], List[Item]]:
    """Fallback random split. Not as good as iterative stratification."""
    rng = random.Random(seed)
    items_shuffled = items[:]
    rng.shuffle(items_shuffled)
    N = len(items_shuffled)
    n_val = int(round(val_frac * N))
    n_test = int(round(test_frac * N))
    n_train = max(0, N - n_val - n_test)
    train = items_shuffled[:n_train]
    val = items_shuffled[n_train:n_train + n_val]
    test = items_shuffled[n_train + n_val:n_train + n_val + n_test]
    return train, val, test


def enforce_split_coverage(
    train: List[Item],
    val: List[Item],
    test: List[Item],
    n_classes: int,
) -> Tuple[List[Item], List[Item], List[Item]]:
    """Deterministically ensure train and val keep minimum per-class coverage.

    Rules:
    - Every class present anywhere must appear in TRAIN at least once.
    - If a class has >= 2 total samples, ensure VAL holds at least one.
    """

    splits = {
        "train": list(train),
        "val": list(val),
        "test": list(test),
    }

    counts: Dict[str, List[int]] = {split: [0] * n_classes for split in splits}
    totals = [0] * n_classes

    for split_name, items in splits.items():
        for it in items:
            for cid in it.classes:
                counts[split_name][cid] += 1
                totals[cid] += 1 if split_name == "train" else 0

    # Add val/test contributions to totals
    for it in splits["val"]:
        for cid in it.classes:
            totals[cid] += 1
    for it in splits["test"]:
        for cid in it.classes:
            totals[cid] += 1

    def item_key(it: Item) -> Tuple[int, str]:
        return (len(it.classes), it.stem)

    def move(item: Item, src: str, dst: str) -> None:
        if item not in splits[src]:
            return
        splits[src].remove(item)
        splits[dst].append(item)
        for cid in item.classes:
            counts[src][cid] -= 1
            counts[dst][cid] += 1

    def required_val(cid: int) -> int:
        return 1 if totals[cid] >= 2 else 0

    def required_train(cid: int) -> int:
        return 1 if totals[cid] > 0 else 0

    def pick_candidate(split: str, cid: int) -> Optional[Item]:
        candidates = [it for it in splits[split] if cid in it.classes]
        if not candidates:
            return None
        candidates.sort(key=item_key)
        return candidates[0]

    def enforce_val() -> bool:
        changed = False
        for cid in sorted(range(n_classes), key=lambda c: (totals[c], c)):
            need = required_val(cid)
            if need == 0:
                continue
            while counts["val"][cid] < need:
                candidate: Optional[Tuple[str, Item]] = None
                if counts["test"][cid] > 0:
                    item = pick_candidate("test", cid)
                    if item:
                        candidate = ("test", item)
                elif counts["train"][cid] > 0:
                    item = pick_candidate("train", cid)
                    if item:
                        candidate = ("train", item)
                if not candidate:
                    break
                src, item = candidate
                move(item, src, "val")
                changed = True
        return changed

    def enforce_train() -> bool:
        changed = False
        for cid in sorted(range(n_classes), key=lambda c: (totals[c], c)):
            need = required_train(cid)
            while counts["train"][cid] < need:
                min_val = required_val(cid)
                candidate: Optional[Tuple[str, Item]] = None
                if counts["val"][cid] > min_val:
                    item = pick_candidate("val", cid)
                    if item:
                        candidate = ("val", item)
                elif counts["test"][cid] > 0:
                    item = pick_candidate("test", cid)
                    if item:
                        candidate = ("test", item)
                if not candidate:
                    break
                src, item = candidate
                move(item, src, "train")
                changed = True
        return changed

    def invariants_ok() -> bool:
        for cid in range(n_classes):
            if totals[cid] == 0:
                continue
            if counts["train"][cid] == 0:
                return False
            if totals[cid] >= 2 and counts["val"][cid] == 0:
                return False
        return True

    max_iterations = max(1, n_classes * 4)
    for _ in range(max_iterations):
        changed = False
        changed |= enforce_val()
        changed |= enforce_train()
        if invariants_ok():
            break
        if not changed:
            break

    if not invariants_ok():
        missing_train = [cid for cid in range(n_classes) if totals[cid] > 0 and counts["train"][cid] == 0]
        missing_val = [cid for cid in range(n_classes) if totals[cid] >= 2 and counts["val"][cid] == 0]
        raise RuntimeError(
            "Failed to enforce per-class coverage: "
            f"train_missing={missing_train}, val_missing={missing_val}"
        )

    for split_name in splits:
        splits[split_name].sort(key=lambda it: it.stem)

    return splits["train"], splits["val"], splits["test"]


def materialize_split(
    split_name: str,
    items: List[Item],
    out_root: Path,
    use_symlinks: bool,
) -> List[Path]:
    """Copy or symlink images/labels into out_root/images/split and out_root/labels/split."""
    out_img = out_root / "images" / split_name
    out_lbl = out_root / "labels" / split_name
    out_img.mkdir(parents=True, exist_ok=True)
    out_lbl.mkdir(parents=True, exist_ok=True)

    written: List[Path] = []
    for it in items:
        dst_img = out_img / it.img_path.name
        dst_lbl = out_lbl / it.lbl_path.name

        if use_symlinks:
            # Windows symlinks might need admin; fallback to copy if fails
            try:
                if not dst_img.exists():
                    os.symlink(it.img_path.resolve(), dst_img)
            except Exception:
                shutil.copy2(it.img_path, dst_img)
            try:
                if not dst_lbl.exists():
                    os.symlink(it.lbl_path.resolve(), dst_lbl)
            except Exception:
                shutil.copy2(it.lbl_path, dst_lbl)
        else:
            shutil.copy2(it.img_path, dst_img)
            shutil.copy2(it.lbl_path, dst_lbl)
        written.append(dst_img)
    return written


def write_yaml(
    out_yaml: Path,
    out_root: Path,
    names: List[str],
    include_test: bool,
) -> None:
    """Write main data.yaml."""
    path_line = f"path: {out_root.resolve().as_posix()}"
    train_line = "train: images/train"
    val_line = "val: images/val"
    test_line = "test: images/test" if include_test else None

    names_block = "names:\n" + "\n".join([f"  - {n}" for n in names])
    lines = [path_line, train_line, val_line]
    if test_line:
        lines.append(test_line)
    lines.append("")
    lines.append(names_block)
    out_yaml.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_list_file(fp: Path, items: List[Item]) -> None:
    """Write a YOLO 'list-of-images' file (absolute paths)."""
    fp.write_text(
        "\n".join([it.img_path.resolve().as_posix() for it in items]) + "\n",
        encoding="utf-8",
    )


def write_smoke(
    out_root: Path,
    names: List[str],
    train_items: List[Item],
    k: int = 5,
) -> None:
    """Pick K images from TRAIN that cover frequent classes greedily."""
    k = max(1, min(k, len(train_items)))
    # frequency by class
    freq: Dict[int, int] = {}
    for it in train_items:
        for c in it.classes:
            freq[c] = freq.get(c, 0) + 1
    # sort items by "coverage score" (sum of class frequencies, preferring more classes)
    def score(it: Item) -> Tuple[int, int]:
        return (sum(freq.get(c, 0) for c in it.classes), len(set(it.classes)))

    selected: List[Item] = []
    covered: Set[int] = set()
    pool = sorted(train_items, key=score, reverse=True)

    # greedily cover new classes first
    for it in pool:
        if len(selected) >= k:
            break
        if any(c not in covered for c in it.classes):
            selected.append(it)
            covered.update(it.classes)

    # fill remainder
    if len(selected) < k:
        for it in pool:
            if it not in selected:
                selected.append(it)
                if len(selected) >= k:
                    break

    smoke_txt = out_root / "smoke.txt"
    smoke_yaml = out_root / "smoke.yaml"
    write_list_file(smoke_txt, selected)

    # smoke.yaml points train/val to the same list (overfit smoke test)
    smoke_yaml.write_text(
        f"""path: {out_root.resolve().as_posix()}
train: smoke.txt
val: smoke.txt

names:
""" + "\n".join([f"  - {n}" for n in names]) + "\n",
        encoding="utf-8",
    )
    print(f"[smoke] wrote {smoke_txt} and {smoke_yaml} ({len(selected)} images)")


def write_warmup(
    out_root: Path,
    names: List[str],
    train_items: List[Item],
    val_exists: bool,
    warmup_frac: float = 0.2,
    seed: int = 42,
) -> None:
    """Create data_warmup.txt and data_warmup.yaml.
    - Train on a stratified subset of TRAIN (default 20%).
    - Validate on the MAIN VAL if it exists, else validate on the same subset.
    """
    if warmup_frac <= 0 or warmup_frac >= 1:
        warmup_frac = 0.2

    rng = random.Random(seed)
    N = len(train_items)
    k = max(1, int(round(warmup_frac * N)))

    # Prefer stratified sampling by class presence
    idx = list(range(N))
    if _HAS_ITER_STRAT:
        # one-shot holdout from train to get 'warmup' subset
        # we want exactly k items -> test_size = k/N
        Y = multilabel_indicator(train_items, max((c for it in train_items for c in it.classes), default=-1) + 1)
        test_size = min(0.9, max(1 / N, k / N))
        msss = MultilabelStratifiedShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
        tr_idx, wu_idx = next(msss.split(np.arange(N).reshape(-1, 1), Y))
        # If too many due to rounding, trim
        wu_idx = list(wu_idx)[:k]
        selected = [train_items[i] for i in wu_idx]
    else:
        # fallback random
        rng.shuffle(idx)
        selected = [train_items[i] for i in idx[:k]]

    warm_txt = out_root / "data_warmup.txt"
    write_list_file(warm_txt, selected)

    warm_yaml = out_root / "data_warmup.yaml"
    # For warmup we train on the subset and (by default) validate on the main val set
    val_ref = "images/val" if val_exists else "data_warmup.txt"
    warm_yaml.write_text(
        f"""path: {out_root.resolve().as_posix()}
train: data_warmup.txt
val: {val_ref}

names:
""" + "\n".join([f"  - {n}" for n in names]) + "\n",
        encoding="utf-8",
    )
    print(f"[warmup] wrote {warm_txt} and {warm_yaml} ({len(selected)} images), val -> {val_ref}")


def write_reports(
    out_root: Path,
    names: List[str],
    train: List[Item],
    val: List[Item],
    test: List[Item],
) -> None:
    """Write per-class counts per split to JSON and CSV."""
    def counts(items: List[Item], n_classes: int) -> List[int]:
        arr = [0] * n_classes
        for it in items:
            for c in it.classes:
                if 0 <= c < n_classes:
                    arr[c] += 1
        return arr

    n_classes = len(names)
    c_train = counts(train, n_classes)
    c_val = counts(val, n_classes)
    c_test = counts(test, n_classes)

    rep = {
        "splits": {
            "train": len(train),
            "val": len(val),
            "test": len(test)
        },
        "per_class": [
            {
                "id": i,
                "name": names[i],
                "train": c_train[i],
                "val": c_val[i],
                "test": c_test[i],
            }
            for i in range(n_classes)
        ]
    }
    (out_root / "split_report.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")

    with (out_root / "split_report.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["class_id", "name", "train", "val", "test"])
        for i in range(n_classes):
            w.writerow([i, names[i], c_train[i], c_val[i], c_test[i]])

    print(f"[report] wrote split_report.json and split_report.csv")

def _safe_unlink(p: Path):
    try:
        if p.exists() or p.is_symlink():
            p.unlink()
    except Exception as e:
        print(f"[warn] could not delete file {p}: {e}")

def _safe_rmtree(p: Path):
    try:
        if p.exists():
            shutil.rmtree(p)
    except Exception as e:
        print(f"[warn] could not delete directory {p}: {e}")

def clean_previous_outputs(out_root: Path, staging_root: Path):
    """
    Remove only the elements generated by this script.
    Does NOT touch 'staging/' or 'raw/' (or anything inside them).
    """
    # Always resolve to avoid accidental relative overlaps
    out_root = out_root.resolve()
    staging_root = staging_root.resolve()
    raw_dir = (out_root / "raw").resolve()  # conventional; OK if it doesn't exist

    # Paths to clean (directories)
    dirs_to_remove = [
        out_root / "images" / "train",
        out_root / "images" / "val",
        out_root / "images" / "test",
        out_root / "labels" / "train",
        out_root / "labels" / "val",
        out_root / "labels" / "test",
    ]

    # Guard: do not remove if target is staging or raw or inside them
    def _protected(path: Path) -> bool:
        rp = path.resolve()
        return (rp == staging_root or str(rp).startswith(str(staging_root) + os.sep)
                or rp == raw_dir or str(rp).startswith(str(raw_dir) + os.sep))

    # Remove directories
    for d in dirs_to_remove:
        if _protected(d):
            print(f"[skip] protected path, not deleting: {d}")
            continue
        _safe_rmtree(d)

    # Remove top-level generated files
    files_to_remove = [
        out_root / "data.yaml",
        out_root / "smoke.txt",
        out_root / "smoke.yaml",
        out_root / "data_warmup.txt",
        out_root / "data_warmup.yaml",
        out_root / "split_report.json",
        out_root / "split_report.csv",
    ]
    for f in files_to_remove:
        if _protected(f):
            print(f"[skip] protected path, not deleting: {f}")
            continue
        _safe_unlink(f)

    # Optional: if images/ or labels/ become empty directories, keep them (harmless).
    print("[clean] previous generated outputs removed (if they existed).")


# ---------- Main ----------

def main():
    ap = argparse.ArgumentParser(description="Create stratified YOLO splits + smoke/warmup from staging.")
    ap.add_argument("--staging-root", type=str, required=True, help="Path to staging folder (contains images/, labels/, classes.txt, notes.json).")
    ap.add_argument("--output-root", type=str, default="datasets/uma", help="Path to output dataset root.")
    ap.add_argument("--val-frac", type=float, default=0.2, help="Validation fraction (0..1).")
    ap.add_argument("--test-frac", type=float, default=0.0, help="Test fraction (0..1). If 0, no test split.")
    ap.add_argument("--warmup-frac", type=float, default=0.2, help="Warmup subset fraction of TRAIN for data_warmup.txt.")
    ap.add_argument("--smoke-count", type=int, default=5, help="How many images to put in smoke.txt.")
    ap.add_argument("--use-symlinks", type=str, default="false", help="Use symlinks instead of copying files (true/false).")
    ap.add_argument("--seed", type=int, default=42, help="Random seed.")
    ap.add_argument("--clean-output", type=str, default="false",
                help="Remove previous generated splits/files under --output-root before creating new ones (true/false).")

    args = ap.parse_args()

    staging_root = Path(args.staging_root)
    out_root = Path(args.output_root)
    out_root.mkdir(parents=True, exist_ok=True)

    use_symlinks = str(args.use_symlinks).strip().lower() in {"1", "true", "yes", "y"}

    clean_output = str(args.clean_output).strip().lower() in {"1", "true", "yes", "y"}
    if clean_output:
        if str(staging_root).startswith(str(out_root / "images")) or str(staging_root).startswith(str(out_root / "labels")):
            raise RuntimeError("Refusing to clean: staging_root appears to be inside output splits. Check your paths.")
        clean_previous_outputs(out_root, staging_root)

    # 1) Read class names and notes
    classes_txt = staging_root / "classes.txt"
    names = read_classes_txt(classes_txt)
    notes = read_notes_json(staging_root / "notes.json")
    check_names_vs_notes(names, notes)
    n_classes = len(names)

    # 2) Collect labeled items
    items, freq = collect_items(staging_root)
    print(f"[info] collected {len(items)} labeled images from staging")

    # 3) Stratified split
    if _HAS_ITER_STRAT:
        train, val, test = iterative_stratified_split(
            items, n_classes, args.val_frac, args.test_frac, seed=args.seed
        )
    else:
        print("[warn] iterative-stratification not installed; using simple random split")
        train, val, test = simple_seeded_split(
            items, args.val_frac, args.test_frac, seed=args.seed
        )

    # 3b) Ensure every class and validation coverage meet minimums
    train, val, test = enforce_split_coverage(train, val, test, n_classes)

    print(f"[split] train={len(train)} val={len(val)} test={len(test)}")

    # 4) Materialize directories
    written_train = materialize_split("train", train, out_root, use_symlinks)
    written_val = materialize_split("val", val, out_root, use_symlinks)
    include_test = len(test) > 0
    if include_test:
        _ = materialize_split("test", test, out_root, use_symlinks)

    # 5) Main data.yaml
    write_yaml(out_root / "data.yaml", out_root, names, include_test=include_test)
    print(f"[yaml] wrote {out_root / 'data.yaml'}")

    # 6) Smoke files (from TRAIN)
    write_smoke(out_root, names, train_items=train, k=args.smoke_count)

    # 7) Warmup files (subset of TRAIN; validate on main VAL if it exists)
    write_warmup(
        out_root, names, train_items=train, val_exists=(len(val) > 0),
        warmup_frac=args.warmup_frac, seed=args.seed
    )

    # 8) Reports
    write_reports(out_root, names, train, val, test)

    print("\nDone.\n"
          f"- Main YAML: {out_root / 'data.yaml'}\n"
          f"- Smoke:     {out_root / 'smoke.txt'}, {out_root / 'smoke.yaml'}\n"
          f"- Warmup:    {out_root / 'data_warmup.txt'}, {out_root / 'data_warmup.yaml'}\n"
          f"- Splits at: {out_root / 'images'} and {out_root / 'labels'}\n")


if __name__ == "__main__":
    main()
