# core/utils/pointer.py
from __future__ import annotations

import time

from core.controllers.android import ScrcpyController  # type check only
from core.controllers.base import IController
from core.utils.logger import logger_uma


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
