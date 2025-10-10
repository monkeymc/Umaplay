# tests/test_career_date.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple, List

import pytest
from PIL import Image, ImageDraw

from core.perception.extractors.state import extract_career_date, find_best
from core.perception.yolo.yolo_local import LocalYOLOEngine
from core.perception.ocr.ocr_local import LocalOCREngine
from core.controllers.static_image import StaticImageController
from core.settings import Settings
from core.constants import CLASS_UI_TURNS
from core.utils.geometry import xyxy_int
from core.utils.preprocessors import (
    tighten_to_pill,
    career_date_crop_box,
    preprocess_digits,
    read_date_pill_robust,
)

from core.utils.date_uma import parse_career_date

# ----------------------------
# Configuration
# ----------------------------
DATA_DIR = Path("tests/data")
OUT_DIR = Path("tests/outputs/test_career_date")
OUT_DIR.mkdir(parents=True, exist_ok=True)

YOLO_IMGSZ = getattr(Settings, "YOLO_IMGSZ", 832)
YOLO_CONF = getattr(Settings, "YOLO_CONF", 0.60)
YOLO_IOU = getattr(Settings, "YOLO_IOU", 0.45)

DET_NAME = "PP-OCRv5_mobile_det"
REC_NAME = "en_PP-OCRv5_mobile_rec"


# ----------------------------
# Helpers
# ----------------------------
def _ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def _draw_turns_and_boxes(
    pil_img: Image.Image,
    turns_xyxy: Tuple[int, int, int, int],
    banner_box: Tuple[int, int, int, int],
    pill_box_abs: Tuple[int, int, int, int],
) -> Image.Image:
    """Overlay turns (red), banner (gold), pill (lime)."""
    viz = pil_img.copy()
    d = ImageDraw.Draw(viz)
    d.rectangle(xyxy_int(turns_xyxy), outline="red", width=3)
    d.rectangle(banner_box, outline="gold", width=3)
    d.rectangle(pill_box_abs, outline="lime", width=3)
    return viz


def _key_numeric(di) -> str:
    """Y{year}-{MM or 'None'}-{half or 'None'}"""
    m = "None" if di.month is None else f"{di.month:02d}"
    h = "None" if di.half is None else str(di.half)
    return f"Y{di.year_code}-{m}-{h}"


def _run_pipeline(img_path: Path):
    img = Image.open(img_path).convert("RGB")
    ctrl = StaticImageController(img)
    yolo = LocalYOLOEngine(ctrl=ctrl)
    ocr = LocalOCREngine(DET_NAME, REC_NAME)

    pil_img, _, parsed = yolo.recognize(
        imgsz=YOLO_IMGSZ,
        conf=YOLO_CONF,
        iou=YOLO_IOU,
        tag=f"career_date::{img_path.name}",
    )

    turns_det = find_best(parsed, CLASS_UI_TURNS, conf_min=0.20)
    assert turns_det, "Turns widget not found."

    # banner and pill boxes for artifacts
    bx1, by1, bx2, by2 = career_date_crop_box(pil_img, turns_det["xyxy"])
    banner_box = (bx1, by1, bx2, by2)

    pill_box_local = tighten_to_pill(pil_img.crop(banner_box))
    px1, py1, px2, py2 = (
        bx1 + pill_box_local[0],
        by1 + pill_box_local[1],
        bx1 + pill_box_local[2],
        by1 + pill_box_local[3],
    )
    pill_box_abs = (px1, py1, px2, py2)

    # robust OCR via extractor (uses the enhancement cascade)
    raw = extract_career_date(ocr, pil_img, parsed, conf_min=0.20)
    di = parse_career_date(raw)

    return pil_img, parsed, turns_det["xyxy"], banner_box, pill_box_abs, raw, di


# ----------------------------
# Test cases (parametrized)
# ----------------------------
CASES = [
    # (
    #     DATA_DIR / "lobby_stats_01_low_res.png",
    #     "Y2-04-2",  # Classic Year Late Apr
    # ),
    (
        DATA_DIR / "lobby_stats_01_high_res.png",
        "Y2-04-2",  # Classic Year Late Apr
    ),
    (
        DATA_DIR / "training_stats_01.png",
        "Y4-None-None",  # Finale Season
    ),
]


@pytest.mark.parametrize("img_path,expected_key", CASES, ids=[p[0].name for p in CASES])
def test_career_date_end_to_end(img_path: Path, expected_key: str) -> None:
    pil_img, parsed, turns_xyxy, banner_box, pill_box_abs, raw, di = _run_pipeline(
        img_path
    )

    # Save artifacts per image
    out_dir = _ensure_dir(OUT_DIR / img_path.stem)
    # viz
    _draw_turns_and_boxes(pil_img, turns_xyxy, banner_box, pill_box_abs).save(
        out_dir / "viz_boxes.png"
    )
    # crops
    pil_img.crop(banner_box).save(out_dir / "banner.png")
    pil_img.crop(pill_box_abs).save(out_dir / "pill.png")
    # metadata
    with open(out_dir / "career_date.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "raw": raw,
                "parsed": {
                    "year_code": di.year_code,
                    "month": di.month,
                    "half": di.half,
                },
                "key_numeric": _key_numeric(di),
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    # assert
    assert _key_numeric(di) == expected_key, f"raw='{raw}' parsed={di}"
