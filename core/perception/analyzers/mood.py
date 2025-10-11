# core/perception/analyzers/mood.py
from __future__ import annotations

from typing import Dict, Tuple

import cv2
import numpy as np
from PIL import Image

from core.perception.ocr.interface import OCRInterface
from core.types import XYXY
from core.utils.geometry import crop_pil
from core.utils.text import fuzzy_ratio


# Public labels and (optional) priority if you ever need ranking
MOOD_LABELS = ("AWFUL", "BAD", "NORMAL", "GOOD", "GREAT")
MOOD_PRIORITY: Dict[str, int] = {
    "AWFUL": 0,
    "BAD": 1,
    "NORMAL": 2,
    "GOOD": 3,
    "GREAT": 4,
}

# Reference HSB centers you provided (deg). We convert to OpenCV hue units (deg/2).
# AWFUL -> HSB: 276, 34, 71.  RGB=157,120,182  (purple)
# BAD   -> HSB: 198, 73, 89.  RGB=62,179,228   (cyan/blue)
# NORMAL-> HSB: 49,  84, 97.  RGB=247,210,39   (yellow)
# GOOD  -> HSB: 19,  71, 97.  RGB=248,127,72   (orange)
# GREAT -> HSB: 339, 62, 91.  RGB=232,88,139   (magenta/pink)
_HUE_CENTERS_DEG = {
    "AWFUL": 276.0,
    "BAD": 198.0,
    "NORMAL": 49.0,
    "GOOD": 19.0,
    "GREAT": 339.0,
}
_HUE_CENTERS = {k: v / 2.0 for k, v in _HUE_CENTERS_DEG.items()}  # OpenCV: 0..179


def _circ_dist(a: float, b: float) -> float:
    """Shortest circular distance on [0,180) hue wheel."""
    d = abs(a - b)
    return min(d, 180.0 - d)


def _robust_hue_from_crop(img: Image.Image, xyxy: XYXY) -> Tuple[float, float]:
    """
    Returns (median_hue, quality_score in [0,1]) from the cropped mood pill.
    Uses a forgiving saturation/value mask to handle AWFUL (low-S purple) as well.
    """
    x1, y1, x2, y2 = map(int, xyxy)
    crop = np.array(img.crop((x1, y1, x2, y2)))
    if crop.size == 0:
        return -1.0, 0.0

    bgr = cv2.cvtColor(crop, cv2.COLOR_RGB2BGR)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    H, S, V = hsv[..., 0].astype(np.float32), hsv[..., 1], hsv[..., 2]

    # Primary mask: colorful & bright enough
    mask = (S >= 30) & (V >= 60)

    # If too few pixels (thin white edges / glare), relax mask a bit
    if np.count_nonzero(mask) < 100:
        mask = (S >= 15) & (V >= 50)

    if not np.any(mask):
        return -1.0, 0.0

    # Weighted circular mean to reduce gradient noise
    # Weight by saturation to emphasize colored pixels
    h = H[mask]
    s = S[mask].astype(np.float32) / 255.0
    ang = h * (np.pi / 90.0)
    w = s.clip(0.1, 1.0)  # avoid zero weights
    mu = np.sum(w * np.exp(1j * ang)) / (np.sum(w) + 1e-6)
    med = (np.angle(mu) % (2 * np.pi)) * 90.0 / np.pi  # back to 0..179

    # A crude quality proxy: concentration of the resultant vector
    quality = float(np.abs(mu))  # 0..1: 1 means very concentrated hue

    return float(med), float(quality)


def mood_label_by_color(img: Image.Image, xyxy: XYXY) -> Tuple[str, float]:
    """
    Color-first mood classifier. Returns (label, confidence_score [0..1]).
    If the crop is empty or not colorful enough → ("UNK", 0.0).
    """
    hue, q = _robust_hue_from_crop(img, xyxy)
    if hue < 0.0:
        return "UNK", 0.0

    # Find closest mood center on hue wheel
    best_lab, best_d = "UNK", 999.0
    for lab, c in _HUE_CENTERS.items():
        d = _circ_dist(hue, c)
        if d < best_d:
            best_d, best_lab = d, lab

    # Combine angular closeness and hue concentration into a score
    # (when best_d == 0 and q == 1 -> score ≈ 1)
    # 90 is half the hue circle, like your badge scorer.
    conf = max(0.0, (1.0 - best_d / 90.0)) * (0.5 + 0.5 * q)

    # Mild safeguard: if the hue is very far from any center, mark as unknown
    if conf < 0.30:
        return "UNK", conf

    return best_lab, conf


def mood_label_by_ocr(
    ocr: OCRInterface, img: Image.Image, xyxy: XYXY
) -> Tuple[str, float]:
    """
    OCR fallback. Returns (label, fuzzy_score).
    """
    crop = crop_pil(img, xyxy, pad=0)
    txt = (ocr.text(crop) or "").upper()

    best, sc = "UNK", 0.0
    for k in MOOD_LABELS:
        r = fuzzy_ratio(txt, k)
        if r > sc:
            best, sc = k, r
    return (best if sc >= 0.60 else "UNK", sc)


def mood_label(ocr: OCRInterface | None, img: Image.Image, xyxy: XYXY) -> str:
    """
    Unified mood classifier:
      1) Try color.
      2) If unknown or low confidence, try OCR (if available).
    Returns "AWFUL"|"BAD"|"NORMAL"|"GOOD"|"GREAT" or "UNK".
    """
    lab, conf = mood_label_by_color(img, xyxy)
    if lab != "UNK":
        return lab

    if ocr is not None:
        lab2, _ = mood_label_by_ocr(ocr, img, xyxy)
        return lab2

    return "UNK"
