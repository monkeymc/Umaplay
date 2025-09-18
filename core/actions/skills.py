# core/actions/skills.py
from __future__ import annotations

import random
import time
from typing import List, Optional, Sequence, Tuple
from collections import Counter
from PIL import Image

from core.controllers.android import ScrcpyController
from core.controllers.base import IController
from core.perception.yolo.interface import IDetector
from core.settings import Settings
from core.utils.logger import logger_uma
from core.utils.geometry import crop_pil
from core.utils.text import fuzzy_contains, fuzzy_ratio, fuzzy_best_match
from core.perception.is_button_active import ActiveButtonClassifier
from core.types import DetectionDict
from core.utils.yolo_objects import inside, yolo_signature


def _nearly_same(a: List[Tuple[str, int, int]], b: List[Tuple[str, int, int]]) -> bool:
    """
    Heuristic equivalence for scene signatures.
    Each signature item is (name, cx_bucket, cy_bucket). Two signatures are
    considered the same if:
      1) They have the same per-class counts (ignoring positions), and
      2) For every item in `a`, there exists an *unmatched* item in `b` with
         the same name and |dx|<=1 and |dy|<=1 bucket.
    This tolerates tiny shifts between frames (e.g., 8–16 px).
    """
    if len(a) != len(b):
        return False

    # Same counts per class?
    ca = Counter(n for n, _, _ in a)
    cb = Counter(n for n, _, _ in b)
    if ca != cb:
        return False

    TOL = 1  # buckets (each of your buckets is ~8 px)

    # Build per-class pools for B we can remove from as we match
    pools = {}
    for name, x, y in b:
        pools.setdefault(name, []).append([x, y])

    # Greedy matching with tolerance
    for name, ax, ay in a:
        pool = pools.get(name, [])
        match_idx = -1
        best_metric = None
        for j, (bx, by) in enumerate(pool):
            dx, dy = abs(ax - bx), abs(ay - by)
            if dx <= TOL and dy <= TOL:
                # prefer tighter matches (Chebyshev distance)
                m = max(dx, dy)
                if best_metric is None or m < best_metric:
                    best_metric = m
                    match_idx = j
                    if m == 0:
                        break
        if match_idx == -1:
            return False
        # consume the match so duplicates are handled correctly
        pool.pop(match_idx)

    return True


# ----------------------------
# Button logic (OCR + fuzzy)
# ----------------------------


def _click_button_by_text(
    ctrl: IController,
    ocr,
    game_img: Image.Image,
    dets: List[DetectionDict],
    *,
    classes: Sequence[str],
    texts: Sequence[str],
    threshold: float = 0.70,
) -> bool:
    """
    Find buttons of specific classes, OCR them, click the one that best matches any `texts`.
    Falls back to single-button click if only one exists.
    """
    choices = [d for d in dets if str(d.get("name")) in classes]
    if not choices:
        return False

    if len(choices) == 1:
        ctrl.click_xyxy_center(choices[0]["xyxy"], clicks=1)
        return True

    if "BACK" in texts:
        # Special heuristic for BACK:
        # choose the white button that is **bottom-most** (largest y)
        # and, among those, **left-most** (smallest x).
        try:
            pick = min(
                choices,
                key=lambda d: (
                    -((d["xyxy"][1] + d["xyxy"][3]) / 2.0),  # prefer larger y (bottom)
                    ((d["xyxy"][0] + d["xyxy"][2]) / 2.0),  # then smaller x (left)
                ),
            )
            ctrl.click_xyxy_center(pick["xyxy"], clicks=1)
            return True
        except Exception as e:
            logger_uma.warning(f"Couldn't directly find BACK: {e}")
            # fall back to normal OCR matching below if something goes wrong
            pass

    best_d, best_score = None, 0.0
    for d in choices:
        crop = crop_pil(game_img, d["xyxy"], pad=0)
        txt = (ocr.text(crop) or "").strip()
        score = max(fuzzy_ratio(txt, t) for t in texts)
        if score > best_score:
            best_d, best_score = d, score

    if best_d and best_score >= threshold:
        ctrl.click_xyxy_center(best_d["xyxy"], clicks=1)
        return True
    return False


# ----------------------------
# Skill purchase core
# ----------------------------
def _collect_skills_view(
    yolo_engine: IDetector,
    *,
    imgsz: int = 832,
    conf: float = 0.51,
    iou: float = 0.45,
) -> Tuple[Image.Image, List[DetectionDict]]:
    """Take a screenshot + detections (wrapper for easier testing)."""
    game_img, _, parsed = yolo_engine.recognize(
        imgsz=imgsz, conf=conf, iou=iou, tag="skill"
    )
    return game_img, parsed


def _find_buy_inside(
    square: DetectionDict, candidates: List[DetectionDict]
) -> Optional[DetectionDict]:
    """Return the buy button whose bbox lies inside the 'skills_square' bbox."""
    sq_xyxy = square.get("xyxy")
    if not sq_xyxy:
        return None
    for c in candidates:
        if inside(c["xyxy"], sq_xyxy, pad=4):
            return c
    return None


def _scan_and_click_buys(
    ctrl: IController,
    ocr,
    yolo_engine: IDetector,
    targets: Sequence[str],
    *,
    imgsz: int,
    conf: float,
    iou: float,
    ocr_threshold: float = 0.68,
) -> Tuple[bool, Image.Image, List[DetectionDict]]:
    """
    One pass over current screen: click any `skills_buy` whose parent square OCR-matches a target skill.
    Returns (clicked_any, game_img, dets).
    """
    game_img, dets = _collect_skills_view(yolo_engine, imgsz=imgsz, conf=conf, iou=iou)

    squares = [d for d in dets if d["name"] == "skills_square"]
    buys = [d for d in dets if d["name"] == "skills_buy"]
    clf = ActiveButtonClassifier.load(Settings.IS_BUTTON_ACTIVE_CLF_PATH)
    clicked_any = False

    for sq in squares:

        # if valid skill (not obtained)
        buy = _find_buy_inside(sq, buys)
        if buy is None:
            continue

        # if we can buy it

        crop_buy = crop_pil(game_img, buy["xyxy"], pad=0)
        p = float(clf.predict_proba(crop_buy))
        if p < 0.55:
            # IS OFF (inactive button)
            continue

        crop = crop_pil(game_img, sq["xyxy"], pad=3)
        text = ocr.text(crop) or ""
        # quick contains OR best match (robust)
        contains_any = any(
            fuzzy_contains(text, t, threshold=ocr_threshold) for t in targets
        )
        best_name, best_score = fuzzy_best_match(text, targets)
        if contains_any or best_score >= ocr_threshold:
            ctrl.click_xyxy_center(buy["xyxy"], clicks=1)
            logger_uma.info(
                "Clicked BUY for skill '%s' (score=%.2f)", best_name or "?", best_score
            )
            clicked_any = True

    return clicked_any, game_img, dets


def _confirm_learn_close_back_flow(
    ctrl: IController, ocr, 
    yolo_engine: IDetector,*, imgsz: int, conf: float, iou: float, waiting_poput=2
) -> None:
    """
    Confirm → Learn → Close → Back (with re-detect + OCR at each step).
    Each step tolerates multiple buttons; we pick the best OCR match.
    """
    # Confirm
    for _ in range(6):
        game_img, dets = _collect_skills_view(yolo_engine, imgsz=imgsz, conf=conf, iou=iou)
        if _click_button_by_text(
            ctrl, ocr, game_img, dets, classes=("button_green",), texts=("CONFIRM",)
        ):
            break
        time.sleep(0.15)

    time.sleep(waiting_poput)

    # Learn (confirmation dialog)
    for _ in range(10):
        game_img, dets = _collect_skills_view(yolo_engine, imgsz=imgsz, conf=conf, iou=iou)
        if _click_button_by_text(
            ctrl, ocr, game_img, dets, classes=("button_green",), texts=("LEARN",)
        ):
            break
        time.sleep(0.15)

    # Animation / toast
    time.sleep(waiting_poput)

    # Close
    for _ in range(10):
        game_img, dets = _collect_skills_view(yolo_engine, imgsz=imgsz, conf=conf, iou=iou)
        if _click_button_by_text(
            ctrl, ocr, game_img, dets, classes=("button_white",), texts=("CLOSE",)
        ):
            break
        time.sleep(0.15)

    time.sleep(waiting_poput)

    # Back (bottom-left white)
    for _ in range(10):
        game_img, dets = _collect_skills_view(yolo_engine, imgsz=imgsz, conf=conf, iou=iou)
        if _click_button_by_text(
            ctrl, ocr, game_img, dets, classes=("button_white",), texts=("BACK",)
        ):
            break
        time.sleep(0.15)
    time.sleep(waiting_poput)


def auto_buy_skills(
    ctrl: IController,
    ocr,
    yolo_engine: IDetector,
    skill_list: Sequence[str],
    *,
    imgsz: int = 832,
    conf: float = 0.51,
    iou: float = 0.45,
    max_scrolls: int = 10,
    ocr_threshold: float = 0.68,
    scroll_time_range: int = [6, 7],
    early_stop: bool = True,
) -> bool:
    """
    Main entrypoint used on RaceDay.
    Returns True if at least one skill was bought (and confirm/learn/close/back sequence executed).
    """
    if not skill_list:
        logger_uma.info("[skills] No targets configured.")
        return False

    logger_uma.info("[skills] Buying targets: %s", ", ".join(skill_list))

    any_clicked = False
    prev_sig: Optional[List[Tuple[str, int, int]]] = None

    for i in range(max_scrolls):
        clicked, game_img, dets = _scan_and_click_buys(
            ctrl,
            ocr,
            yolo_engine,
            skill_list,
            imgsz=imgsz,
            conf=conf,
            iou=iou,
            ocr_threshold=ocr_threshold,
        )
        any_clicked |= clicked

        # early stop if nothing clicked and screen basically didn't change
        cur_sig = yolo_signature(dets)
        if (
            early_stop
            and not clicked
            and prev_sig is not None
            and _nearly_same(prev_sig, cur_sig)
        ):
            logger_uma.info("[skills] Early stop (same view twice).")
            break
        prev_sig = cur_sig

        # If on the very first pass nothing was clicked, the mouse might not be
        # over the scrollable list. Nudge focus by clicking a skills square (or
        # fallback to screen center) and then perform a few micro-scrolls.
        if i == 0 and not any_clicked:
            try:
                squares = [d for d in dets if d.get("name") == "skills_square"]
                if squares:
                    ctrl.move_xyxy_center(squares[0]["xyxy"])
                    logger_uma.debug(
                        "[skills] Focus nudge: moved to first skills_square"
                    )

                else:
                    # Center of the last screenshot (local) → screen coords
                    W, H = game_img.size
                    cx, cy = W // 2, H // 2
                    sx, sy = ctrl.local_to_screen(cx, cy)
                    j = 10
                    logger_uma.debug(
                        "[skills] Focus nudge: moved to screen center local(%d,%d) -> screen(%d,%d)",
                        cx,
                        cy,
                        sx,
                        sy,
                    )
                    ctrl.move_to(
                        sx + random.randint(-j, j),
                        sy + random.randint(-j, j),
                        duration=0.18,
                    )
                time.sleep(0.10)
            except Exception as e:
                logger_uma.debug("[skills] Focus nudge failed: %s", e)

        scroll_time = random.randint(scroll_time_range[0], scroll_time_range[1])

        is_android = isinstance(ctrl, ScrcpyController)
        if is_android:
            x, y, w, h = ctrl._client_bbox_screen_xywh()
            cx, cy = (x + w // 2), (y + h // 2)
            ctrl.move_to(cx, cy)
            time.sleep(0.5)
            # Heuristic for Redmi 13 Pro
            ctrl.scroll(
                -h // 10, steps=4, duration_range=[0.2, 0.4], end_hold_range=[0.1, 0.2]
            )
        else:
            for _ in range(scroll_time):
                # Small scroll for next batch
                ctrl.scroll(-1)
                time.sleep(0.01)
        time.sleep(0.1)

    if any_clicked:
        logger_uma.info("[skills] Confirming purchases...")
        _confirm_learn_close_back_flow(ctrl, ocr, yolo_engine, imgsz=imgsz, conf=conf, iou=iou)
    else:
        # Back
        for _ in range(10):
            game_img, dets = _collect_skills_view(yolo_engine, imgsz=imgsz, conf=conf, iou=iou)
            if _click_button_by_text(
                ctrl, ocr, game_img, dets, classes=("button_white",), texts=("BACK",)
            ):
                break
            time.sleep(0.15)
        logger_uma.info("[skills] No matching skills found to buy.")
        time.sleep(1.5)

    return any_clicked
