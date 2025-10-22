from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple, Union
import random

import cv2
import numpy as np
from PIL import Image

from core.perception.extractors.training_metrics import extract_failure_pct_for_tile
from core.perception.yolo.interface import IDetector
from core.settings import Settings
from core.types import DetectionDict
from core.utils.analyzers import analyze_support_crop
from core.utils.geometry import calculate_jitter
from core.utils.logger import logger_uma
from core.utils.support_matching import (
    get_card_priority,
    get_runtime_support_matcher,
    match_support_crop,
)
from typing import Any
from dataclasses import dataclass, asdict

# ---- knobs you may want to tweak later (kept here for clarity) ----
GREEDY_THRESHOLD = 2.5  # "pick immediately" threshold (if you use it)
HIGH_SV_THRESHOLD = 3.5  # when SV >= this, allow risk up to ×RISK_RELAX_FACTOR
RISK_RELAX_FACTOR = 1.5  # e.g., 20% -> 30% when SV is high

# Director scoring by bar color (latest rule you wrote)
DIRECTOR_SCORE_BY_COLOR = {
    "blue": 0.25,  # "blue or less"
    "green": 0.15,
    "orange": 0.10,
    "yellow": 0.00,  # max (or treat is_max as yellow)
    "max": 0.00,  # alias
}

# What counts as blue/green vs orange/max for the standard supports
BLUE_GREEN = {"blue", "green"}
ORANGE_MAX = {"orange", "yellow"}


@dataclass
class TileSV:
    tile_idx: int
    failure_pct: int
    risk_limit_pct: int
    allowed_by_risk: bool
    sv_total: float
    sv_by_type: Dict[str, float]
    greedy_hit: bool
    notes: List[str]

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # optional rounding/pretty-printing
        d["sv_total"] = float(f"{d['sv_total']:.2f}")
        d["sv_by_type"] = {k: float(f"{v:.2f}") for k, v in d["sv_by_type"].items()}
        return d


SUPPORT_NAMES = {
    "support_card",
    "support_card_rainbow",
    "support_etsuko",
    "support_director",
    "support_tazuna",
}

def _center(xyxy: Tuple[float, float, float, float]) -> Tuple[float, float]:
    x1, y1, x2, y2 = xyxy
    return (0.5 * (x1 + x2), 0.5 * (y1 + y2))


def _raised_training_ltr_index(
    parsed_objects_screen: List[Dict], tol_px: int = 3, tol_frac_h: float = 0.06
) -> Optional[int]:
    """
    Return the left-to-right index of the 'raised' training tile if one clearly stands out,
    else None. 'Raised' = top y noticeably smaller than the others.
    """
    btns = [d for d in parsed_objects_screen if d["name"] == "training_button"]
    if len(btns) < 2:
        return None

    tops = np.array([d["xyxy"][1] for d in btns], dtype=float)
    heights = np.array([d["xyxy"][3] - d["xyxy"][1] for d in btns], dtype=float)
    med_top = float(np.median(tops))
    min_top = float(np.min(tops))
    thr = max(float(tol_px), float(tol_frac_h) * float(np.median(heights)))

    if (med_top - min_top) > thr:
        xs = np.array([(d["xyxy"][0] + d["xyxy"][2]) * 0.5 for d in btns], dtype=float)
        ltr_idx = np.argsort(xs)
        btns_ltr = [btns[i] for i in ltr_idx]
        tops_ltr = [b["xyxy"][1] for b in btns_ltr]
        raised_idx_ltr = int(np.argmin(tops_ltr))
        return raised_idx_ltr

    return None


def _center_x(xyxy):
    x1, y1, x2, y2 = xyxy
    return 0.5 * (x1 + x2)


def scan_training_screen(
    ctrl,
    ocr,  # OCRInterface
    yolo_engine: IDetector,
    energy,
    *,
    pause_after_click_range: list = [0.3, 0.4],
    conf_support: float = 0.60,
) -> Tuple[List[Dict], Image.Image, List[DetectionDict]]:
    """
    Efficient scan:
      • One initial capture.
      • If a tile is already raised, harvest it first (no click).
      • Then click each remaining tile exactly once; after each click:
          - recapture once,
          - refresh button geometry (LTR),
          - collect supports present in that capture (they belong to the raised tile),
          - extract failure%.
    Returns: (training_state, last_img, last_parsed)
    """
    # -------- detector params --------
    param_imgsz = 832
    param_conf = 0.60  # lower than 0.8 so we don't miss support cards
    param_iou = 0.45

    # -------- helpers --------
    def _center_x(xyxy):
        x1, _, x2, _ = xyxy
        return 0.5 * (x1 + x2)

    def _get_buttons_ltr(parsed_objs: List[Dict]) -> List[Dict]:
        btns = [d for d in parsed_objs if d["name"] == "training_button"]
        btns.sort(key=lambda d: _center_x(d["xyxy"]))
        return btns

    def _raised_training_ltr_index(
        parsed: List[Dict], tol_px: int = 3, tol_frac_h: float = 0.06
    ) -> Optional[int]:
        btns = [d for d in parsed if d["name"] == "training_button"]
        if len(btns) < 2:
            return None
        tops = np.array([d["xyxy"][1] for d in btns], dtype=float)
        heights = np.array([d["xyxy"][3] - d["xyxy"][1] for d in btns], dtype=float)
        med_top = float(np.median(tops))
        min_top = float(np.min(tops))
        thr = max(float(tol_px), float(tol_frac_h) * float(np.median(heights)))
        if (med_top - min_top) > thr:
            xs = np.array(
                [(d["xyxy"][0] + d["xyxy"][2]) * 0.5 for d in btns], dtype=float
            )
            order = np.argsort(xs)
            btns_ltr = [btns[i] for i in order]
            tops_ltr = [b["xyxy"][1] for b in btns_ltr]
            return int(np.argmin(tops_ltr))
        return None

    def _jitter_delay():
        if pause_after_click_range and len(pause_after_click_range) >= 2:
            a, b = float(pause_after_click_range[0]), float(pause_after_click_range[1])
            lo, hi = (a, b) if a <= b else (b, a)
            return max(0.0, random.uniform(lo, hi))
        return 0.6

    def _reindex_left_to_right(rows: List[Dict]) -> List[Dict]:
        """
        Normalize logical tile indices by current on-screen geometry to avoid
        duplicating 'last raised' tiles (e.g., WIT) due to timing/animation.
        """
        # Sort by X and assign 0..N-1 as canonical indices
        rows_sorted = sorted(rows, key=lambda r: float(r.get("tile_center_x", 0.0)))
        for j, r in enumerate(rows_sorted):
            r["tile_idx"] = j
        return rows_sorted

    def _collect_supports_enriched(
        cur_img: Image.Image, cur_parsed: List[Dict]
    ) -> Tuple[List[Dict], bool]:
        """
        Take *all* supports visible in this capture — they correspond to the currently raised tile.
        Enrich each with bar/type pieces, hint, rainbow, etc.
        """
        frame_bgr = cv2.cvtColor(np.array(cur_img), cv2.COLOR_RGB2BGR)

        # --- helpers: IoU + NMS ---
        def _area(xyxy):
            x1, y1, x2, y2 = [float(v) for v in xyxy]
            return max(0.0, x2 - x1) * max(0.0, y2 - y1)

        def _iou(a, b):
            ax1, ay1, ax2, ay2 = [float(v) for v in a]
            bx1, by1, bx2, by2 = [float(v) for v in b]
            ix1, iy1 = max(ax1, bx1), max(ay1, by1)
            ix2, iy2 = min(ax2, bx2), min(ay2, by2)
            iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
            inter = iw * ih
            if inter <= 0.0:
                return 0.0
            ua = _area(a) + _area(b) - inter
            return inter / ua if ua > 0 else 0.0

        def _nms_by_iou(dets, iou_thr=0.50):
            """
            Class-agnostic NMS: keep highest-conf per overlap cluster.
            Each det: {"xyxy":[...], "conf":float, "name":str, ...}
            """
            if not dets:
                return dets
            # sort by confidence DESC (missing conf -> 0.0)
            ordered = sorted(
                dets, key=lambda d: float(d.get("conf", 0.0)), reverse=True
            )
            kept = []
            for d in ordered:
                dx = d.get("xyxy")
                if not dx:
                    continue
                drop = False
                for k in kept:
                    if _iou(dx, k.get("xyxy")) >= iou_thr:
                        drop = True
                        break
                if not drop:
                    kept.append(d)
            return kept

        # Raw supports filtered by confidence
        supports_raw = [
            d
            for d in cur_parsed
            if d["name"] in SUPPORT_NAMES and d.get("conf", 0.0) >= conf_support
        ]
        # De-duplicate overlaps (e.g., double rainbow hits)
        supports = _nms_by_iou(supports_raw, iou_thr=0.50)
        parts_bar = [d for d in cur_parsed if d["name"] == "support_bar"]
        parts_type = [d for d in cur_parsed if d["name"] == "support_type"]

        def _inside(inner, outer, pad=2):
            ix1, iy1, ix2, iy2 = inner
            ox1, oy1, ox2, oy2 = outer
            return (
                ix1 >= ox1 - pad
                and iy1 >= oy1 - pad
                and ix2 <= ox2 + pad
                and iy2 <= oy2 + pad
            )

        min_confidence = 0.25
        matcher = get_runtime_support_matcher(min_confidence=min_confidence)  # TODO: performance issue if no custom hint in any, and if so we are recalculating?

        enriched: List[Dict] = []
        any_rainbow = False

        for s in supports:
            x1, y1, x2, y2 = [max(0, int(v)) for v in s["xyxy"]]
            crop = frame_bgr[y1:y2, x1:x2].copy()

            # parts within this support
            bar_xyxy = None
            type_xyxy = None
            for pb in parts_bar:
                bx1, by1, bx2, by2 = [int(v) for v in pb["xyxy"]]
                if _inside((bx1, by1, bx2, by2), (x1, y1, x2, y2), pad=1):
                    bar_xyxy = (bx1, by1, bx2, by2)
                    break
            for pt in parts_type:
                tx1, ty1, tx2, ty2 = [int(v) for v in pt["xyxy"]]
                if _inside((tx1, ty1, tx2, ty2), (x1, y1, x2, y2), pad=1):
                    type_xyxy = (tx1, ty1, tx2, ty2)
                    break

            bar_crop = (
                None
                if bar_xyxy is None
                else frame_bgr[
                    bar_xyxy[1] : bar_xyxy[3], bar_xyxy[0] : bar_xyxy[2]
                ].copy()
            )
            type_crop = (
                None
                if type_xyxy is None
                else frame_bgr[
                    type_xyxy[1] : type_xyxy[3], type_xyxy[0] : type_xyxy[2]
                ].copy()
            )

            attrs = analyze_support_crop(
                s["name"],
                crop,
                piece_bar_bgr=bar_crop,
                piece_type_bgr=type_crop,
            )

            has_rainbow = s["name"].endswith("_rainbow") or (
                s["name"] == "support_card_rainbow"
            )
            any_rainbow |= has_rainbow

            normalized_name = s["name"].replace("_rainbow", "")
            support_record: Dict[str, Any] = {
                **s,
                "name": normalized_name,
                "support_type": attrs["support_type"],
                "support_type_score": attrs["support_type_score"],
                "friendship_bar": attrs["friendship_bar"],
                "has_hint": attrs["has_hint"],
                "has_rainbow": bool(has_rainbow),
            }

            if matcher and attrs.get("has_hint"):
                match = match_support_crop(crop, matcher=matcher, min_confidence=min_confidence)
                if match:
                    name = match.get("name", "")
                    rarity = match.get("rarity", "")
                    attribute = match.get("attribute", "")

                    support_record["matched_card"] = match
                    support_record["priority_config"] = get_card_priority(
                        name,
                        rarity,
                        attribute,
                    )       

                    logger_uma.debug(
                        "[support_match] Hint support matched %s (%s/%s) score=%.3f",
                        name,
                        rarity,
                        attribute,
                        match.get("score", 0.0),
                    )
                else:
                    logger_uma.debug("[support_match] No confident match for hint support")

            enriched.append(support_record)

        return enriched, any_rainbow

    ENERGY_TO_IGNORE_FAILURE = 45

    def _failure_pct(cur_img, cur_parsed, tile_xyxy):
        if energy >= ENERGY_TO_IGNORE_FAILURE:
            return 0

        failure_predict = extract_failure_pct_for_tile(
            cur_img, cur_parsed, tile_xyxy, ocr
        )
        if failure_predict == -1:
            # try again
            time.sleep(0.2)
            failure_predict = extract_failure_pct_for_tile(
                cur_img, cur_parsed, tile_xyxy, ocr
            )

            if failure_predict == -1:
                failure_predict = Settings.MAX_FAILURE + 1

        return failure_predict

    # -------- 1) Initial capture, wait for button training animations --------
    time.sleep(0.3)
    cur_img, _, cur_parsed = yolo_engine.recognize(
        imgsz=param_imgsz, conf=param_conf, iou=param_iou, tag="training"
    )

    btns = _get_buttons_ltr(cur_parsed)

    if btns and len(btns) != 5:
        time.sleep(0.5)
        # try again
        cur_img, _, cur_parsed = yolo_engine.recognize(
            imgsz=param_imgsz, conf=param_conf, iou=param_iou, tag="training"
        )

        btns = _get_buttons_ltr(cur_parsed)
    if not btns:
        logger_uma.warning("No training buttons detected.")
        return [], cur_img, cur_parsed

    # Fixed LTR scaffold
    scan = [
        {
            "tile_idx": j,
            "tile_xyxy": btns[j]["xyxy"],
            "tile_center_x": float(_center_x(btns[j]["xyxy"])),
            "supports": [],
        }
        for j in range(len(btns))
    ]

    processed: set = set()
    results: List[Dict] = []

    # -------- 1.5) FAST_MODE: low-energy fast path (raised + WIT only) --------
    if (
        Settings.FAST_MODE
        and isinstance(energy, (int, float))
        and 0 <= int(energy) <= 35
    ):
        # Identify raised and WIT (last) indices
        ridx_fast = _raised_training_ltr_index(cur_parsed)
        last_idx = len(scan) - 1 if len(scan) > 0 else None
        wanted = []
        if ridx_fast is not None and 0 <= ridx_fast < len(scan):
            wanted.append(("raised", ridx_fast))
        if last_idx is not None and (ridx_fast is None or last_idx != ridx_fast):
            wanted.append(("wit", last_idx))

        for tag_kind, idx in wanted:
            tile = scan[idx]
            if tag_kind == "raised":
                supps, any_rainbow = _collect_supports_enriched(cur_img, cur_parsed)
                results.append(
                    {
                        **tile,
                        "supports": supps,
                        "has_any_rainbow": any_rainbow,
                        "failure_pct": _failure_pct(
                            cur_img, cur_parsed, tile["tile_xyxy"]
                        ),
                        "skipped_click": True,
                    }
                )
            else:
                # Click WIT (last) tile
                ctrl.click_xyxy_center(
                    tile["tile_xyxy"],
                    clicks=1,
                    jitter=calculate_jitter(tile["tile_xyxy"], percentage_offset=0.20),
                )
                time.sleep(_jitter_delay())
                cur_img, _, cur_parsed = yolo_engine.recognize(
                    imgsz=param_imgsz, conf=param_conf, iou=param_iou, tag="training"
                )
                # Refresh LTR geometry
                btns_now = [d for d in cur_parsed if d["name"] == "training_button"]
                btns_now.sort(key=lambda d: _center_x(d["xyxy"]))
                if len(btns_now) == len(scan):
                    for j, b in enumerate(btns_now):
                        scan[j]["tile_xyxy"] = b["xyxy"]
                        scan[j]["tile_center_x"] = float(_center_x(b["xyxy"]))
                # Determine effective raised after click
                ridx_now = _raised_training_ltr_index(cur_parsed)
                eff_idx = (
                    ridx_now
                    if (ridx_now is not None and 0 <= ridx_now < len(scan))
                    else idx
                )
                eff_tile = scan[eff_idx]
                supps, any_rainbow = _collect_supports_enriched(cur_img, cur_parsed)
                results.append(
                    {
                        **eff_tile,
                        "supports": supps,
                        "has_any_rainbow": any_rainbow,
                        "failure_pct": _failure_pct(
                            cur_img, cur_parsed, eff_tile["tile_xyxy"]
                        ),
                        "skipped_click": False,
                    }
                )

        # Normalize tile indices by current geometry to prevent duplicates
        results = _reindex_left_to_right(results)
        logger_uma.info(
            "FAST MODE: Only analyzing WIT; everything else may have high risk"
        )
        return results, cur_img, cur_parsed

    # -------- 2) Already-raised tile (no click) --------
    ridx = _raised_training_ltr_index(cur_parsed)
    if ridx is not None and 0 <= ridx < len(scan):
        tile = scan[ridx]
        supps, any_rainbow = _collect_supports_enriched(cur_img, cur_parsed)
        tile_record = {
            **tile,
            "supports": supps,
            "has_any_rainbow": any_rainbow,
            "failure_pct": _failure_pct(cur_img, cur_parsed, tile["tile_xyxy"]),
            "skipped_click": True,  # we did not click for the already-raised tile
        }
        results.append(tile_record)
        processed.add(ridx)

        # -------- FAST_MODE: Greedy short-circuit --------
        if Settings.FAST_MODE:
            try:
                # Compute SV for just this tile and check greedy
                sv_rows_one = compute_support_values([tile_record])
                if sv_rows_one and sv_rows_one[0].get("greedy_hit", False):
                    notes = sv_rows_one[-1].get("notes", "")
                    logger_uma.info(
                        f"FAST MODE: Found a greedy training option, not analizing nothing more. notes={notes}"
                    )
                    # Return results so far, don't waste time checking other options; caller will act immediately
                    return results, cur_img, cur_parsed
            except Exception as e:
                # Never break scanning on SV errors; just continue
                logger_uma.error(f"Error while checking FAST_MODE greedy SV: {e}")

    # -------- 3) Visit remaining tiles exactly once --------
    for idx in range(len(scan)):
        if idx in processed:
            continue

        tile = scan[idx]
        # Click to raise this tile
        ctrl.click_xyxy_center(
            tile["tile_xyxy"],
            clicks=1,
            jitter=calculate_jitter(tile["tile_xyxy"], percentage_offset=0.20),
        )

        time.sleep(_jitter_delay())

        # Recapture once
        cur_img, _, cur_parsed = yolo_engine.recognize(
            imgsz=param_imgsz, conf=param_conf, iou=param_iou, tag="training"
        )

        # Refresh geometry (LTR) to keep tile_xyxy up-to-date
        btns_now = _get_buttons_ltr(cur_parsed)
        if len(btns_now) == len(scan):
            for j, b in enumerate(btns_now):
                scan[j]["tile_xyxy"] = b["xyxy"]
                scan[j]["tile_center_x"] = float(_center_x(b["xyxy"]))
        else:
            logger_uma.warning(
                "Button count changed during scan: expected %d, got %d; keeping previous geometry",
                len(scan),
                len(btns_now),
            )

        # Whichever tile is raised after the click is the effective index
        ridx = _raised_training_ltr_index(cur_parsed)
        eff_idx = ridx if (ridx is not None and 0 <= ridx < len(scan)) else idx
        eff_tile = scan[eff_idx]

        supps, any_rainbow = _collect_supports_enriched(cur_img, cur_parsed)

        tile_record = {
            **eff_tile,
            "supports": supps,
            "has_any_rainbow": any_rainbow,
            "failure_pct": _failure_pct(cur_img, cur_parsed, eff_tile["tile_xyxy"]),
            "skipped_click": False,
        }
        results.append(tile_record)
        processed.add(eff_idx)

        # -------- FAST_MODE: Greedy short-circuit --------
        if Settings.FAST_MODE:
            try:
                # Compute SV for just this tile and check greedy
                sv_rows_one = compute_support_values([tile_record])
                if sv_rows_one and sv_rows_one[0].get("greedy_hit", False):
                    notes = sv_rows_one[-1].get("notes", "")
                    logger_uma.info(
                        f"FAST MODE: Found a greedy training option, not analizing nothing more. notes={notes}"
                    )
                    # Return results so far, don't waste time checking other options; caller will act immediately
                    return results, cur_img, cur_parsed
            except Exception as e:
                # Never break scanning on SV errors; just continue
                logger_uma.error(f"Error while checking FAST_MODE greedy SV: {e}")

    # Final normalization: enforce 0..N-1 by on-screen LTR to avoid duplicated WIT/GUTS
    results = _reindex_left_to_right(results)
    return results, cur_img, cur_parsed


def compute_support_values(training_state: List[Dict]) -> List[Dict[str, Any]]:
    """
    Compute Support Value (SV) per tile and apply the failure filtering rule.

    Inputs
    ------
    training_state : list[dict]
        Exactly the structure you pasted (each tile has 'supports', 'failure_pct', ...).

    Scoring Rules (as provided)
    ---------------------------
    • Each blue/green gauge support: +1  (per card)
    • If any blue/green support on the tile has a hint: +0.5 once (tile-capped) x2 if HINT_IS_IMPORTANT is True in Settings
    • Rainbow support (FT): +1 per rainbow card
      - Combo bonus: if >=2 rainbous, only add 0.5
    • Orange/Max gauge WITHOUT hint: +0  (no base)
      Orange/Max gauge WITH hint: +0.5 once (tile-capped, even if multiple)  x2 if HINT_IS_IMPORTANT is True in Settings
    • Reporter (support_etsuko): +0.1
    • Director (support_director): color-based
        blue: +0.25, green: +0.15, orange: +0.10, yellow/max: +0
    • Tazuna (support_tazuna): +0.15 (yellow, max). +1 (blue), +0.5 (green, orange)
    Failure rule
    ------------
    Let max_failure = BASE_MAX_FAILURE (20%) by default.
    - If SV < 3.5 → the tile must have failure_pct ≤ max_failure
    - If SV ≥ 3.5 → allow up to min(100, floor(max_failure * 1.5))

    Returns
    -------
    List[dict] with keys:
      - tile_idx, failure_pct, risk_limit_pct, allowed_by_risk
      - sv_total (float)
      - sv_by_type (dict[str,float])    # per support_type aggregation
      - greedy_hit (bool)               # SV ≥ GREEDY_THRESHOLD
      - notes (list[str])               # human-readable breakdown
    """
    out: List[TileSV] = []

    default_priority_cfg = Settings.default_support_priority()
    default_bluegreen_value = float(default_priority_cfg.get("scoreBlueGreen", 0.75))
    default_orange_value = float(default_priority_cfg.get("scoreOrangeMax", 0.5))

    def _support_label(support: Dict[str, Any]) -> str:
        matched = support.get("matched_card") or {}
        if isinstance(matched, dict) and matched.get("name"):
            name = str(matched.get("name", "")).strip()
            attr = str(matched.get("attribute", "")).strip()
            rarity = str(matched.get("rarity", "")).strip()
            suffix = " / ".join([p for p in (attr, rarity) if p])
            if suffix:
                return f"{name} ({suffix})"
            return name or "support"
        base = str(support.get("name", "support")).strip()
        return base or "support"

    def _hint_candidate_for_support(
        support: Dict[str, Any],
        *,
        color_key: str,
        default_value: float,
        color_desc: str,
    ) -> Tuple[float, Dict[str, Any]]:
        priority_cfg = support.get("priority_config")
        matched_card = support.get("matched_card")
        matched = isinstance(matched_card, dict) and bool(matched_card)
        if not isinstance(priority_cfg, dict):
            priority_cfg = default_priority_cfg
            matched = False
        enabled = bool(priority_cfg.get("enabled", True))
        label = _support_label(support)
        config_value = float(priority_cfg.get(color_key, default_value))
        base_value = config_value if matched else default_value
        important_mult = 3.0 if Settings.HINT_IS_IMPORTANT else 1.0
        effective_value = base_value * important_mult if enabled else 0.0
        meta = {
            "label": label,
            "color_desc": color_desc,
            "enabled": enabled,
            "matched": matched,
            "base_value": base_value,
            "important_mult": important_mult,
        }
        return effective_value, meta

    def _format_hint_note(meta: Dict[str, Any], bonus: float) -> str:
        label = meta["label"]
        color_desc = meta["color_desc"]
        base_value = meta["base_value"]
        source = "priority" if meta["matched"] else "default"
        important_mult = meta.get("important_mult", 1.0)
        note = f"Hint on {label} ({color_desc}): +{bonus:.2f} (base={base_value:.2f} {source}"
        if important_mult != 1.0:
            note += f", important×{important_mult:.1f}"
        note += ")"
        return note

    for tile in training_state:
        idx = int(tile.get("tile_idx", -1))
        failure_pct = int(tile.get("failure_pct", 0) or 0)
        supports = tile.get("supports", []) or []

        sv_total = 0.0
        sv_by_type: Dict[str, float] = {}
        notes: List[str] = []

        # Tile-level caps/flags
        blue_hint_candidates: List[Tuple[float, Dict[str, Any]]] = []
        orange_hint_candidates: List[Tuple[float, Dict[str, Any]]] = []
        hint_disabled_notes: List[str] = []

        # For rainbow combo computation (per type)
        rainbow_count = 0

        # ---- 1) per-support contributions ----
        for s in supports:
            sname = s.get("name", "")
            # stype = s.get("support_type", "unknown") or "unknown"
            bar = s.get("friendship_bar", {}) or {}
            color = str(bar.get("color", "unknown")).lower()
            is_max = bool(bar.get("is_max", False))
            has_hint = bool(s.get("has_hint", False))
            has_rainbow = bool(s.get("has_rainbow", False))
            label = _support_label(s)

            # Normalize 'max' color if flagged
            if is_max and color not in ("yellow", "max"):
                color = "yellow"

            # --- special cameos ---
            if sname == "support_etsuko":  # reporter
                sv_total += 0.1
                sv_by_type["special_reporter"] = (
                    sv_by_type.get("special_reporter", 0.0) + 0.1
                )
                notes.append(f"Reporter ({label}): +0.10")
                continue

            if sname == "support_director":
                # director score depends on color (blue/green/orange/yellow)
                score = DIRECTOR_SCORE_BY_COLOR.get(
                    color, DIRECTOR_SCORE_BY_COLOR.get("yellow", 0.0)
                )
                if score > 0:
                    sv_total += score
                    sv_by_type["special_director"] = (
                        sv_by_type.get("special_director", 0.0) + score
                    )
                    notes.append(f"Director ({label}, {color}): +{score:.2f}")
                else:
                    notes.append(f"Director ({label}, {color}): +0.00")
                continue

            if sname == "support_tazuna":
                # Tazuna score depends on color:
                if color in ("blue", "green"):
                    score = 1.0
                elif color in ("orange", ):
                    score = 0.5
                elif color in ("yellow",) or is_max:
                    score = 0.15
                else:
                    score = 0.0
                
                if score > 0:
                    sv_total += score
                    sv_by_type["special_tazuna"] = (
                        sv_by_type.get("special_tazuna", 0.0) + score
                    )
                    notes.append(f"Tazuna ({label}, {color}): +{score:.2f}")
                else:
                    notes.append(f"Tazuna ({label}, {color}): +0.00")
                continue

            # --- standard support cards (including rainbow variants) ---
            # Rainbow counts as +1 baseline
            if has_rainbow:
                sv_total += 1.0
                notes.append(f"rainbow ({label}): +1.00")
                rainbow_count = rainbow_count + 1
                # Rainbow hint does not add extra beyond standard tile-capped hint rules;
                # we still let hint rules below consider color buckets if needed.
                # (If you want rainbow to bypass color gates, keep as-is)

            # Blue/green baseline
            if color in BLUE_GREEN:
                sv_total += 1.0
                sv_by_type["cards"] = sv_by_type.get("cards", 0.0) + 1.0
                notes.append(f"{label} {color}: +1.00")
                if has_hint:
                    bonus, meta = _hint_candidate_for_support(
                        s,
                        color_key="scoreBlueGreen",
                        default_value=default_bluegreen_value,
                        color_desc="blue/green",
                    )
                    if not meta["enabled"]:
                        hint_disabled_notes.append(
                            f"Hint on {meta['label']} ({meta['color_desc']}): skipped (priority disabled)"
                        )
                    else:
                        blue_hint_candidates.append((bonus, meta))
            # Orange/Max baseline is 0; only hint may help (tile-capped)
            elif color in ORANGE_MAX or is_max:
                if has_hint:
                    bonus, meta = _hint_candidate_for_support(
                        s,
                        color_key="scoreOrangeMax",
                        default_value=default_orange_value,
                        color_desc="orange/max",
                    )
                    if not meta["enabled"]:
                        hint_disabled_notes.append(
                            f"Hint on {meta['label']} ({meta['color_desc']}): skipped (priority disabled)"
                        )
                    else:
                        orange_hint_candidates.append((bonus, meta))
                notes.append(f"{label} {color}: +0.00")
            else:
                notes.append(f"{label} {color}: +0.00 (unknown color category)")

        # ---- 2) tile-capped hint bonuses ----
        for disabled_note in hint_disabled_notes:
            notes.append(disabled_note)

        best_hint_value = 0.0
        best_hint_meta: Optional[Dict[str, Any]] = None

        if blue_hint_candidates:
            candidate_value, candidate_meta = max(
                blue_hint_candidates, key=lambda item: item[0]
            )
            if candidate_value > best_hint_value:
                best_hint_value = candidate_value
                best_hint_meta = {**candidate_meta, "bucket": "hint_bluegreen"}

        if orange_hint_candidates:
            candidate_value, candidate_meta = max(
                orange_hint_candidates, key=lambda item: item[0]
            )
            if candidate_value > best_hint_value:
                best_hint_value = candidate_value
                best_hint_meta = {**candidate_meta, "bucket": "hint_orange_max"}

        if best_hint_meta and best_hint_value > 0:
            bucket = str(best_hint_meta.get("bucket", "hint_bluegreen"))
            sv_total += best_hint_value
            sv_by_type[bucket] = sv_by_type.get(bucket, 0.0) + best_hint_value
            notes.append(_format_hint_note(best_hint_meta, best_hint_value))
        elif best_hint_meta:
            notes.append(_format_hint_note(best_hint_meta, best_hint_value))

        # ---- 3) rainbow combo bonus (per type) ----

        if rainbow_count >= 2:
            # +0.5 for each *type* that has ≥2 rainbow cards
            combo_bonus = 0.5
            sv_total += combo_bonus
            sv_by_type["rainbow_combo"] = (
                sv_by_type.get("rainbow_combo", 0.0) + combo_bonus
            )
            notes.append(f"Rainbow combo +{combo_bonus}")

        # ---- risk gating with dynamic relax based on SV ----
        base_limit = Settings.MAX_FAILURE
        # Piecewise multiplier:
        #   SV ≥ 4.0 → x2.0
        #   SV > 3.0 → x1.5
        #   SV ≥ 2.5 → x1.25
        #   else     → x1.0

        has_hint = bool(blue_hint_candidates or orange_hint_candidates)
        if sv_total >= 5:
            risk_mult = 2.0
        elif sv_total >= 3.5 and not (has_hint and Settings.HINT_IS_IMPORTANT):
            # cap if hint is overcalculating
            risk_mult = 2.0
        elif sv_total >= 2.75 and not (has_hint and Settings.HINT_IS_IMPORTANT):
            # cap if hint is overcalculating
            risk_mult = 1.5
        elif sv_total >= 2.25:
            risk_mult = 1.25
        else:
            risk_mult = 1.0

        risk_limit = int(min(100, base_limit * risk_mult))
        allowed = failure_pct <= risk_limit
        notes.append(
            f"Dynamic risk: SV={sv_total:.2f} → base {base_limit}% × {risk_mult:.2f} = {risk_limit}%"
        )

        # ---- 5) greedy mark (optional early exit logic can use this) ----
        greedy_hit = (sv_total >= GREEDY_THRESHOLD) and allowed
        if greedy_hit:
            notes.append(
                f"Greedy hit: SV {sv_total:.2f} ≥ {GREEDY_THRESHOLD} and failure {failure_pct}% ≤ {risk_limit}%"
            )

        out.append(
            TileSV(
                tile_idx=idx,
                failure_pct=failure_pct,
                risk_limit_pct=risk_limit,
                allowed_by_risk=bool(allowed),
                sv_total=float(sv_total),
                sv_by_type=sv_by_type,
                greedy_hit=greedy_hit,
                notes=notes,
            )
        )

    # Return simple dicts for convenience in notebooks / JSON
    return [t.as_dict() for t in out]
