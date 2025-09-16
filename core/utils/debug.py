# core/utils/debug.py
from __future__ import annotations
import os, time
from typing import Optional, Union
import numpy as np
from PIL import Image, Image as PILImage
from core.utils.logger import logger_uma

import re
from typing import Dict, List, Optional, Tuple

import cv2

from core.utils.logger import logger_uma

def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def dump_image(img: Union[Image.Image, np.ndarray],
               filename: Optional[str] = None,
               folder: str = "debug") -> str:
    """
    Save a PIL.Image (or numpy array) into the debug folder.
    Returns the absolute path saved.
    """
    _ensure_dir(folder)
    ts = time.strftime("%Y%m%d-%H%M%S")
    if filename is None:
        name = f"frame_{ts}.png"
    else:
        name = f"{filename}_{ts}.png"

    if not name.lower().endswith(".png"):
        name += ".png"
    path = os.path.join(folder, name)

    if isinstance(img, Image.Image):
        img.save(path)
    else:
        # assume RGB ndarray; if BGR you can convert before calling
        PILImage.fromarray(img).save(path)

    logger_uma.debug(f"dumped image -> {os.path.abspath(path)}")
    return os.path.abspath(path)

def _to_bgr(pil_img: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

def _draw_xyxy_bgr(bgr: np.ndarray, xyxy: Tuple[int,int,int,int], color=(0,255,255), thickness=2):
    x1,y1,x2,y2 = [int(v) for v in xyxy]
    cv2.rectangle(bgr, (x1,y1), (x2,y2), color, thickness)

def _first_training_button_ltr(parsed_objects_screen: List[Dict]) -> Optional[Dict]:
    btns = [d for d in parsed_objects_screen if d["name"] == "training_button"]
    if not btns:
        return None
    btns = sorted(btns, key=lambda d: (d["xyxy"][0] + d["xyxy"][2]) * 0.5)  # left->right
    return btns[0]

def _find_obj(parsed_objects_screen: List[Dict], name: str) -> Optional[Dict]:
    cand = [d for d in parsed_objects_screen if d["name"] == name]
    if not cand:
        return None
    cand.sort(key=lambda d: d["conf"], reverse=True)
    return cand[0]


def debug_failure_pct_on_first_tile(ctrl, detect_objects_single, ocr, pause_after_click=0.22):
    """
    Clicks the leftmost training button, crops the failure bubble ROI, shows debug images,
    and prints OCR results. Returns the parsed integer (or -1).
    """
    # 0) capture & detect
    game_img, _, parsed_objects_screen = detect_objects_single(ctrl)

    # 1) leftmost training button
    tb = _first_training_button_ltr(parsed_objects_screen)
    if tb is None:
        logger_uma.info("No training_button found.")
        return -1

    # 2) click its center to raise the bubble (jittered)
    ctrl.click_xyxy_center(tb["xyxy"], clicks=1, jitter=2)
    import time as _t; _t.sleep(pause_after_click)

    # 3) re-capture & re-detect
    game_img2, _, parsed_objects_screen2 = detect_objects_single(ctrl)
    bgr = _to_bgr(game_img2)

    # 4) anchor with stats
    stats = _find_obj(parsed_objects_screen2, "ui_stats")
    if stats is None:
        logger_uma.info("ui_stats not found; cannot anchor failure ROI.")
        return -1

    tb2 = _first_training_button_ltr(parsed_objects_screen2)
    if tb2 is None:
        logger_uma.info("training_button not found after click.")
        return -1

    x1,y1,x2,y2 = tb2["xyxy"]
    xs1, ys1, xs2, ys2 = stats["xyxy"]

    # ROI as before
    pad_x = max(2, int(0.02 * (x2 - x1)))
    roi_x1 = max(0, int(x1) + pad_x)
    roi_x2 = min(bgr.shape[1], int(x2) - pad_x)
    pad_above = 2
    pad_below = 2
    roi_y1 = max(0, int(ys2) + pad_above)
    roi_y2 = max(roi_y1 + 2, int(y1) - pad_below)
    if roi_y2 - roi_y1 < 14:
        roi_y1 = max(0, int(y1) - 48)
        roi_y2 = int(y1) - 2

    roi = (roi_x1, roi_y1, roi_x2, roi_y2)
    crop = bgr[roi_y1:roi_y2, roi_x1:roi_x2].copy()

    # Viz
    try:
        from IPython.display import display
        from PIL import Image as PILImage
        vis = bgr.copy()
        _draw_xyxy_bgr(vis, tb2["xyxy"], (0,255,0), 2)
        _draw_xyxy_bgr(vis, stats["xyxy"], (255,0,0), 2)
        _draw_xyxy_bgr(vis, roi, (0,255,255), 2)
        display(PILImage.fromarray(cv2.cvtColor(vis, cv2.COLOR_BGR2RGB)))
        display(PILImage.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)))
    except Exception:
        pass

    # light preprocessing
    if crop.size == 0:
        logger_uma.info("ROI empty.")
        return -1

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    scale = 2
    gray_big = cv2.resize(gray, (gray.shape[1]*scale, gray.shape[0]*scale), interpolation=cv2.INTER_CUBIC)
    _, th = cv2.threshold(gray_big, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    th_inv = cv2.bitwise_not(th)

    # Try OCR on a couple variants (keep behavior)
    try:
        txt_raw  = ocr.text(Image.fromarray(cv2.cvtColor(gray_big, cv2.COLOR_GRAY2RGB)))
    except Exception:
        txt_raw = ""
    try:
        txt_bin  = ocr.text(Image.fromarray(cv2.cvtColor(th_inv,   cv2.COLOR_GRAY2RGB)))
    except Exception:
        txt_bin = ""
    try:
        dig_bin  = ocr.digits(Image.fromarray(cv2.cvtColor(th_inv, cv2.COLOR_GRAY2RGB)))
    except Exception:
        dig_bin = ""

    logger_uma.info("[OCR] raw:   %r", txt_raw)
    logger_uma.info("[OCR] bin:   %r", txt_bin)
    logger_uma.info("[OCR] digits(th_inv): %s", dig_bin)

    # parse %
    def _parse_pct(*candidates: str) -> int:
        for s in candidates:
            if not s:
                continue
            m = re.search(r"(\d{1,3})", s)
            if m:
                v = int(m.group(1))
                if 0 <= v <= 100:
                    return v
        return -1

    pct = _parse_pct(txt_bin, txt_raw, str(dig_bin))
    logger_uma.info("→ Parsed failure %% = %s", pct)
    return pct
