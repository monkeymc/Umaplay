# core/utils/pointer.py
from __future__ import annotations

import random
import time
from typing import Iterable, Optional, Tuple

from core.controllers.android import ScrcpyController  # type check only
from core.controllers.base import IController
from core.utils.logger import logger_uma

XYXY = Tuple[float, float, float, float]


def smart_scroll_small(
    ctrl: IController,
    *,
    steps_pc: int = 4,
    delay_pc: float = 0.02,
    steps_android: int = 2,
    fraction_android: float = 0.10,
    settle_pre_s: float = 0.05,
    settle_mid_s: float = 0.10,
    settle_post_s: float = 0.10,
) -> None:
    """
    Small, device-aware scroll:
      • On Android (scrcpy): slight cursor nudge to mid/lower area, short drag with end-hold to kill inertia.
      • On PC: a few wheel ticks with short delays.

    Tunables:
      - steps_pc:    number of wheel ticks on PC
      - delay_pc:    delay between wheel ticks
      - steps_android: number of short drags on Android
      - fraction_android: drag distance as a fraction of client height (e.g., 0.10 = 10%)
    """
    time.sleep(settle_pre_s)

    if isinstance(ctrl, ScrcpyController):
        xywh = ctrl._client_bbox_screen_xywh()
        if not xywh:
            logger_uma.debug("[pointer] no client bbox for Android scroll; skipping")
            time.sleep(settle_post_s)
            return

        x, y, w, h = xywh
        cx, cy = (x + w // 2), int(y + h * 0.66)
        ctrl.move_to(cx, cy)
        time.sleep(settle_mid_s)

        drag_px = max(20, int(h * fraction_android))
        ctrl.scroll(-drag_px, steps=max(1, steps_android), duration_range=(0.20, 0.40), end_hold_range=(0.10, 0.20))
    else:
        for _ in range(max(1, steps_pc)):
            ctrl.scroll(-1)
            time.sleep(max(0.0, delay_pc))

    time.sleep(settle_post_s)


def burst_click_center(
    ctrl: IController,
    xyxy: XYXY,
    *,
    clicks_range: Tuple[int, int] = (2, 3),
    pause_after_s: Optional[float] = None,
) -> None:
    """
    Perform a short burst of clicks at the center of `xyxy`.
    Useful for things like 'View Results' or 'Skip' where multiple taps help.
    """
    lo, hi = clicks_range
    n = random.randint(max(1, lo), max(lo, hi))
    ctrl.click_xyxy_center(xyxy, clicks=n)
    if pause_after_s is not None:
        time.sleep(max(0.0, float(pause_after_s)))


def nudge_focus_to_center(ctrl: IController, xyxy: XYXY, *, pause_s: float = 0.10) -> None:
    """
    Move cursor to the center of `xyxy` with the controller's human-ish move,
    then wait briefly to let hover-driven UI settle.
    """
    try:
        ctrl.move_xyxy_center(xyxy)
        time.sleep(max(0.0, pause_s))
    except Exception as e:
        logger_uma.debug("[pointer] nudge_focus_to_center failed: %s", e)
