# core/utils/nav.py
from __future__ import annotations

import random
from time import sleep
from typing import List, Sequence, Tuple, Dict, Optional

from PIL import Image

from core.controllers.base import IController
from core.perception.yolo.interface import IDetector
from core.types import DetectionDict
from core.utils.logger import logger_uma
from core.utils.waiter import Waiter


def collect_snapshot(
    waiter: Waiter, yolo_engine: IDetector, *, tag: str
) -> Tuple[Image.Image, List[DetectionDict]]:
    img, _, dets = yolo_engine.recognize(
        imgsz=waiter.cfg.imgsz, conf=waiter.cfg.conf, iou=waiter.cfg.iou, tag=tag
    )
    return img, dets


def has(dets: List[DetectionDict], name: str, *, conf_min: float = 0.0) -> bool:
    return any(
        d.get("name") == name and float(d.get("conf", 0.0)) >= conf_min for d in dets
    )


def by_name(
    dets: List[DetectionDict], name: str, *, conf_min: float = 0.0
) -> List[DetectionDict]:
    return [
        d
        for d in dets
        if d.get("name") == name and float(d.get("conf", 0.0)) >= conf_min
    ]


def rows_top_to_bottom(
    dets: List[DetectionDict], name: str, *, conf_min: float = 0.0
) -> List[DetectionDict]:
    rows = by_name(dets, name, conf_min=conf_min)
    rows.sort(key=lambda d: d["xyxy"][1])
    return rows


def random_center_tap(
    ctrl: IController, img: Image.Image, *, clicks: int, dev_frac: float = 0.20
) -> None:
    """Tap near the center with random deviation."""
    W, H = img.size
    cx = W * 0.5 + random.uniform(-W * dev_frac, W * dev_frac)
    cy = H * 0.5 + random.uniform(-H * dev_frac, H * dev_frac)
    ctrl.click_xyxy_center((cx, cy, cx, cy), clicks=clicks)


def click_button_loop(
    waiter: Waiter,
    *,
    classes: Sequence[str],
    tag_prefix: str,
    max_clicks: int = 6,
    sleep_between_s: float = 0.30,
    prefer_bottom: bool = True,
    texts: Optional[Sequence[str]] = None,
    clicks_each: int = 1,
    allow_greedy_click: bool = True,
    forbid_texts: Optional[Sequence[str]] = None,
    timeout_s: float = 2.0,
) -> int:
    """
    Repeatedly click a button limited by max_clicks. Returns number of successful clicks.
    """
    done = 0
    while done < max_clicks:
        ok = waiter.click_when(
            classes=classes,
            texts=texts,
            prefer_bottom=prefer_bottom,
            allow_greedy_click=allow_greedy_click,
            forbid_texts=forbid_texts,
            clicks=clicks_each,
            timeout_s=timeout_s,
            tag=f"{tag_prefix}_loop",
        )
        if not ok:
            break
        done += 1
        sleep(sleep_between_s)
    return done


def advance_sequence_with_mid_taps(
    waiter: Waiter,
    yolo_engine: IDetector,
    ctrl: IController,
    *,
    tag_prefix: str,
    iterations_max: int = 6,
    advance_class: str = "button_advance",
    advance_texts: Optional[Sequence[str]] = None,
    taps_each_click: Tuple[int, int] = (3, 4),
    tap_dev_frac: float = 0.20,
    sleep_after_advance: float = 0.40,
) -> int:
    """
    Click NEXT/advance a few times; after each advance, tap around center to nudge UI.
    Returns number of advances performed.
    """
    advances = 0
    for i in range(iterations_max):
        did = waiter.click_when(
            classes=(advance_class,),
            texts=advance_texts,
            prefer_bottom=True,
            allow_greedy_click=True,
            timeout_s=3.0,
            clicks=random.randint(*taps_each_click),
            tag=f"{tag_prefix}_advance",
        )
        if not did and i > 5:
            break
        sleep(sleep_after_advance)
        img, _ = collect_snapshot(waiter, yolo_engine, tag=f"{tag_prefix}_tap")
        random_center_tap(
            ctrl, img, clicks=random.randint(*taps_each_click), dev_frac=tap_dev_frac
        )
        advances += 1
        sleep(sleep_after_advance / 2)
    return advances


def handle_shop_exchange_on_clock_row(
    waiter: Waiter,
    yolo_engine: IDetector,
    ctrl: IController,
    *,
    tag_prefix: str = "shop",
    ensure_enter: bool = True,
) -> bool:
    """
    If the SHOP prompt appears (green button with 'SHOP'), enter the shop and:
      - find 'shop_clock'
      - find the row that vertically contains the clock center (or closest)
      - click the nearest 'shop_exchange' in that row
      - confirm via green 'EXCHANGE'
    Returns True if an exchange click was attempted.
    """
    # Enter shop if prompted
    shop_appeared = True
    if ensure_enter:
        shop_appeared = waiter.click_when(
            classes=("button_green",),
            texts=("SHOP",),
            prefer_bottom=False,
            allow_greedy_click=False,
            timeout_s=3.0,
            clicks=2,
            tag=f"{tag_prefix}_enter",
        )
        if not shop_appeared:
            return False
        sleep(3)
    else:
        # Already inside the shop; ensure UI elements settle before detection.
        sleep(1.0)
    img, dets = collect_snapshot(waiter, yolo_engine, tag=f"{tag_prefix}_scan")

    clocks = by_name(dets, "shop_clock")
    if not clocks:
        logger_uma.debug("[nav] shop: no clock detected")
        return False

    clock = max(clocks, key=lambda d: float(d.get("conf", 0.0)))
    x1c, y1c, x2c, y2c = clock["xyxy"]
    cy_clock = 0.5 * (y1c + y2c)

    # restrict to the row containing the clock, if any
    rows = [
        d for d in by_name(dets, "shop_row") if d["xyxy"][1] <= cy_clock <= d["xyxy"][3]
    ]
    if rows:
        row = max(rows, key=lambda d: float(d.get("conf", 0.0)))
        ry1, ry2 = row["xyxy"][1], row["xyxy"][3]
        exchanges = [
            d
            for d in by_name(dets, "shop_exchange")
            if ry1 <= (0.5 * (d["xyxy"][1] + d["xyxy"][3])) <= ry2
        ]
    else:
        exchanges = by_name(dets, "shop_exchange")

    if not exchanges:
        logger_uma.debug("[nav] shop: no exchange buttons found")
        return False

    target = min(
        exchanges, key=lambda d: abs((0.5 * (d["xyxy"][1] + d["xyxy"][3])) - cy_clock)
    )

    # y-proximity tolerance (~6% screen height or >=12px)
    img_h = img.height if isinstance(img, Image.Image) else 1080
    tol = max(12.0, 0.06 * img_h)
    cy_ex = 0.5 * (target["xyxy"][1] + target["xyxy"][3])

    if abs(cy_ex - cy_clock) > tol:
        logger_uma.debug("[nav] shop: exchange not aligned with clock within tolerance")
        return False

    ctrl.click_xyxy_center(target["xyxy"], clicks=1)
    logger_uma.info("[nav] shop: clicked 'Exchange' aligned with clock row")

    # confirm EXCHANGE
    waiter.click_when(
        classes=("button_green",),
        texts=("EXCHANGE",),
        prefer_bottom=False,
        timeout_s=2.0,
        allow_greedy_click=False,
        tag=f"{tag_prefix}_confirm_exchange",
    )

    # click button_white button with 'Close'
    if waiter.click_when(
        classes=("button_white",),
        texts=("CLOSE",),
        prefer_bottom=False,
        timeout_s=2.0,
        allow_greedy_click=False,
        tag=f"{tag_prefix}_close",
    ):
        sleep(0.4)
        logger_uma.info("[nav] shop: clicked 'Close'")
        # click button_white with 'END SALE' text
        if waiter.click_when(
            classes=("button_white",),
            texts=("END SALE",),
            prefer_bottom=False,
            timeout_s=2.0,
            allow_greedy_click=False,
            tag=f"{tag_prefix}_end_sale",
        ):
            logger_uma.info("[nav] shop: clicked 'End Sale'")
            sleep(0.4)
            # Click button_green with 'OK' text
            if waiter.click_when(
                classes=("button_green",),
                texts=("OK",),
                prefer_bottom=False,
                timeout_s=2.0,
                allow_greedy_click=False,
                tag=f"{tag_prefix}_ok",
            ):
                logger_uma.info("[nav] shop: clicked 'OK'")
                sleep(1)
                # Press the object with 'ui_race' class
                if waiter.click_when(
                    classes=("ui_race",),
                    prefer_bottom=True,
                    timeout_s=2.0,
                    allow_greedy_click=True,
                    tag=f"{tag_prefix}_race",
                ):
                    logger_uma.info("[nav] shop: clicked 'Race'")
            else:
                return False
        else:
            return False
    else:
        return False

    return True
