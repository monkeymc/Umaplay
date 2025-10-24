# core/actions/roulette.py
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from threading import Event
from typing import List, Optional, Sequence, Tuple

from PIL import Image

from core.controllers.base import IController
from core.perception.is_button_active import ActiveButtonClassifier
from core.perception.ocr.interface import OCRInterface
from core.perception.yolo.interface import IDetector
from core.settings import Settings
from core.types import DetectionDict
from core.utils import nav
from core.utils.geometry import crop_pil
from core.utils.logger import logger_uma
from core.utils.waiter import Waiter


@dataclass(slots=True)
class ButtonState:
    detection: DetectionDict
    probability: float
    is_active: bool


class RouletteFlow:
    def __init__(
        self,
        ctrl: IController,
        ocr: Optional[OCRInterface],
        yolo_engine: IDetector,
        waiter: Waiter,
        *,
        spin_clicks: Sequence[int] = (2, 4),
        skip_clicks: Sequence[int] = (2, 4),
        agent_name: str = None,
        stop_event: Optional[Event] = None,
    ) -> None:
        self.ctrl = ctrl
        self.ocr = ocr
        self.yolo_engine = yolo_engine
        self.waiter = waiter
        self.spin_clicks = tuple(spin_clicks)
        self.skip_clicks = tuple(skip_clicks)
        self._thr = {
            "button_active": 0.70,
            "button_inactive": 0.55,
            "fallback_conf": 0.30,
        }
        self.agent_name = agent_name
        if self.agent_name is None:
            self.agent_name = Settings.AGENT_NAME_NAV
        self._stop_event = stop_event

        try:
            self._button_clf = ActiveButtonClassifier.load(
                Settings.IS_BUTTON_ACTIVE_CLF_PATH
            )
        except Exception as exc:  # pragma: no cover - diagnostic only during proto
            logger_uma.warning(
                "[RouletteFlow] Failed to load ActiveButtonClassifier: %s", exc
            )
            self._button_clf = None

    def _should_stop(self) -> bool:
        return self._stop_event is not None and self._stop_event.is_set()

    def snapshot(self, *, tag: str = "roulette_scan") -> Tuple[Image.Image, List[DetectionDict]]:
        return nav.collect_snapshot(self.waiter, self.yolo_engine, agent=self.agent_name, tag=tag)

    def button_detections(
        self,
        dets: List[DetectionDict],
        *,
        conf_min: Optional[float] = None,
    ) -> List[DetectionDict]:
        threshold = conf_min if conf_min is not None else self._thr["fallback_conf"]
        return [
            d
            for d in dets
            if d.get("name") == "roulette_button" and float(d.get("conf", 0.0)) >= threshold
        ]

    def active_buttons(self, dets: List[DetectionDict]) -> List[DetectionDict]:
        return self.button_detections(dets, conf_min=self._thr["button_active"])

    def inactive_buttons(self, dets: List[DetectionDict]) -> List[DetectionDict]:
        buttons = self.button_detections(dets, conf_min=self._thr["button_inactive"])
        return [
            d
            for d in buttons
            if float(d.get("conf", 0.0)) < self._thr["button_active"]
        ]

    def classify_button_state(
        self,
        detection: DetectionDict,
        *,
        img: Optional[Image.Image] = None,
        tag: str = "roulette_button_check",
    ) -> Optional[ButtonState]:
        if not self._button_clf:
            return None
        if self._should_stop():
            return None
        if img is None:
            img, _ = self.snapshot(tag=tag)
            if self._should_stop():
                return None
        crop = crop_pil(img, detection.get("xyxy", (0, 0, 0, 0)))
        try:
            probability = float(self._button_clf.predict_proba(crop))
        except Exception as exc:
            logger_uma.debug("[RouletteFlow] Active classifier failed: %s", exc)
            return None
        is_active = probability >= 0.51
        return ButtonState(detection=detection, probability=probability, is_active=is_active)

    def tap_spin_center(self, detection: DetectionDict, *, clicks: Optional[int] = None) -> None:
        spin_times = clicks if clicks is not None else random.randint(*self.spin_clicks)
        self.ctrl.click_xyxy_center(detection["xyxy"], clicks=spin_times)

    def tap_skip_region(
        self, img: Image.Image, *, clicks: Optional[int] = None, y_ratio: float = 0.1
    ) -> None:
        width, height = img.size
        cx = int(width * 0.5) + int(random.uniform(-width * 0.03, width * 0.1))
        cy = int(height * y_ratio) + int(random.uniform(-height * y_ratio * 0.02, height * y_ratio * 0.02))
        skip_times = clicks if clicks is not None else random.randint(*self.skip_clicks)
        self.ctrl.click_xyxy_center((cx, cy, cx, cy), clicks=skip_times)

    def debug_scan(self) -> List[ButtonState]:
        img, dets = self.snapshot(tag="roulette_debug_scan")
        results: List[ButtonState] = []
        for det in self.button_detections(dets):
            state = self.classify_button_state(det, img=img, tag="roulette_debug_state")
            if state is not None:
                results.append(state)
        if not results:
            logger_uma.debug("[RouletteFlow] No roulette_button detected")
        return results

    def run_cycle(self, *, tag_prefix: str = "roulette") -> dict:
        spun_any = False

        while True:
            if self._should_stop():
                reason = "stopped_after_spin" if spun_any else "stopped"
                return {"spun": spun_any, "reason": reason}
            img, dets = self.snapshot(tag=f"{tag_prefix}_scan")
            if self._should_stop():
                reason = "stopped_after_spin" if spun_any else "stopped"
                return {"spun": spun_any, "reason": reason}
            buttons = self.button_detections(dets)
            if not buttons:
                if spun_any:
                    return {"spun": True}
                logger_uma.debug("[RouletteFlow] No button detected; nudging UI")
                self.tap_skip_region(img, clicks=2)
                return {"spun": False, "reason": "no-button"}

            primary = max(buttons, key=lambda d: float(d.get("conf", 0.0)))
            state = self.classify_button_state(primary, img=img, tag=f"{tag_prefix}_state")
            if self._should_stop():
                reason = "stopped_after_spin" if spun_any else "stopped"
                return {"spun": spun_any, "reason": reason}

            if state and state.is_active:
                spun_any = True
                logger_uma.info(
                    "[RouletteFlow] Button active (p=%.3f); spinning.", state.probability
                )
                self.tap_spin_center(primary)
                time.sleep(0.4)
                inactive_counter = 0
                while inactive_counter < 1.5:
                    if self._should_stop():
                        reason = "stopped_after_spin" if spun_any else "stopped"
                        return {"spun": spun_any, "reason": reason}
                    img, dets = self.snapshot(tag=f"{tag_prefix}_scan")
                    if self._should_stop():
                        reason = "stopped_after_spin" if spun_any else "stopped"
                        return {"spun": spun_any, "reason": reason}
                    buttons = self.button_detections(dets)
                    if buttons:
                        primary = max(buttons, key=lambda d: float(d.get("conf", 0.0)))
                        state = self.classify_button_state(
                            primary, img=img, tag=f"{tag_prefix}_state"
                        )
                        if self._should_stop():
                            reason = "stopped_after_spin" if spun_any else "stopped"
                            return {"spun": spun_any, "reason": reason}
                        if state and not state.is_active:
                            inactive_counter += 1
                        else:
                            inactive_counter = 0
                            self.tap_spin_center(primary)
                    else:
                        inactive_counter += 0.5
                    time.sleep(0.4)

                self.tap_skip_region(img, clicks=random.randint(2, 3))

                restart_cycle = False
                max_time = time.time() + 10
                while time.time() < max_time:
                    if self._should_stop():
                        reason = "stopped_after_spin" if spun_any else "stopped"
                        return {"spun": spun_any, "reason": reason}
                    img, dets = self.snapshot(tag=f"{tag_prefix}_scan")
                    if self._should_stop():
                        reason = "stopped_after_spin" if spun_any else "stopped"
                        return {"spun": spun_any, "reason": reason}
                    buttons = self.button_detections(dets)
                    if buttons:
                        primary = max(buttons, key=lambda d: float(d.get("conf", 0.0)))
                        state = self.classify_button_state(
                            primary, img=img, tag=f"{tag_prefix}_state"
                        )
                        if self._should_stop():
                            reason = "stopped_after_spin" if spun_any else "stopped"
                            return {"spun": spun_any, "reason": reason}

                        if state:
                            if state.is_active:
                                logger_uma.debug(
                                    "[RouletteFlow] Button detected; restarting handlerspinning."
                                )
                                restart_cycle = True
                                break
                            else:
                                logger_uma.debug(
                                    "[RouletteFlow] Button inactive; continuing with bypass."
                                )
                                time.sleep(0.6)

                    self.tap_skip_region(img, clicks=random.randint(2, 3))
                    time.sleep(0.3)
                else:
                    logger_uma.debug("[RouletteFlow] Timed out waiting for button detection.")

                if restart_cycle:
                    continue

                return {"spun": True}

            if state and not state.is_active:
                logger_uma.debug(
                    "[RouletteFlow] Button inactive cooldown (p=%.3f).",
                    state.probability,
                )
                self.tap_skip_region(img, clicks=random.randint(2, 3))
                time.sleep(0.6)
                return {
                    "spun": spun_any,
                    "reason": "cooldown",
                    "probability": state.probability,
                }

            logger_uma.debug("[RouletteFlow] Unable to classify button state.")
            time.sleep(0.4)
            if self._should_stop():
                reason = "stopped_after_spin" if spun_any else "stopped"
                return {"spun": spun_any, "reason": reason}
            if spun_any:
                return {"spun": True, "reason": "unknown"}
            return {"spun": False, "reason": "unknown"}
