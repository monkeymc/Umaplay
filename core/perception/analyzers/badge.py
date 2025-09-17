
from typing import Tuple

import cv2
import numpy as np
from PIL import Image

from core.perception.ocr.interface import OCRInterface
from core.types import XYXY
from core.utils.geometry import crop_pil
from core.utils.text import fuzzy_ratio


BADGE_PRIORITY = {"EX": 5, "G1": 4, "G2": 3, "G3": 2, "OP": 1, "UNK": 0}
BADGE_PRIORITY_REVERSE = {5: "EX", 4: "G1", 3: "G2", 2: "G3", 1: "OP", 0: "UNK"}

def _badge_label_by_ocr(ocr: OCRInterface, img: Image.Image, xyxy: XYXY) -> Tuple[str, float]:
    txt = ocr.text(crop_pil(img, xyxy, pad=0)).upper()
    cand = ["G1", "G2", "G3", "OP", "EX"]
    best, sc = "", 0.0
    for c in cand:
        r = fuzzy_ratio(txt, c)
        if r > sc:
            best, sc = c, r
    return (best if sc >= 0.60 else "UNK", sc)

def _badge_label_by_color(img: Image.Image, xyxy: XYXY) -> Tuple[str, float]:
    """Color fallback using hue medians on colored pixels."""
    x1, y1, x2, y2 = map(int, xyxy)
    crop = np.array(img.crop((x1, y1, x2, y2)))
    if crop.size == 0:
        return "UNK", 0.0
    bgr = cv2.cvtColor(crop, cv2.COLOR_RGB2BGR)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    H, S, V = hsv[...,0], hsv[...,1], hsv[...,2]
    colored = (S >= 80) & (V >= 80)
    if not np.any(colored):
        return "UNK", 0.0
    h = H[colored].astype(np.float32)
    # circular mean
    ang = h * (np.pi / 90.0)
    mu = np.mean(np.exp(1j * ang))
    med = (np.angle(mu) % (2*np.pi)) * 90.0 / np.pi  # 0..179
    # reference centers in OpenCV hue (deg/2)
    centers = {
        "G1": 212/2,   # blue
        "G2": 343/2,   # magenta/pink
        "G3": 140/2,   # green-ish ~70
        "OP":  40/2,   # orange
        "EX":  36/2,   # gold (close to OP)
    }
    def circ_dist(a, b):
        d = abs(a-b) 
        return min(d, 180-d)
    best_lab, best_d = "UNK", 999.0
    for lab, c in centers.items():
        d = circ_dist(med, c)
        if d < best_d:
            best_d, best_lab = d, lab
    # OP vs EX are very close; keep as OP by default unless very near EX
    if best_lab in ("OP","EX"):
        if best_d <= 6:
            pass
        else:
            best_lab = "OP"
    score = max(0.0, 1.0 - best_d/90.0)
    return best_lab, score

def _badge_label(ocr, img: Image.Image, xyxy: XYXY) -> str:
    """
badge_g1 -> HSB=212, 77, 89 / RGB=52, 133, 227
badge_g2 -> HSB=36, 100, 81 / RGB=206, 125, 0
badge_g3 -> HSB=343, 63, 96 / RGB=244, 90, 134
badge_op -> HSB=40, 95, 100 / RGB=255, 173, 12
badge_ex -> HSB=36, 100, 81 / RGB=206, 125, 0
    """
    lab, _ = _badge_label_by_color(img, xyxy)
    if lab != "UNK":
        return lab

    lab2, sc = _badge_label_by_ocr(ocr, img, xyxy)
    return lab2