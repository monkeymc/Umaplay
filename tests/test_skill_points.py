# tests/test_skill_points.py
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

import pytest
from PIL import Image, ImageDraw

from core.controllers.static_image import StaticImageController
from core.perception.ocr.ocr_local import LocalOCREngine
from core.perception.yolo.yolo_local import LocalYOLOEngine
from core.perception.extractors.state import extract_skill_points
from core.constants import CLASS_UI_SKILLS_PTS
from core.settings import Settings


# ----------------------------
# Configuration
# ----------------------------
DATA_DIR = Path("tests/data")
OUT_DIR = Path("tests/outputs/test_skill_points")
OUT_DIR.mkdir(parents=True, exist_ok=True)

YOLO_IMGSZ = getattr(Settings, "YOLO_IMGSZ", 832)
YOLO_CONF = getattr(Settings, "YOLO_CONF", 0.60)
YOLO_IOU = getattr(Settings, "YOLO_IOU", 0.45)

DET_NAME = "PP-OCRv5_mobile_det"
REC_NAME = "en_PP-OCRv5_mobile_rec"

TOL = 25  # acceptable absolute delta


# ----------------------------
# Helpers
# ----------------------------
def _ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


from core.types import DetectionDict


def _draw_detections(pil_img: Image.Image, parsed: List[DetectionDict]) -> Image.Image:
    """Overlay YOLO detections; CLASS_UI_SKILLS_PTS in red, others in lime."""
    out = pil_img.copy()
    draw = ImageDraw.Draw(out)
    for d in parsed:
        x1, y1, x2, y2 = map(int, d["xyxy"])
        color = "red" if d["name"] == CLASS_UI_SKILLS_PTS else "lime"
        draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
        draw.text((x1 + 4, y1 + 4), f"{d['name']} {d['conf']:.2f}", fill=color)
    return out


def _run_pipeline(
    img_path: Path,
) -> Tuple[Image.Image, List[DetectionDict], int]:
    """YOLO detect + extract skill points."""
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
        tag=f"skillpts_test::{img_path.name}",
    )

    pts = extract_skill_points(ocr, pil_img, parsed, conf_min=0.20)
    return pil_img, parsed, pts


def _assert_with_tolerance(pred: int, expected: int, tol: int) -> None:
    assert pred != -1, f"Skill points not recognized (pred=-1). Expected {expected}."
    assert 0 <= pred <= 9999, f"Skill points out of range: {pred}"
    assert abs(pred - expected) <= tol, (
        f"SkillPts pred={pred}, expected={expected}, tol={tol}"
    )


# ----------------------------
# Test cases (parametrized)
# ----------------------------
CASES = [
    (DATA_DIR / "lobby_stats_01_low_res.png", 472),
    (DATA_DIR / "lobby_stats_01_high_res.png", 472),
    (DATA_DIR / "training_stats_01.png", 370),
]


@pytest.mark.parametrize("img_path,expected", CASES, ids=[p[0].name for p in CASES])
def test_skill_points_end_to_end(img_path: Path, expected: int) -> None:
    pil_img, parsed, pts = _run_pipeline(img_path)

    # outputs folder per image
    out_dir = _ensure_dir(OUT_DIR / img_path.stem)

    # save artifacts
    _draw_detections(pil_img, parsed).save(out_dir / "detections.png")
    with open(out_dir / "skill_points.json", "w", encoding="utf-8") as f:
        json.dump({"skill_points": pts}, f, indent=2, ensure_ascii=False)

    # assert with tolerance
    _assert_with_tolerance(pts, expected, TOL)
