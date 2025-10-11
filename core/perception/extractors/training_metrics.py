# core/perception/extractors/training_metrics.py
from __future__ import annotations
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

from core.perception.ocr.interface import OCRInterface
from core.utils.logger import logger_uma


def _center(xyxy: Tuple[float, float, float, float]) -> Tuple[float, float]:
    x1, y1, x2, y2 = xyxy
    return (0.5 * (x1 + x2), 0.5 * (y1 + y2))


def _nearest_detection(
    parsed_objects_screen: List[Dict],
    name: str,
    target_center: Tuple[float, float],
    conf_min: float = 0.60,
) -> Optional[Dict]:
    cands = [
        d for d in parsed_objects_screen if d["name"] == name and d["conf"] >= conf_min
    ]
    if not cands:
        return None
    tx, ty = target_center
    return min(
        cands,
        key=lambda d: (
            (0.5 * (d["xyxy"][0] + d["xyxy"][2]) - tx) ** 2
            + (0.5 * (d["xyxy"][1] + d["xyxy"][3]) - ty) ** 2
        ),
    )


def _failure_band_xyxy(
    frame_shape, btn_xyxy, stats_xyxy
) -> Optional[Tuple[int, int, int, int]]:
    """
    Stats bottom → button top; centered on the button width. Never crosses above stats.
    Returns (x1,y1,x2,y2) in left_img coordinates.
    """
    H, W = frame_shape[:2]
    bx1, by1, bx2, by2 = [int(round(v)) for v in btn_xyxy]
    _, _, _, sy2 = [int(round(v)) for v in stats_xyxy]

    btn_w = max(8, bx2 - bx1)
    btn_h = max(8, by2 - by1)
    cx = int(round((bx1 + bx2) * 0.5))

    # center horizontally on the button; trim capsule edges a bit
    pad_x = max(2, int(0.02 * btn_w))
    x1 = max(0, cx - btn_w // 2 + pad_x)
    x2 = min(W, cx + (btn_w - btn_w // 2) - pad_x)

    guard = max(1, int(0.1 * btn_h))
    top = sy2
    bottom = by1 + guard  # just below button

    if bottom <= top:
        return None  # no room to read

    # desired height ~70% of button height, but never exceed the gap
    tgt_h = max(18, min(int(round(0.70 * btn_h)), 64))
    gap_h = bottom - top
    h = min(tgt_h, gap_h)

    # center vertically in the available gap
    mid = (top + bottom) // 2
    y1 = max(top, mid - h // 2)
    y2 = min(bottom, y1 + h)

    if x2 <= x1 or y2 <= y1:
        return None
    return (x1, y1, x2, y2)


def extract_failure_pct_for_tile(
    left_img: Image.Image,
    objs: List[Dict],
    tile_xyxy: Tuple[float, float, float, float],
    ocr: OCRInterface,
    conf_btn_min: float = 0.65,
    conf_stats_min: float = 0.50,
) -> int:
    # TODO
    #  def _parse_failure_from_text(text: str) -> Optional[int]:
    #     """
    #     Prefer `N%` in the text; else any plausible 0..100 integer.
    #     """
    #     if not text:
    #         return None

    #     low = text.lower()

    #     # Normalize confusable characters
    #     trans = str.maketrans({
    #         'O': '0', 'o': '0',
    #         'I': '1', 'l': '1', '|': '1', '!': '1',
    #         'S': '5', 's': '5',
    #         'B': '8',
    #         'Z': '2', 'z': '2',
    #         'g': '9', 'q': '9',
    #         # common stray chars:
    #         '—': '-', '–': '-', '•': ' ',
    #     })
    #     norm = low.translate(trans)

    #     # Remove known words (keep % so regex can catch N%)
    #     norm = re.sub(r'(failure|fa1lure|faiiure|falure|fail|risk|chance|chanc|risl|ris1k)', ' ', norm)

    #     # Keep only digits, %, spaces
    #     keep = re.sub(r'[^0-9% ]+', ' ', norm)
    #     keep = re.sub(r'\s+', ' ', keep).strip()

    #     # 1) look for "NN%"
    #     m = re.search(r'(\d{1,3})\s*%', keep)
    #     if m:
    #         try:
    #             n = int(m.group(1))
    #             if 0 <= n <= 100:
    #                 return n
    #         except Exception:
    #             pass

    #     # 2) otherwise: first plausible 0..100 number
    #     nums = [int(x) for x in re.findall(r'\b(\d{1,3})\b', keep)]
    #     for n in nums:
    #         if 0 <= n <= 100:
    #             return n

    #     return None

    tile_c = _center(tile_xyxy)
    btn = _nearest_detection(objs, "training_button", tile_c, conf_min=conf_btn_min)
    stats = _nearest_detection(objs, "ui_stats", tile_c, conf_min=conf_stats_min)
    if btn is None or stats is None:
        logger_uma.debug("[failure] missing btn/stats for failure calculation")
        return -1

    frame_bgr = cv2.cvtColor(np.array(left_img), cv2.COLOR_RGB2BGR)

    # band between ui_stats (bottom) and button (top), same width as button
    band_xyxy = _failure_band_xyxy(frame_bgr.shape, btn["xyxy"], stats["xyxy"])
    if band_xyxy is None:
        logger_uma.debug("[failure] band collapsed for failure calculation")
        return -1

    x1, y1, x2, y2 = band_xyxy
    band_bgr = frame_bgr[y1:y2, x1:x2]
    if band_bgr.size == 0:
        return -1

    # trim rounded edges; helps avoid the orange/blue pill border
    Wb = band_bgr.shape[1]
    cut = int(0.12 * Wb)
    if Wb > 2 * cut:
        band_bgr = band_bgr[:, cut : Wb - cut]

    # ---- OCR on COLOR (BGR) ----
    ocr_text_split = ocr.text(band_bgr, joiner="|").split("|")

    if len(ocr_text_split) > 1:
        if "%" in ocr_text_split[0]:
            swap = ocr_text_split[0]
            ocr_text_split[0] = ocr_text_split[1]
            ocr_text_split[1] = swap

        val = " ".join(ocr_text_split[1:])
    else:
        val = ocr_text_split[-1]

    val = (
        val.replace("%", "")
        .strip()
        .lower()
        .split("lure")[-1]
        .strip()
        .split("ure")[-1]
        .strip()
        .split("re")[-1]
        .strip()
        .split("e")[-1]
        .strip()
        .replace("f", "")
        .replace("failure", "")
    )
    if val == "":
        val = (
            " ".join(ocr_text_split)
            .replace("%", "")
            .strip()
            .lower()
            .split("lure")[-1]
            .strip()
            .split("ure")[-1]
            .strip()
            .split("re")[-1]
            .strip()
            .split("e")[-1]
            .strip()
            .replace("f", "")
            .replace("failure", "")
        )
    val = val.replace(" ", "")
    try:
        val = int(val)
        if val < 0 or val > 100:
            return -1
    except Exception as e:
        logger_uma.warning(f"Failure is not a number: {val}. {e}")
        return -1
    return val
