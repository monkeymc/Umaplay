# core/agent_nav.py
from __future__ import annotations

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
        self._thr = {
            "race_team_trials": 0.50,
            "race_daily_races": 0.50,
            "banner_opponent": 0.50,
            "race_daily_races_monies_row": 0.80,
        }

        # flows
        self.team_trials = TeamTrialsFlow(ctrl, ocr, yolo_engine, self.waiter)
        self.daily_race = DailyRaceFlow(ctrl, ocr, yolo_engine, self.waiter)

    # --------------------------
    # Screen classification
    # --------------------------

    def classify_nav_screen(self, dets: List[DetectionDict]) -> Tuple[ScreenName, ScreenInfo]:
        counts = Counter(d["name"] for d in dets)

        has_team_trials = nav.has(dets, "race_team_trials", conf_min=self._thr["race_team_trials"])
        has_daily_races = nav.has(dets, "race_daily_races", conf_min=self._thr["race_daily_races"])

        if has_team_trials or has_daily_races:
            return "RaceScreen", {"counts": dict(counts)}

        if nav.has(dets, "banner_opponent", conf_min=self._thr["banner_opponent"]):
            return "TeamTrialsBanners", {"counts": dict(counts)}

        if self.waiter.seen(
            classes=("button_green",),
            texts=("RESTORE",),
            tag="agent_nav_team_trials_restore_seen",
        ):
            return "TeamTrialsFinished", {"counts": dict(counts)}

        if nav.has(dets, "race_daily_races_monies_row", conf_min=self._thr["race_daily_races_monies_row"]):
            return "RaceDailyRows", {"counts": dict(counts)}

        return "UnknownNav", {"counts": dict(counts)}

    # --------------------------
    # Main
    # --------------------------

    def run(self) -> Tuple[ScreenName, ScreenInfo]:
        self.ctrl.focus()
        self.is_running = True
        last_screen: ScreenName = "UnknownNav"
        last_info: ScreenInfo = {}

        counter = 60
        while self.is_running or counter > 0:
            
            img, dets = nav.collect_snapshot(self.waiter, self.yolo_engine, tag="agent_nav")
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

            elif screen == "TeamTrialsBanners":
                logger_uma.info("[AgentNav] TeamTrials banners detected")
                self.team_trials.process_banners_screen()

            elif screen == "TeamTrialsFinished":
                logger_uma.info("[AgentNav] TeamTrials finished detected")
                self.team_trials.handle_finished_prompt()
                self.is_running = False
                counter = 0

            else:
                # Stop if we don't know what we're seeing; extend rules as needed
                counter -= 1

            last_screen, last_info = screen, info
            sleep(2)

        return last_screen, last_info
