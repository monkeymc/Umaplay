# core/perception/analyzers/energy_bar.py
from __future__ import annotations

from typing import Dict

import cv2
import numpy as np
from PIL import Image


def energy_from_bar_crop(pil_img: Image.Image) -> Dict[str, object]:
    """
    Estimate energy fill from a cropped 'ui_energy' bar *including* the white inner ring.
    Automatically locates the bar's interior (colored+gray) and computes the fill ratio.

    Returns a dict with:
        energy_ratio: float in [0,1]
        energy_pct:   int in [0,100]
        gray_ratio:   float in [0,1]
        valid:        bool
        reason:       str|None
        x1_content:   int
        x2_content:   int
        cut_x:        int
        inner_shape:  (W,H)
    """
    bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    H, W = bgr.shape[:2]
    if H < 10 or W < 20:
        return {
            "energy_ratio": 0.0,
            "energy_pct": 0,
            "gray_ratio": 1.0,
            "valid": False,
            "reason": "too-small",
            "inner_shape": (W, H),
        }

    # 1) Trim top/bottom white rings only
    pad_y = max(2, int(round(0.18 * H)))
    y1, y2 = pad_y, H - pad_y
    inner = bgr[y1:y2, :]
    if inner.size == 0:
        return {
            "energy_ratio": 0.0,
            "energy_pct": 0,
            "gray_ratio": 1.0,
            "valid": False,
            "reason": "inner-crop-empty",
            "inner_shape": (0, 0),
        }

    # 2) HSV masks
    hsv = cv2.cvtColor(inner, cv2.COLOR_BGR2HSV)
    S, V = hsv[..., 1], hsv[..., 2]
    colored_mask = (S >= 70) & (V >= 60)  # blue→green→yellow gradient
    grayish_mask = (S <= 60) & (V >= 70) & (V <= 200)
    white_mask = (S <= 50) & (V >= 200)
    dark_mask = V <= 60

    content_mask = (colored_mask | grayish_mask) & (~white_mask) & (~dark_mask)

    # Small horizontal smoothing
    kx = max(3, int(round(inner.shape[0] * 0.12)))
    kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (kx, 1))
    content_bin = content_mask.astype(np.uint8) * 255
    content_bin = cv2.morphologyEx(content_bin, cv2.MORPH_CLOSE, kernel_h)
    content_bin = content_bin > 0

    # 3) Longest run of content columns
    col_content = content_bin.mean(axis=0)
    content_cols = col_content >= 0.5

    def longest_true_run(mask_1d: np.ndarray):
        best_len = 0
        best_rng = (0, 0)
        cur_len = 0
        start = 0
        for i, v in enumerate(mask_1d.tolist() + [False]):  # sentinel
            if v:
                if cur_len == 0:
                    start = i
                cur_len += 1
            else:
                if cur_len > best_len:
                    best_len = cur_len
                    best_rng = (start, i)  # [start, i)
                cur_len = 0
        return best_rng

    x1c, x2c = longest_true_run(content_cols)
    if x2c - x1c < max(10, int(0.3 * W)):
        return {
            "energy_ratio": 0.0,
            "energy_pct": 0,
            "gray_ratio": 1.0,
            "valid": False,
            "reason": "content-not-found",
            "x1_content": x1c,
            "x2_content": x2c,
            "inner_shape": (inner.shape[1], inner.shape[0]),
        }

    # Restrict to interior band
    band_hsv = hsv[:, x1c:x2c]
    band_S, band_V = band_hsv[..., 1], band_hsv[..., 2]
    band_colored = (band_S >= 70) & (band_V >= 60)

    band_bin = band_colored.astype(np.uint8) * 255
    band_bin = cv2.morphologyEx(band_bin, cv2.MORPH_CLOSE, kernel_h)
    band_colored = band_bin > 0

    # 4) Fill by column majority
    col_frac_colored = band_colored.mean(axis=0)
    colored_major = col_frac_colored >= 0.5
    filled_cols = int(colored_major.sum())
    total_cols = max(1, colored_major.size)
    energy_ratio = filled_cols / total_cols
    gray_ratio = 1.0 - energy_ratio
    energy_pct = int(round(energy_ratio * 100.0))

    # cut position
    if filled_cols > 0:
        cm = np.asarray(colored_major, dtype=bool)

        if cm.size == 0:
            # No columns to consider; pick left as a sane default
            cut_x = x1c
        elif cm.all():
            # All colored → rightmost inner column
            cut_x = x1c + total_cols - 1  # == (x2c - 1) if total_cols == x2c - x1c
        elif cm.any():
            # At least one colored → take the last True
            last_true_local = int(np.flatnonzero(cm)[-1])  # 0-based offset from x1c
            cut_x = x1c + last_true_local
        else:
            # No colored at all (defensive; depends on what filled_cols means)
            cut_x = x1c
    else:
        cut_x = x1c

    out = {
        "energy_ratio": float(energy_ratio),
        "energy_pct": int(energy_pct),
        "gray_ratio": float(gray_ratio),
        "valid": True,
        "reason": None,
        "x1_content": int(x1c),
        "x2_content": int(x2c),
        "cut_x": int(cut_x),
        "inner_shape": (inner.shape[1], inner.shape[0]),
    }

    return out
