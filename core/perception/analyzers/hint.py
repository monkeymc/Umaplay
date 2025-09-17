# -*- coding: utf-8 -*-
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
import numpy as np
import cv2


@dataclass
class HintConfig:
    # ROI (fractions of the card crop)
    x_lo: float = 0.60
    x_hi: float = 0.985
    y_lo: float = 0.00
    y_hi: float = 0.40

    # Target pink color: HSB ~ (339, 71, 100)  → OpenCV HSV (H in 0..179, S,V in 0..255)
    hint_h_center: int = 170  # ≈ 339° / 2
    h_tol_strict: int = 8  # narrow band for high precision
    h_tol_wide: int = 16  # wider band for purity check
    s_min_strict: int = 140  # be strict on saturation/value to avoid skin/orange
    v_min_strict: int = 140
    s_min_wide: int = 100
    v_min_wide: int = 110

    # Morphology
    morph_frac: float = 0.02  # kernel radius = morph_frac * min(W,H)

    # Decision thresholds
    min_coverage_frac: float = 0.25  # strict pink coverage in ROI (area ratio)
    min_purity: float = 0.65  # strict_pixels / wide_pixels  (color purity)
    min_cc_area_frac: float = 0.01  # (optional) largest CC area over ROI area for viz


class HintDetector:
    def __init__(self, cfg: Optional[HintConfig] = None):
        self.cfg = cfg or HintConfig()

    @staticmethod
    def _to_hsv(bgr: np.ndarray) -> np.ndarray:
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

    def _roi_xyxy(self, card: np.ndarray) -> Tuple[int, int, int, int]:
        H, W = card.shape[:2]
        x1 = int(round(self.cfg.x_lo * W))
        x2 = int(round(self.cfg.x_hi * W))
        y1 = int(round(self.cfg.y_lo * H))
        y2 = int(round(self.cfg.y_hi * H))
        # clamp and guarantee non-empty
        x1 = np.clip(x1, 0, max(W - 1, 0))
        x2 = np.clip(x2, 1, W)
        y1 = np.clip(y1, 0, max(H - 1, 0))
        y2 = np.clip(y2, 1, H)
        if x2 <= x1:
            x2 = min(W, x1 + 1)
        if y2 <= y1:
            y2 = min(H, y1 + 1)
        return x1, y1, x2, y2

    @staticmethod
    def _h_in_band(h: np.ndarray, center: int, tol: int) -> np.ndarray:
        # hue wrap-around
        lo = (center - tol) % 180
        hi = (center + tol) % 180
        if lo <= hi:
            return (h >= lo) & (h <= hi)
        else:
            return (h >= lo) | (h <= hi)

    def _clean(self, mask: np.ndarray, W: int, H: int) -> np.ndarray:
        k = max(1, int(round(self.cfg.morph_frac * min(W, H))))
        ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1))
        m = cv2.morphologyEx(mask, cv2.MORPH_OPEN, ker)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, ker)
        return m

    def analyze(self, card_bgr: np.ndarray) -> Dict:
        cfg = self.cfg

        # 1) crop ROI
        rx1, ry1, rx2, ry2 = self._roi_xyxy(card_bgr)
        roi = card_bgr[ry1:ry2, rx1:rx2]
        Hroi, Wroi = roi.shape[:2]
        area_roi = float(max(1, Hroi * Wroi))

        if roi.size == 0:
            return {
                "roi_xyxy_local": (rx1, ry1, rx2, ry2),
                "hint_xyxy_local": None,
                "has_hint": False,
                "score": 0.0,
                "coverage": 0.0,
                "purity": 0.0,
            }

        hsv = self._to_hsv(roi)
        h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]

        # 2) strict + wide pink masks
        h_strict = self._h_in_band(h, cfg.hint_h_center, cfg.h_tol_strict)
        h_wide = self._h_in_band(h, cfg.hint_h_center, cfg.h_tol_wide)

        strict = (h_strict & (s >= cfg.s_min_strict) & (v >= cfg.v_min_strict)).astype(
            np.uint8
        ) * 255
        wide = (h_wide & (s >= cfg.s_min_wide) & (v >= cfg.v_min_wide)).astype(
            np.uint8
        ) * 255

        strict = self._clean(strict, Wroi, Hroi)
        wide = self._clean(wide, Wroi, Hroi)

        # 3) coverage & purity gates
        n_strict = int(np.count_nonzero(strict))
        n_wide = int(np.count_nonzero(wide))

        coverage = n_strict / area_roi
        purity = n_strict / max(1.0, n_wide)  # ∈ (0..1]

        if (coverage < cfg.min_coverage_frac) or (purity < cfg.min_purity):
            return {
                "roi_xyxy_local": (rx1, ry1, rx2, ry2),
                "hint_xyxy_local": None,
                "has_hint": False,
                "score": float(coverage),
                "coverage": float(coverage),
                "purity": float(purity),
            }

        # 4) (viz) largest connected component in strict mask
        num, lbl, stats, _ = cv2.connectedComponentsWithStats(strict, connectivity=8)
        if num <= 1:
            hint_box = None
        else:
            idx = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])  # skip bg=0
            x, y, w, h = map(int, stats[idx][:4])
            # optional tiny-area filter just for nicer boxes (won't change has_hint)
            if (w * h) / area_roi < cfg.min_cc_area_frac:
                hint_box = None
            else:
                hint_box = (rx1 + x, ry1 + y, rx1 + x + w, ry1 + y + h)

        return {
            "roi_xyxy_local": (rx1, ry1, rx2, ry2),
            "hint_xyxy_local": hint_box,
            "has_hint": True,
            "score": float(coverage),  # keep your print format
            "coverage": float(coverage),
            "purity": float(purity),
        }
