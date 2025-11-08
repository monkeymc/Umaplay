
from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple, Union
import random

import numpy as np
from PIL import Image

from core.perception.yolo.interface import IDetector
from core.settings import Settings
from core.types import DetectionDict
from core.utils.geometry import calculate_jitter
from core.utils.logger import logger_uma
from core.utils.skill_memory import SkillMemoryManager
from typing import Any
from dataclasses import dataclass, asdict

from core.utils.training_check_helpers import (
    get_buttons_ltr,
    _center_x,
    raised_training_ltr_index,
    collect_supports_enriched,
    failure_pct,
    reindex_left_to_right
)
from core.scenarios.registry import registry

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


def get_compute_support_values():
    """Resolve the correct compute_support_values function based on active scenario."""
    compute_fn, _ = registry.resolve(Settings.ACTIVE_SCENARIO)
    return compute_fn


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

def scan_training_screen(
    ctrl,
    ocr,  # OCRInterface
    yolo_engine: IDetector,
    energy,
    *,
    pause_after_click_range: list = [0.3, 0.4],
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

    def _jitter_delay():
        if pause_after_click_range and len(pause_after_click_range) >= 2:
            a, b = float(pause_after_click_range[0]), float(pause_after_click_range[1])
            lo, hi = (a, b) if a <= b else (b, a)
            return max(0.0, random.uniform(lo, hi))
        return 0.6

    # -------- 1) Initial capture, wait for button training animations --------
    time.sleep(0.3)
    cur_img, _, cur_parsed = yolo_engine.recognize(
        imgsz=param_imgsz, conf=param_conf, iou=param_iou, tag="training"
    )

    btns = get_buttons_ltr(cur_parsed)

    if btns and len(btns) != 5:
        time.sleep(0.5)
        # try again
        cur_img, _, cur_parsed = yolo_engine.recognize(
            imgsz=param_imgsz, conf=param_conf, iou=param_iou, tag="training"
        )

        btns = get_buttons_ltr(cur_parsed)
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
        ridx_fast = raised_training_ltr_index(cur_parsed)
        last_idx = len(scan) - 1 if len(scan) > 0 else None
        wanted = []
        if ridx_fast is not None and 0 <= ridx_fast < len(scan):
            wanted.append(("raised", ridx_fast))
        if last_idx is not None and (ridx_fast is None or last_idx != ridx_fast):
            wanted.append(("wit", last_idx))

        for tag_kind, idx in wanted:
            tile = scan[idx]
            if tag_kind == "raised":
                supps, any_rainbow = collect_supports_enriched(cur_img, cur_parsed)
                results.append(
                    {
                        **tile,
                        "supports": supps,
                        "has_any_rainbow": any_rainbow,
                        "failure_pct": failure_pct(
                            cur_img, cur_parsed, tile["tile_xyxy"], energy, ocr
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
                ridx_now = raised_training_ltr_index(cur_parsed)
                eff_idx = (
                    ridx_now
                    if (ridx_now is not None and 0 <= ridx_now < len(scan))
                    else idx
                )
                eff_tile = scan[eff_idx]
                supps, any_rainbow = collect_supports_enriched(cur_img, cur_parsed)
                results.append(
                    {
                        **eff_tile,
                        "supports": supps,
                        "has_any_rainbow": any_rainbow,
                        "failure_pct": failure_pct(
                            cur_img, cur_parsed, eff_tile["tile_xyxy"], energy, ocr
                        ),
                        "skipped_click": False,
                    }
                )

        # Normalize tile indices by current geometry to prevent duplicates
        results = reindex_left_to_right(results)
        logger_uma.info(
            "FAST MODE: Only analyzing WIT; everything else may have high risk"
        )
        return results, cur_img, cur_parsed

    # -------- 2) Already-raised tile (no click) --------
    ridx = raised_training_ltr_index(cur_parsed)
    if ridx is not None and 0 <= ridx < len(scan):
        tile = scan[ridx]
        supps, any_rainbow = collect_supports_enriched(cur_img, cur_parsed)
        tile_record = {
            **tile,
            "supports": supps,
            "has_any_rainbow": any_rainbow,
            "failure_pct": failure_pct(cur_img, cur_parsed, tile["tile_xyxy"], energy, ocr),
            "skipped_click": True,  # we did not click for the already-raised tile
        }
        results.append(tile_record)
        processed.add(ridx)

        # -------- FAST_MODE: Greedy short-circuit --------
        if Settings.FAST_MODE:
            try:
                # Compute SV for just this tile and check greedy
                sv_rows_one = get_compute_support_values()([tile_record])
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
        btns_now = get_buttons_ltr(cur_parsed)
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
        ridx = raised_training_ltr_index(cur_parsed)
        eff_idx = ridx if (ridx is not None and 0 <= ridx < len(scan)) else idx
        eff_tile = scan[eff_idx]

        supps, any_rainbow = collect_supports_enriched(cur_img, cur_parsed)

        tile_record = {
            **eff_tile,
            "supports": supps,
            "has_any_rainbow": any_rainbow,
            "failure_pct": failure_pct(cur_img, cur_parsed, eff_tile["tile_xyxy"], energy, ocr),
            "skipped_click": False,
        }
        results.append(tile_record)
        processed.add(eff_idx)

        # -------- FAST_MODE: Greedy short-circuit --------
        if Settings.FAST_MODE:
            try:
                # Compute SV for just this tile and check greedy
                sv_rows_one = get_compute_support_values()([tile_record])
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
    results = reindex_left_to_right(results)
    return results, cur_img, cur_parsed
