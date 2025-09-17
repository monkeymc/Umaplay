# core/perception/analyzers.py
from __future__ import annotations

import os
from typing import Dict, Optional

import numpy as np

from core.perception.analyzers.friendship_bar import FBAConfig, FriendshipBarAnalyzer
from core.perception.analyzers.hint import HintConfig, HintDetector
from core.perception.analyzers.support_type import FixedRoiTypeClassifier
from core.utils.logger import logger_uma

try:
    from core.settings import ASSETS_DIR

    ICONS_DIR = os.path.join(ASSETS_DIR, "icons")
except Exception:
    ICONS_DIR = "assets/icons"

# --- Singletons (initialized once) -------------------------------------------
type_clf = FixedRoiTypeClassifier(ICONS_DIR)

fba = FriendshipBarAnalyzer(
    FBAConfig(
        roi_height_frac=0.18,
        h_tolerance=12,
        vote_margin=0.03,
    )
)

hint_det = HintDetector(
    HintConfig(
        x_lo=0.60,
        x_hi=1.00,
        y_lo=0.00,
        y_hi=0.40,
        h_tol_strict=8,
        h_tol_wide=16,
        s_min_strict=140,
        v_min_strict=140,
        s_min_wide=100,
        v_min_wide=110,
        min_coverage_frac=0.25,
        min_purity=0.60,
    )
)


def analyze_support_crop(
    class_name,
    bgr: np.ndarray,
    *,
    piece_bar_bgr: Optional[np.ndarray] = None,
    piece_type_bgr: Optional[np.ndarray] = None,
) -> Dict:
    """
    Run support-type, friendship-bar, and hint analyzers on a single crop (BGR).
    Returns a dict with the same shape you already used.
    """
    out = {
        "support_type": "unknown",
        "support_type_score": 0.0,
        "friendship_bar": {
            "color": "unknown",
            "progress_pct": 0,
            "fill_ratio": 0.0,
            "is_max": False,
        },
        "has_hint": False,
    }

    # cv2.imwrite("test2.png", piece_bar_bgr) to see images
    # support type (prefer YOLO 'support_type' crop if provided)
    try:
        if "director" in class_name or "etsuko" in class_name:
            t = {"type": "ACADEMY", "score": 1}
        else:
            t = type_clf.classify(piece_type_bgr if piece_type_bgr is not None else bgr)

        out["support_type"] = t.get("type", "unknown")
        out["support_type_score"] = float(t.get("score", 0.0))
    except Exception as e:
        logger_uma.debug("support_type classify error: %s", e)

    # friendship bar (prefer YOLO 'support_bar' strip if provided)
    try:
        if piece_bar_bgr is not None:
            fb = fba.analyze_strip(piece_bar_bgr)
        else:
            fb = fba.analyze(bgr)
        out["friendship_bar"] = {
            "color": fb["color"],
            "progress_pct": int(fb["progress_pct"]),
            "fill_ratio": float(fb["fill_ratio"]),
            "is_max": bool(fb["is_max"]),
        }
    except Exception as e:
        logger_uma.debug("friendship_bar analyze error: %s", e)

    # hint
    try:
        hd = hint_det.analyze(bgr)
        out["has_hint"] = bool(hd["has_hint"])
    except Exception as e:
        logger_uma.debug("hint analyze error: %s", e)

    return out
