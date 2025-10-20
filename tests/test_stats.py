# tests/test_stats.py
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Tuple, List, cast

import pytest
from PIL import Image, ImageDraw

_RESAMPLING_NEAREST = getattr(getattr(Image, "Resampling", Image), "NEAREST")

from core.perception.ocr.ocr_local import LocalOCREngine
from core.perception.extractors.state import extract_stats
from core.constants import CLASS_UI_STATS
from core.perception.yolo.yolo_local import LocalYOLOEngine
from core.controllers.static_image import StaticImageController
from core.settings import Settings
from core.types import DetectionDict


# ----------------------------
# Configuration
# ----------------------------
DATA_DIR = Path("tests/data")
OUT_DIR = Path("tests/outputs/test_stats")
OUT_DIR.mkdir(parents=True, exist_ok=True)

YOLO_IMGSZ = getattr(Settings, "YOLO_IMGSZ", 832)
YOLO_CONF = getattr(Settings, "YOLO_CONF", 0.60)
YOLO_IOU = getattr(Settings, "YOLO_IOU", 0.45)

DET_NAME = "PP-OCRv5_mobile_det"
REC_NAME = "en_PP-OCRv5_mobile_rec"

TOL = 25  # acceptable absolute delta per stat

# pytest tests/test_stats.py


# ----------------------------
# Helpers
# ----------------------------
def _ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def _draw_detections(pil_img: Image.Image, parsed: List[DetectionDict]) -> Image.Image:
    """Overlay YOLO detections; CLASS_UI_STATS in red, others in lime."""
    out = pil_img.copy()
    draw = ImageDraw.Draw(out)
    for d in parsed:
        x1, y1, x2, y2 = map(int, d["xyxy"])
        color = "red" if d["name"] == CLASS_UI_STATS else "lime"
        draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
        draw.text((x1 + 4, y1 + 4), f"{d['name']} {d['conf']:.2f}", fill=color)
    return out


def _save_segments_strip(
    seg_info: Dict[str, Dict[str, object]], out_path: Path
) -> None:
    """Save the 5 cropped segments as a single horizontal strip."""
    keys = ["SPD", "STA", "PWR", "GUTS", "WIT"]
    segs = [cast(Image.Image, seg_info[k]["seg"]) for k in keys]
    # normalize height to max, pad between
    h = max(s.height for s in segs)
    pad = 6
    widths = [int(s.width * (h / s.height)) if s.height else s.width for s in segs]
    strip = Image.new("RGB", (sum(widths) + pad * (len(segs) - 1), h), (20, 20, 20))
    x = 0
    for s, w in zip(segs, widths):
        resized = s.resize((w, h), _RESAMPLING_NEAREST)
        strip.paste(resized, (x, 0))
        x += w + pad
    strip.save(out_path)


def _run_pipeline(
    img_path: Path,
) -> Tuple[
    Image.Image,
    List[DetectionDict],
    Dict[str, int],
    Dict[str, Dict[str, object]],
]:
    """YOLO detect + extract stats (with & without segments)."""
    img = Image.open(img_path).convert("RGB")
    ctrl = StaticImageController(img)
    yolo_engine = LocalYOLOEngine(ctrl=ctrl)

    ocr = LocalOCREngine(
        text_detection_model_name=DET_NAME,
        text_recognition_model_name=REC_NAME,
    )

    pil_img, raw, parsed = yolo_engine.recognize(
        imgsz=YOLO_IMGSZ,
        conf=YOLO_CONF,
        iou=YOLO_IOU,
        tag=f"stats_test::{img_path.name}",
    )

    stats = extract_stats(ocr, pil_img, parsed, with_segments=False)
    seg_info = extract_stats(ocr, pil_img, parsed, with_segments=True)
    return pil_img, parsed, stats, seg_info


def _assert_with_tolerance(pred: Dict[str, int], exp: Dict[str, int], tol: int) -> None:
    missing = [k for k in exp.keys() if k not in pred]
    assert not missing, f"Missing keys in prediction: {missing}"
    for k in exp.keys():
        pv = pred[k]
        ev = exp[k]
        assert pv != -1, f"{k} not recognized (pred=-1). Expected {ev}."
        assert abs(pv - ev) <= tol, f"{k}: pred={pv}, expected={ev}, tol={tol}"


# ----------------------------
# Test cases (parametrized)
# ----------------------------
CASES = [
    (
        DATA_DIR / "lobby_stats_01_low_res.png",
        {"SPD": 385, "STA": 331, "PWR": 203, "GUTS": 128, "WIT": 167},
    ),
    (
        DATA_DIR / "lobby_stats_01_high_res.png",
        {"SPD": 385, "STA": 331, "PWR": 203, "GUTS": 128, "WIT": 167},
    ),
    (
        DATA_DIR / "training_stats_01.png",
        {"SPD": 796, "STA": 633, "PWR": 652, "GUTS": 393, "WIT": 461},
    ),
]


@pytest.mark.parametrize("img_path,expected", CASES, ids=[p[0].name for p in CASES])
def test_stats_end_to_end(img_path: Path, expected: Dict[str, int]) -> None:
    # run
    pil_img, parsed, stats, seg_info = _run_pipeline(img_path)

    # outputs folder per image
    out_dir = _ensure_dir(OUT_DIR / img_path.stem)

    # save artifacts
    _draw_detections(pil_img, parsed).save(out_dir / "detections.png")
    _save_segments_strip(seg_info, out_dir / "segments.png")
    with open(out_dir / "stats.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    # assert with tolerance
    _assert_with_tolerance(stats, expected, TOL)
