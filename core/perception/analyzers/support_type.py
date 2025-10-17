import os
from typing import Dict, Tuple, Optional
from dataclasses import dataclass

import cv2
import numpy as np


# ---------- small helpers ----------
def _to_hsv(bgr: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)


def _edge_im(gray_or_mask: np.ndarray) -> np.ndarray:
    g = cv2.GaussianBlur(gray_or_mask, (3, 3), 0)
    return cv2.Canny(g, 40, 120)


def _white_glyph_mask(hsv: np.ndarray, s_max=80, v_min=180) -> np.ndarray:
    # "white-ish" parts (the glyph itself). Be permissive on S, strict on V.
    S, V = hsv[..., 1], hsv[..., 2]
    return ((S <= s_max) & (V >= v_min)).astype(np.uint8) * 255


def _color_mask(hsv: np.ndarray, s_min=70, v_min=90) -> np.ndarray:
    # "colored" parts (tile background) for hue estimation / sanity checks
    S, V = hsv[..., 1], hsv[..., 2]
    return ((S >= s_min) & (V >= v_min)).astype(np.uint8) * 255


def _circ_med(h: np.ndarray) -> Optional[float]:
    if h.size == 0:
        return None
    ang = h.astype(np.float32) * (np.pi / 90.0)  # 180 -> 2π
    v = np.exp(1j * ang)
    mu = np.mean(v)
    if np.abs(mu) < 1e-6:
        return float(np.median(h))
    a = np.angle(mu)
    if a < 0:
        a += 2 * np.pi
    return float(a * 90.0 / np.pi)  # back to [0..179]


def _circ_dist(h1: float, h2: float) -> float:
    d = abs(h1 - h2)
    return min(d, 180.0 - d)


# ---------- template bundle ----------
@dataclass
class _Template:
    key: str  # 'spd','sta','pwr','guts','wit','friend'
    glyph_edge: np.ndarray  # edges of white glyph mask
    hue_med: Optional[float]  # median hue of the colored tile in the icon


class FixedRoiTypeClassifier:
    """
    Classifies the support-card type symbol using a fixed top-left ROI + glyph-edge template matching.
    """

    def __init__(self, icons_dir: str):
        self.fmap: Dict[str, str] = {
            "SPD": "support_card_type_spd.png",
            "STA": "support_card_type_sta.png",
            "PWR": "support_card_type_pwr.png",
            "GUTS": "support_card_type_guts.png",
            "WIT": "support_card_type_wit.png",
            "FRIEND": "support_card_type_friend.png",
        }
        self.templates: Dict[str, _Template] = {}
        self._load_templates(icons_dir)

        # Matching knobs
        self.accept_thresh = 0.38  # accept TM_CCOEFF_NORMED >= this
        self.template_scales = [0.6, 0.75, 0.9, 1.0, 1.2, 1.4]  # scale template to ROI
        self.pad_frac = 0.02  # small padding around ROI
        self.debug = False

    def _load_templates(self, icons_dir: str):
        for key, fn in self.fmap.items():
            key = key.upper()
            p = os.path.join(icons_dir, fn)
            icon = cv2.imread(p, cv2.IMREAD_UNCHANGED)
            if icon is None:
                raise FileNotFoundError(f"Missing template: {p}")

            # Composite over white if alpha present
            if icon.shape[2] == 4:
                a = icon[..., 3:4].astype(np.float32) / 255.0
                bgr = (icon[..., :3].astype(np.float32) * a + 255.0 * (1.0 - a)).astype(
                    np.uint8
                )
            else:
                bgr = icon[..., :3]

            hsv = _to_hsv(bgr)
            # white glyph from template
            glyph_mask = _white_glyph_mask(hsv, s_max=80, v_min=180)
            if cv2.countNonZero(glyph_mask) < 10:
                # fallback: use edges of whole icon if mask is too small
                glyph_edge = _edge_im(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))
            else:
                glyph_edge = _edge_im(glyph_mask)

            # hue median from colored part (for soft fallback)
            color_mask = _color_mask(hsv, s_min=70, v_min=90)
            H = hsv[..., 0]
            hue_med = (
                _circ_med(H[color_mask > 0]) if cv2.countNonZero(color_mask) else None
            )

            self.templates[key] = _Template(key, glyph_edge, hue_med)

    # ----- fixed ROI in top-left quadrant -----
    def _fixed_roi(self, card_bgr: np.ndarray) -> Tuple[int, int, int, int]:
        H, W = card_bgr.shape[:2]
        # first quadrant with a bit of margin: x∈[2%, 48%], y∈[2%, 48%]
        px = int(self.pad_frac * W)
        py = int(self.pad_frac * H)
        x1, y1 = px, py
        x2, y2 = int(0.48 * W), int(0.48 * H)
        return x1, y1, x2, y2

    # ----- nearest-by-hue among *templates* (soft fallback) -----
    def _fallback_from_hue(self, roi_bgr: np.ndarray) -> Optional[str]:
        hsv = _to_hsv(roi_bgr)
        cmask = _color_mask(hsv, s_min=70, v_min=90)
        if cv2.countNonZero(cmask) == 0:
            return None
        h_med = _circ_med(hsv[..., 0][cmask > 0])
        if h_med is None:
            return None
        bestk, bestd = None, 999
        for k, t in self.templates.items():
            if t.hue_med is None:
                continue
            d = _circ_dist(h_med, t.hue_med)
            if d < bestd:
                bestd, bestk = d, k
        return bestk

    def classify(self, card_bgr: np.ndarray) -> Dict:
        """
        Color-only support-type classifier with robust STA vs GUTS disambiguation.

        Strategy:
        1) Take a fixed top-left ROI of the card.
        2) Keep only colored pixels (S,V high).
        3) Vote by hue-band coverage for {SPD,WIT,PWR,STA,GUTS}.
        4) If STA vs GUTS is close/ambiguous, tie-break with Lab 'b' channel:
            - red (STA) → more yellowish → higher b
            - magenta (GUTS) → more bluish → lower b
        5) Confidence combines hue distance to the reference center and coverage.
        """
        # ---------- ROI ----------
        x1, y1, x2, y2 = self._fixed_roi(card_bgr)
        roi = card_bgr[y1:y2, x1:x2]
        if roi.size == 0:
            return {
                "type": "unknown",
                "score": 0.0,
                "roi_xyxy": (x1, y1, x2, y2),
                "hue_med": None,
                "coverage": 0.0,
            }

        # ---------- HSV + colored mask ----------
        hsv = _to_hsv(roi)
        Hh, Ss, Vv = hsv[..., 0], hsv[..., 1], hsv[..., 2]
        colored = (Ss >= 70) & (Vv >= 80)  # keep badge background, drop white glyph
        n_colored = int(colored.sum())
        coverage = n_colored / float(max(1, roi.shape[0] * roi.shape[1]))
        if n_colored < 10:
            return {
                "type": "unknown",
                "score": 0.0,
                "roi_xyxy": (x1, y1, x2, y2),
                "hue_med": None,
                "coverage": float(coverage),
            }

        # robust circular median hue for diagnostics / distance scoring
        hue_med = _circ_med(Hh[colored])

        # ---------- Hue bands (OpenCV hue 0..179) ----------
        # Reference centers (HSB/2):
        REF = {
            "SPD": 202 // 2,  # ~101 (blue)
            "STA": 7 // 2,  # ~3   (red)
            "PWR": 38 // 2,  # ~19  (orange)
            "GUTS": 337 // 2,  # ~168 (pink/magenta)
            "WIT": 163 // 2,  # ~82  (green/teal)
        }

        # Band definitions: slightly narrower for STA vs GUTS so they don't overlap.
        # STA spans around 0 with wrap; GUTS stays in magenta range.
        BANDS = {
            "SPD": [(REF["SPD"] - 12, REF["SPD"] + 12)],
            "WIT": [(REF["WIT"] - 12, REF["WIT"] + 12)],
            "PWR": [(REF["PWR"] - 12, REF["PWR"] + 12)],
            "STA": [(0, 10), (170, 179)],  # tight red
            "GUTS": [(158, 176)],  # magenta / pink
        }

        def _band_mask(H, band):
            lo, hi = int(band[0]) % 180, int(band[1]) % 180
            if lo <= hi:
                return (H >= lo) & (H <= hi)
            else:
                return (H >= lo) | (H <= hi)

        total_col = max(1, n_colored)
        cov = {}
        for k, bands in BANDS.items():
            m = np.zeros_like(Hh, dtype=bool)
            for bd in bands:
                m |= _band_mask(Hh, bd)
            cov[k] = float(np.count_nonzero(m & colored)) / float(total_col)

        # ---------- Primary vote ----------
        order = sorted(cov.items(), key=lambda kv: kv[1], reverse=True)
        top_type, top_cover = order[0]
        second_type, second_cover = order[1]

        # ---------- STA vs GUTS tie-breaker ----------
        # If winner is one of {STA,GUTS} or they are close, use Lab 'b' channel.
        close_margin = 0.05
        if (top_type in ("STA", "GUTS")) or (
            cov["STA"] > 0 and abs(cov["STA"] - cov["GUTS"]) < close_margin
        ):
            # compute Lab 'b' for colored pixels (OpenCV Lab has b∈[0..255], 128 neutral)
            lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB)
            b_chan = lab[..., 2]
            if n_colored > 0:
                mean_b = float(b_chan[colored].mean())
            else:
                mean_b = 128.0

            # Thresholds: >135 → yellowish (red/STA), <121 → bluish (magenta/GUTS).
            # Between them, keep the hue vote result.
            if mean_b >= 135.0:
                top_type = "STA"
            elif mean_b <= 121.0:
                top_type = "GUTS"
            else:
                # Keep the previous vote but nudge if very close:
                if cov["GUTS"] - cov["STA"] > 0.01:
                    top_type = "GUTS"
                elif cov["STA"] - cov["GUTS"] > 0.01:
                    top_type = "STA"
                # else leave as-is

            # Adjust cover we use for confidence if tie-broken
            top_cover = max(cov[top_type], top_cover)

        # ---------- Confidence score ----------
        # Combine hue distance to the reference center (where available) and coverage.
        def _circ_dist_scalar(a, b):
            return min(abs(a - b), 180.0 - abs(a - b))

        max_tol = 18.0  # ~±36° in real hue
        if hue_med is None:
            hue_score = 0.0
        else:
            ref_h = REF[top_type] if top_type in REF else None
            if ref_h is None:
                hue_score = 0.0
            else:
                d = _circ_dist_scalar(float(hue_med), float(ref_h))
                hue_score = max(0.0, min(1.0, 1.0 - d / max_tol))

        # Weight hue closeness and band coverage (tweak weights if you like)
        score = 0.6 * hue_score + 0.4 * float(top_cover)
        # Penalize very low overall colored coverage
        if coverage < 0.02:
            score *= 0.5

        out_type = top_type if score >= 0.30 else "unknown"

        return {
            "type": out_type,
            "score": float(score),
            "roi_xyxy": (x1, y1, x2, y2),
            "hue_med": float(hue_med) if hue_med is not None else None,
            "coverage": float(coverage),
        }
