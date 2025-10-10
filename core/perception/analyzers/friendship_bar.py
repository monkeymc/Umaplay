# -*- coding: utf-8 -*-
from dataclasses import dataclass
from typing import Tuple, Dict, Optional
import os
import cv2
import numpy as np


@dataclass
class FBAConfig:
    # --- ROI: bottom-anchored search window on the card crop ---
    roi_height_frac: float = 0.18  # look at the bottom 18% of the card
    x_pad_frac: float = 0.02  # horizontal padding inside the crop (each side)

    # Bar strip taken from the ROI (no contouring by default)
    min_bar_height_frac: float = 0.55  # bar strip is at least 55% of ROI height
    hpad_frac: float = 0.03  # extra horizontal pad applied to the bar strip
    cap_ignore_frac: float = (
        0.12  # ignore rightmost gray “cap” when measuring color/fill
    )

    # Pixel gates
    colored_S_min: int = 60  # pixels with S>=, V>= are considered “colored” (not gray)
    colored_V_min: int = 80
    gray_S_max: int = 35  # (unused for voting; kept for completeness)
    gray_V_lo: int = 30
    gray_V_hi: int = 120

    # Progress (column-wise) computation
    col_majority_threshold: float = (
        0.40  # a column counts as filled if >=40% colored pixels
    )

    # HSV hue centers (OpenCV 0..179; real degrees/2)
    # Your HSB spec: blue ≈198°, green ≈80°, orange ≈38°, yellow ≈51°
    blue_h_center: int = 198 // 2  # 99
    green_h_center: int = 80 // 2  # 40
    orange_h_center: int = 38 // 2  # 19
    yellow_band: Tuple[int, int] = (51 // 2 - 3, 51 // 2 + 3)  # (22, 30) approx

    # Band width for color voting and decision margin
    h_tolerance: int = 12  # ± hue window for blue/green/orange
    vote_margin: float = 0.03  # top1 − top2 coverage must exceed this to be decisive
    min_color_cover: float = (
        0.05  # require at least 5% area for a color to be considered
    )

    # MAX classification rules
    max_yellow_cover: float = 0.55  # if yellow area ≥ 55% of strip → MAX
    max_if_yellow_full: float = 0.85  # OR if fill ≥ 85% and yellowish present → MAX

    # Fill-ratio fallback thresholds (if vote is ambiguous)
    blue_hi: float = 0.60  # <0.60 → blue
    green_hi: float = 0.80  # <0.80 → green, else orange
    min_colored_cover_for_fill: float = 0.02  # if below → treat as empty/blue


class FriendshipBarAnalyzer:
    """
    Analyze a support-card crop (BGR) and return:
      - roi_xyxy: chosen ROI on the card (where the bar lives)
      - bar_xyxy: exact bar-strip inside that ROI (bottom-anchored, padded)
      - color:    one of {'blue','green','orange','yellow'}
      - progress_pct, fill_ratio: estimated progress
      - is_max:   True if the bar is the MAX (yellow) state
      - quality:  auxiliary scores for debugging
    """

    def __init__(self, cfg: Optional[FBAConfig] = None):
        self.cfg = cfg or FBAConfig()

    @staticmethod
    def _to_hsv(bgr: np.ndarray) -> np.ndarray:
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

    @staticmethod
    def _ensure_dir(path: str) -> None:
        os.makedirs(path, exist_ok=True)

    def _bottom_roi_xyxy(self, card: np.ndarray) -> Tuple[int, int, int, int]:
        H, W = card.shape[:2]
        h = max(1, int(self.cfg.roi_height_frac * H))
        y1 = max(0, H - h)
        y2 = H
        x1 = int(self.cfg.x_pad_frac * W)
        x2 = int((1.0 - self.cfg.x_pad_frac) * W)
        return x1, y1, x2, y2

    def _bar_strip_xyxy(
        self, roi_xyxy: Tuple[int, int, int, int]
    ) -> Tuple[int, int, int, int]:
        # Take a bottom-anchored strip of the ROI with guaranteed minimum thickness,
        # then add a small horizontal padding.
        x1r, y1r, x2r, y2r = roi_xyxy
        roi_h = y2r - y1r
        roi_w = x2r - x1r
        min_h = max(2, int(self.cfg.min_bar_height_frac * roi_h))
        by2 = y2r
        by1 = max(y1r, by2 - min_h)

        hpad = int(self.cfg.hpad_frac * roi_w)
        bx1 = max(x1r, x1r - 0 + hpad)  # left pad inside ROI
        bx2 = min(x2r, x2r + 0 - hpad)  # right pad inside ROI
        return bx1, by1, bx2, by2

    @staticmethod
    def _circular_hue_distance(h: np.ndarray, center: int) -> np.ndarray:
        d = np.abs(h.astype(np.int16) - int(center))
        return np.minimum(d, 180 - d)

    def _vote_dominant_color(
        self, hsv: np.ndarray, drop_right_cols: int
    ) -> Dict[str, float]:
        """Return fractional cover for each of {blue, green, orange, yellow} inside `hsv`."""
        H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
        if drop_right_cols > 0:
            H = H[:, :-drop_right_cols]
            S = S[:, :-drop_right_cols]
            V = V[:, :-drop_right_cols]

        colored = (S >= self.cfg.colored_S_min) & (V >= self.cfg.colored_V_min)
        total = max(1, int(np.count_nonzero(colored)))

        # Yellow band (for MAX)
        y0, y1 = self.cfg.yellow_band
        yellow_mask = colored & (H >= y0) & (H <= y1)
        yellow_cover = float(np.count_nonzero(yellow_mask)) / total

        # Blue/green/orange bands by circular distance
        tol = self.cfg.h_tolerance
        blue_mask = colored & (
            self._circular_hue_distance(H, self.cfg.blue_h_center) <= tol
        )
        green_mask = colored & (
            self._circular_hue_distance(H, self.cfg.green_h_center) <= tol
        )
        orange_mask = colored & (
            self._circular_hue_distance(H, self.cfg.orange_h_center) <= tol
        )

        covers = {
            "blue": float(np.count_nonzero(blue_mask)) / total,
            "green": float(np.count_nonzero(green_mask)) / total,
            "orange": float(np.count_nonzero(orange_mask)) / total,
            "yellow": yellow_cover,
            "colored_cover": float(total)
            / max(1, H.size),  # overall fraction of colored pixels
        }
        return covers

    def _progress_from_columns(self, colored_mask: np.ndarray) -> float:
        """Column-major progress: fraction of columns whose colored ratio ≥ threshold."""
        if colored_mask.size == 0:
            return 0.0
        col_frac = colored_mask.mean(axis=0)  # [W]
        filled_cols = (col_frac >= self.cfg.col_majority_threshold).sum()
        return float(filled_cols) / float(col_frac.size)

    # -----------------------------
    # Public API
    # -----------------------------
    def analyze(self, card_bgr: np.ndarray) -> Dict:
        # 1) ROI & bar strip localization (pure geometry, no contours)
        x1r, y1r, x2r, y2r = self._bottom_roi_xyxy(card_bgr)
        bx1, by1, bx2, by2 = self._bar_strip_xyxy((x1r, y1r, x2r, y2r))

        roi = card_bgr[y1r:y2r, x1r:x2r]
        bar = card_bgr[by1:by2, bx1:bx2]
        if roi.size == 0 or bar.size == 0:
            return {
                "roi_xyxy": (x1r, y1r, x2r, y2r),
                "bar_xyxy": (bx1, by1, bx2, by2),
                "progress_pct": 0,
                "fill_ratio": 0.0,
                "color": "blue",
                "is_max": False,
                "quality": {"found": False},
            }

        # small safety: drop the right gray cap from evaluation
        drop_cols = int(self.cfg.cap_ignore_frac * bar.shape[1])
        hsv = self._to_hsv(bar)
        _, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]

        # 2) voting for dominant color (blue/green/orange/yellow)
        covers = self._vote_dominant_color(hsv, drop_right_cols=drop_cols)
        colored_mask = (S[:, : bar.shape[1] - drop_cols] >= self.cfg.colored_S_min) & (
            V[:, : bar.shape[1] - drop_cols] >= self.cfg.colored_V_min
        )

        # 3) progress estimate from columns (uses the same colored mask)
        fill_ratio = self._progress_from_columns(colored_mask)
        progress_pct = int(round(fill_ratio * 100.0))

        # 4) MAX (yellow) check first
        is_max = (covers["yellow"] >= self.cfg.max_yellow_cover) or (
            fill_ratio >= self.cfg.max_if_yellow_full and covers["yellow"] > 0.0
        )

        # 5) choose color:
        if is_max:
            color_state = "yellow"
            progress_pct = max(progress_pct, 100)
            fill_ratio = max(fill_ratio, 1.0)
        else:
            # majority vote among blue/green/orange
            trio = {k: covers[k] for k in ("blue", "green", "orange")}
            top = sorted(trio.items(), key=lambda kv: kv[1], reverse=True)
            (c1, v1), (_, v2) = top[0], top[1]

            decisive = (v1 >= self.cfg.min_color_cover) and (
                (v1 - v2) >= self.cfg.vote_margin
            )

            if decisive:
                color_state = c1
            else:
                # fallback to fill-ratio thresholds
                if covers["colored_cover"] < self.cfg.min_colored_cover_for_fill:
                    color_state = "blue"
                    fill_ratio = 0.0
                    progress_pct = 0
                elif fill_ratio < self.cfg.blue_hi:
                    color_state = "blue"
                elif fill_ratio < self.cfg.green_hi:
                    color_state = "green"
                else:
                    color_state = "orange"

        return {
            "roi_xyxy": (x1r, y1r, x2r, y2r),
            "bar_xyxy": (bx1, by1, bx2, by2),
            "progress_pct": int(progress_pct),
            "fill_ratio": float(fill_ratio),
            "color": color_state,
            "is_max": bool(is_max),
            "quality": {
                "colored_cover": float(covers["colored_cover"]),
                "vote_blue": float(covers["blue"]),
                "vote_green": float(covers["green"]),
                "vote_orange": float(covers["orange"]),
                "vote_yellow": float(covers["yellow"]),
            },
        }

    def analyze_strip(self, bar_bgr: np.ndarray) -> Dict:
        if bar_bgr is None or bar_bgr.size == 0:
            return {
                "progress_pct": 0,
                "fill_ratio": 0.0,
                "color": "blue",
                "is_max": False,
                "quality": {"found": False},
            }

        cfg = self.cfg
        hsv = self._to_hsv(bar_bgr)

        # small safety: drop right “cap”
        drop_cols = int(cfg.cap_ignore_frac * bar_bgr.shape[1])
        _, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
        covers = self._vote_dominant_color(hsv, drop_right_cols=drop_cols)
        colored_mask = (S[:, : bar_bgr.shape[1] - drop_cols] >= cfg.colored_S_min) & (
            V[:, : bar_bgr.shape[1] - drop_cols] >= cfg.colored_V_min
        )

        fill_ratio = self._progress_from_columns(colored_mask)
        progress_pct = int(round(fill_ratio * 100.0))

        is_max = (covers["yellow"] >= cfg.max_yellow_cover) or (
            fill_ratio >= cfg.max_if_yellow_full and covers["yellow"] > 0.0
        )

        if is_max:
            color_state = "yellow"
            progress_pct = max(progress_pct, 100)
            fill_ratio = max(fill_ratio, 1.0)
        else:
            trio = {k: covers[k] for k in ("blue", "green", "orange")}
            top = sorted(trio.items(), key=lambda kv: kv[1], reverse=True)
            (c1, v1), (_, v2) = top[0], top[1]
            decisive = (v1 >= cfg.min_color_cover) and ((v1 - v2) >= cfg.vote_margin)
            if decisive:
                color_state = c1
            else:
                if covers["colored_cover"] < cfg.min_colored_cover_for_fill:
                    color_state = "blue"
                    fill_ratio = 0.0
                    progress_pct = 0
                elif fill_ratio < cfg.blue_hi:
                    color_state = "blue"
                elif fill_ratio < cfg.green_hi:
                    color_state = "green"
                else:
                    color_state = "orange"

        return {
            "progress_pct": int(progress_pct),
            "fill_ratio": float(fill_ratio),
            "color": color_state,
            "is_max": bool(is_max),
            "quality": {"colored_cover": float(covers["colored_cover"])},
        }
