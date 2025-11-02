# -*- coding: utf-8 -*-
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple
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


@dataclass(frozen=True)
class SupportGeometry:
    key: int
    bbox: Tuple[int, int, int, int]
    width: int
    height: int
    center: Tuple[float, float]


def build_support_geometries(
    supports: Sequence[Dict[str, Any]]
) -> List[SupportGeometry]:
    geoms: List[SupportGeometry] = []
    for idx, det in enumerate(supports):
        xyxy = det.get("xyxy", (0, 0, 0, 0))
        sx1, sy1, sx2, sy2 = [max(0, int(v)) for v in xyxy]
        width = max(1, sx2 - sx1)
        height = max(1, sy2 - sy1)
        cx = 0.5 * (sx1 + sx2)
        cy = 0.5 * (sy1 + sy2)
        key = int(det.get("idx", idx))
        geoms.append(
            SupportGeometry(
                key=key,
                bbox=(sx1, sy1, sx2, sy2),
                width=width,
                height=height,
                center=(cx, cy),
            )
        )
    return geoms


def assign_hints_to_supports(
    support_geoms: Sequence[SupportGeometry],
    hints: Sequence[Dict[str, Any]],
    *,
    canvas_height: int,
    expand_x_frac: float = 0.35,
    expand_top_frac: float = 0.90,
    expand_bottom_frac: float = 0.25,
    max_score: float = 1.8,
) -> Tuple[Dict[int, List[Dict[str, Any]]], List[Dict[str, Any]]]:
    assignments: Dict[int, List[Dict[str, Any]]] = {
        geom.key: [] for geom in support_geoms
    }
    tile_hints: List[Dict[str, Any]] = []
    bottom_start = max(0, canvas_height - int(canvas_height * 0.25))

    anchor_x_lo = 0.60
    anchor_y_hi = 0.40
    bar_y_start = 0.70
    left_penalty_weight = 1.2
    bottom_penalty_weight = 1.5
    bar_surcharge = 0.35
    inside_bonus = 0.85
    margin_better = 0.12

    for hint in hints:
        hx1, hy1, hx2, hy2 = [float(v) for v in hint.get("xyxy", (0, 0, 0, 0))]
        hcx = 0.5 * (hx1 + hx2)
        hcy = 0.5 * (hy1 + hy2)
        hconf = float(hint.get("conf", 0.0))

        best_key: Optional[int] = None
        best_score = float("inf")
        best_geom: Optional[SupportGeometry] = None

        for geom in support_geoms:
            sx1, sy1, sx2, sy2 = geom.bbox
            width = float(geom.width)
            height = float(geom.height)

            expand_x = expand_x_frac * width
            expand_top = expand_top_frac * height
            expand_bottom = expand_bottom_frac * height

            ex1 = sx1 - expand_x
            ex2 = sx2 + expand_x
            ey1 = sy1 - expand_top
            ey2 = sy2 + expand_bottom

            if not (ex1 <= hcx <= ex2 and ey1 <= hcy <= ey2):
                continue

            rx = (hcx - sx1) / max(1.0, width)
            ry = (hcy - sy1) / max(1.0, height)

            dx = abs(hcx - geom.center[0]) / max(1.0, width)
            if hcy < sy1:
                dy = (sy1 - hcy) / max(1.0, height)
            elif hcy <= sy2:
                dy = 0.0
            else:
                dy = (hcy - sy2) / max(1.0, height)

            score = dx + 0.6 * dy

            if rx < anchor_x_lo:
                score += (anchor_x_lo - rx) * left_penalty_weight

            if ry > anchor_y_hi:
                score += (ry - anchor_y_hi) * bottom_penalty_weight
                if ry >= bar_y_start:
                    score += bar_surcharge

            inside = sx1 <= hcx <= sx2 and sy1 <= hcy <= sy2
            if inside:
                score *= inside_bonus

            if (best_key is None) or (score < best_score - margin_better):
                best_score = score
                best_key = geom.key
                best_geom = geom

        if not support_geoms:
            tile_hints.append(
                {
                    "conf": hconf,
                    "xyxy": (hx1, hy1, hx2, hy2),
                    "center": (hcx, hcy),
                    "reason": "no_supports",
                }
            )
            continue

        if best_geom is None:
            best_geom = min(
                support_geoms,
                key=lambda g: abs(hcx - g.center[0]) + abs(hcy - g.center[1]),
            )
            best_key = best_geom.key
            best_score = float("inf")

        sx1, sy1, sx2, sy2 = best_geom.bbox
        width = float(best_geom.width)
        height = float(best_geom.height)

        horizontal_gap = abs(hcx - best_geom.center[0]) / max(1.0, width)
        if hcy < sy1:
            vertical_gap = (sy1 - hcy) / max(1.0, height)
        elif hcy <= sy2:
            vertical_gap = 0.0
        else:
            vertical_gap = (hcy - sy2) / max(1.0, height)

        is_bottom_region = max(hy1, hy2) >= bottom_start
        is_far_from_support = (
            vertical_gap >= 0.75
            or horizontal_gap >= 1.35
            or (is_bottom_region and vertical_gap >= 0.45)
        )

        if best_score <= max_score or not is_far_from_support:
            assignments.setdefault(best_key, []).append(
                {
                    "source": "yolo",
                    "conf": hconf,
                    "xyxy": (hx1, hy1, hx2, hy2),
                    "center": (hcx, hcy),
                    "score": float(best_score),
                    "fallback": bool(best_score > max_score),
                }
            )
        else:
            tile_hints.append(
                {
                    "conf": hconf,
                    "xyxy": (hx1, hy1, hx2, hy2),
                    "center": (hcx, hcy),
                    "reason": "far_from_support",
                }
            )

    return assignments, tile_hints
