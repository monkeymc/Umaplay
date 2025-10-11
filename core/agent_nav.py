# core/agent_nav.py
from __future__ import annotations

import threading
from collections import Counter
from time import sleep
from typing import Dict, List, Tuple

from PIL import Image

from core.actions.daily_race import DailyRaceFlow
from core.actions.team_trials import TeamTrialsFlow
from core.controllers.base import IController
from core.perception.ocr.interface import OCRInterface
from core.perception.yolo.interface import IDetector
from core.settings import Settings
from core.types import DetectionDict
from core.utils import nav
from core.utils.logger import logger_uma
from core.utils.waiter import PollConfig, Waiter


ScreenInfo = Dict[str, object]
ScreenName = str


class AgentNav:
    """
    YOLO-driven navigator for the new menus.
    Delegates domain-specific logic to actions.* flows and reuses utils.nav helpers.
    """

    def __init__(
        self,
        ctrl: IController,
        ocr: OCRInterface,
        yolo_engine: IDetector,
        action: str,
        waiter_config: PollConfig = PollConfig(
            imgsz=Settings.YOLO_IMGSZ,
            conf=Settings.YOLO_CONF,
            iou=Settings.YOLO_IOU,
            poll_interval_s=0.5,
            timeout_s=4.0,
            tag="player",
        ),
    ) -> None:
        self.ctrl = ctrl
        self.ocr = ocr
        self.yolo_engine = yolo_engine
        self.waiter = Waiter(ctrl, ocr, yolo_engine, waiter_config)
        self.action = action
        self._stop_event = threading.Event()
        self._thr = {
            "race_team_trials": 0.50,
            "race_daily_races": 0.50,
            "banner_opponent": 0.50,
            "race_daily_races_monies_row": 0.80,
            "race_team_trials_go": 0.45,
            "button_pink": 0.35,
            "button_advance": 0.35,
            "shop_clock": 0.35,
            "shop_exchange": 0.35,
            "button_back": 0.35,
            "button_green": 0.35,
            "button_white": 0.35,
        }

        # flows
        self.team_trials = TeamTrialsFlow(ctrl, ocr, yolo_engine, self.waiter)
        self.daily_race = DailyRaceFlow(ctrl, ocr, yolo_engine, self.waiter)

    # --------------------------
    # Screen classification
    # --------------------------

    def classify_nav_screen(
        self, dets: List[DetectionDict]
    ) -> Tuple[ScreenName, ScreenInfo]:
        counts = Counter(d["name"] for d in dets)

        action = (self.action or "").lower()

        if action == "team_trials":
            if nav.has(
                dets, "race_team_trials", conf_min=self._thr["race_team_trials"]
            ):
                return "RaceScreen", {"counts": dict(counts)}

            if nav.has(dets, "banner_opponent", conf_min=self._thr["banner_opponent"]):
                return "TeamTrialsBanners", {"counts": dict(counts)}

            if self.waiter.seen(
                classes=("button_green",),
                texts=("RESTORE",),
                tag="agent_nav_team_trials_restore_seen",
            ):
                return "TeamTrialsFinished", {"counts": dict(counts)}

            if nav.has(
                dets, "race_team_trials_go", conf_min=self._thr["race_team_trials_go"]
            ):
                return "TeamTrialsGo", {"counts": dict(counts)}

            if nav.has(dets, "shop_clock", conf_min=self._thr["shop_clock"]) or nav.has(
                dets, "shop_exchange", conf_min=self._thr["shop_exchange"]
            ):
                return "TeamTrialsShop", {"counts": dict(counts)}

            # pink + advance + back (button white but I call it back to not confuse with other button white)
            if nav.has(dets, "button_pink", conf_min=self._thr["button_pink"]) and nav.has(
                dets, "button_advance", conf_min=self._thr["button_advance"]
            ) and nav.has(
                dets, "button_white", conf_min=self._thr["button_back"]
            ):
                return "TeamTrialsResults", {"counts": dict(counts)}

            # If it only has a 'Back' button_white button in screen, is TeamTrialsStale
            # and No pink, no advance and not button_green
            if nav.has(dets, "button_white", conf_min=self._thr["button_back"]) and not nav.has(dets, "button_pink", conf_min=self._thr["button_pink"]) and not nav.has(dets, "button_advance", conf_min=self._thr["button_advance"]) and not nav.has(dets, "button_green", conf_min=self._thr["button_green"]):
                return "TeamTrialsStale", {"counts": dict(counts)}

        elif action == "daily_races":
            if nav.has(
                dets, "race_daily_races", conf_min=self._thr["race_daily_races"]
            ):
                return "RaceScreen", {"counts": dict(counts)}

            if nav.has(
                dets,
                "race_daily_races_monies_row",
                conf_min=self._thr["race_daily_races_monies_row"],
            ):
                return "RaceDailyRows", {"counts": dict(counts)}

            # For Daily race, if daily race mode is enabled and has 2 elements: 1 button_white (back) and 1 button_green (next) then the classification is DailyRaceResume
            if nav.has(dets, "button_white", conf_min=self._thr["button_back"]) and nav.has(
                dets, "button_green", conf_min=self._thr["button_green"]
            ):
                return "DailyRaceResume", {"counts": dict(counts)}

        else:
            # Fallback for other actions retains the broader detection for compatibility.
            if nav.has(
                dets, "race_team_trials", conf_min=self._thr["race_team_trials"]
            ) or nav.has(
                dets, "race_daily_races", conf_min=self._thr["race_daily_races"]
            ):
                return "RaceScreen", {"counts": dict(counts)}

            if nav.has(dets, "banner_opponent", conf_min=self._thr["banner_opponent"]):
                return "TeamTrialsBanners", {"counts": dict(counts)}

            if self.waiter.seen(
                classes=("button_green",),
                texts=("RESTORE",),
                tag="agent_nav_team_trials_restore_seen",
            ):
                return "TeamTrialsFinished", {"counts": dict(counts)}

            if nav.has(
                dets,
                "race_daily_races_monies_row",
                conf_min=self._thr["race_daily_races_monies_row"],
            ):
                return "RaceDailyRows", {"counts": dict(counts)}

            if nav.has(
                dets, "race_team_trials_go", conf_min=self._thr["race_team_trials_go"]
            ):
                return "TeamTrialsGo", {"counts": dict(counts)}

            if nav.has(dets, "shop_clock", conf_min=self._thr["shop_clock"]) or nav.has(
                dets, "shop_exchange", conf_min=self._thr["shop_exchange"]
            ):
                return "TeamTrialsShop", {"counts": dict(counts)}

            if nav.has(dets, "button_pink", conf_min=self._thr["button_pink"]) and nav.has(
                dets, "button_advance", conf_min=self._thr["button_advance"]
            ) and nav.has(
                dets, "button_white", conf_min=self._thr["button_back"]
            ):
                return "TeamTrialsResults", {"counts": dict(counts)}

            if nav.has(dets, "button_white", conf_min=self._thr["button_back"]) and not nav.has(dets, "button_pink", conf_min=self._thr["button_pink"]) and not nav.has(dets, "button_advance", conf_min=self._thr["button_advance"]) and not nav.has(dets, "button_green", conf_min=self._thr["button_green"]):
                return "TeamTrialsStale", {"counts": dict(counts)}

            if nav.has(dets, "button_white", conf_min=self._thr["button_back"]) and nav.has(
                dets, "button_green", conf_min=self._thr["button_green"]
            ):
                return "DailyRaceResume", {"counts": dict(counts)}

        return "UnknownNav", {"counts": dict(counts)}

    # --------------------------
    # Main
    # --------------------------

    def run(self) -> Tuple[ScreenName, ScreenInfo]:
        self.ctrl.focus()
        # fresh start: ensure previous stop is cleared
        try:
            self._stop_event.clear()
        except Exception:
            pass
        self.is_running = True
        last_screen: ScreenName = "UnknownNav"
        last_info: ScreenInfo = {}

        counter = 60
        while not self._stop_event.is_set() and counter > 0:
            img, dets = nav.collect_snapshot(
                self.waiter, self.yolo_engine, tag="agent_nav"
            )
            screen, info = self.classify_nav_screen(dets)
            logger_uma.debug(f"[AgentNav] screen={screen} | info={info}")

            if screen == "RaceScreen":
                if self.action == "daily_races":
                    if self.daily_race.enter_from_menu():
                        sleep(1.0)
                elif self.action == "team_trials":
                    if self.team_trials.enter_from_menu():
                        sleep(1.0)

            elif screen == "RaceDailyRows":
                if self.daily_race.pick_first_row():
                    sleep(1.0)
                    self.daily_race.confirm_and_next_to_race()
                    sleep(1.0)
                    self.daily_race.run_race_and_collect()
                self.is_running = False
                counter = 0

            elif self.action == "team_trials" and screen == "TeamTrialsBanners":
                logger_uma.info("[AgentNav] TeamTrials banners detected")
                self.team_trials.process_banners_screen()
            elif self.action == "team_trials" and screen in {
                "TeamTrialsGo",
                "TeamTrialsShop",
                "TeamTrialsResults",
                "TeamTrialsStale",
            }:
                logger_uma.info(
                    f"[AgentNav] TeamTrials recovery state detected: {screen}"
                )
                self.team_trials.resume()

            elif self.action == "team_trials" and screen == "TeamTrialsFinished":
                logger_uma.info("[AgentNav] TeamTrials finished detected")
                self.team_trials.handle_finished_prompt()
                self.is_running = False
                counter = 0

            elif screen == "DailyRaceResume":
                logger_uma.info("[AgentNav] DailyRace resume detected")
                self.daily_race.run_race_and_collect()
                self.is_running = False
                counter = 0
            else:
                # Stop if we don't know what we're seeing; extend rules as needed
                counter -= 1

            last_screen, last_info = screen, info
            # Responsive sleep: wake early if stop requested
            for _ in range(20):  # up to ~2.0s total
                if self._stop_event.is_set():
                    break
                sleep(0.1)

        self.is_running = False
        return last_screen, last_info

    def stop(self) -> None:
        """Signal the run loop to stop on the next iteration."""
        try:
            logger_uma.info("[AgentNav] Stop signal received.")
        except Exception:
            pass
        self.is_running = False
        self._stop_event.set()
