# core/actions/daily_race.py
from __future__ import annotations

import random
from time import sleep
from typing import List

from core.controllers.base import IController
from core.controllers.android import ScrcpyController

try:
    from core.controllers.bluestacks import BlueStacksController
except Exception:
    BlueStacksController = None  # type: ignore
from core.perception.ocr.interface import OCRInterface
from core.perception.yolo.interface import IDetector
from core.types import DetectionDict
from core.utils.logger import logger_uma
from core.utils.waiter import Waiter
from core.utils import nav


class DailyRaceFlow:
    """
    Daily Races navigation: enter menu, pick a 'monies' card/row, confirm, race, results.
    """

    def __init__(
        self,
        ctrl: IController,
        ocr: OCRInterface,
        yolo_engine: IDetector,
        waiter: Waiter,
    ) -> None:
        self.ctrl = ctrl
        self.ocr = ocr
        self.yolo_engine = yolo_engine
        self.waiter = waiter
        self._thr = {
            "row": 0.70,  # race_daily_races_monies_row
        }

    def enter_from_menu(self) -> bool:
        ok = self.waiter.click_when(
            classes=("race_daily_races",),
            prefer_bottom=False,
            timeout_s=2.0,
            tag="daily_race_menu",
        )
        if not ok:
            return False
        sleep(1.2)
        # Often need to click the 'monies' card
        self.waiter.click_when(
            classes=("race_daily_races_monies",),
            prefer_bottom=True,
            timeout_s=2.0,
            tag="daily_race_monies",
        )
        return True

    def pick_first_row(self) -> bool:
        """
        Click the first valid 'race_daily_races_monies_row' (topmost above threshold).
        """
        img, dets = nav.collect_snapshot(
            self.waiter, self.yolo_engine, tag="daily_race_rows"
        )
        rows = nav.rows_top_to_bottom(dets, "race_daily_races_monies_row")
        for row in rows:
            if float(row.get("conf", 0.0)) >= self._thr["row"]:
                self.ctrl.click_xyxy_center(row["xyxy"])
                logger_uma.info("[DailyRace] Clicked 'Monies' row")
                return True
        return False

    def confirm_and_next_to_race(self) -> bool:
        """
        NEXT -> RACE
        """
        sleep(1.5)
        ok = self.waiter.click_when(
            classes=("button_green",),
            prefer_bottom=True,
            allow_greedy_click=True,
            timeout_s=2.0,
            tag="daily_race_next_0",
        )
        if not ok:
            logger_uma.debug("[DailyRace] Confirm not found (continuing anyway)")
        sleep(1.5)
        if self.waiter.click_when(
            classes=("button_green",),
            prefer_bottom=True,
            timeout_s=2.0,
            tag="daily_race_race",
        ):
            logger_uma.info("[DailyRace] RACE 1")
        return True

    def run_race_and_collect(self) -> bool:
        """
        Start race, view results and proceed.
        """

        race_again = True
        finalized = False
        counter = 5
        while race_again and counter > 0:
            sleep(3)
            if isinstance(self.ctrl, ScrcpyController) or (
                BlueStacksController is not None
                and isinstance(self.ctrl, BlueStacksController)
            ):
                sleep(2.0)
            if self.waiter.click_when(
                classes=("button_green",),
                prefer_bottom=True,
                timeout_s=2.0,
                tag="daily_race_next_1",
            ):
                logger_uma.info("[DailyRace] NEXT (1)")
            else:
                race_again = False
                continue
            sleep(1.5)

            if self.waiter.click_when(
                classes=("button_green",),
                prefer_bottom=True,
                timeout_s=2.0,
                tag="daily_race_race",
            ):
                logger_uma.info("[DailyRace] race (2)")
            else:
                race_again = False
                continue
            counter -= 1
            sleep(2.0)
            # After race, click 'View Results' / proceed with white button spamming
            img, _ = nav.collect_snapshot(
                self.waiter, self.yolo_engine, tag="daily_race_view_results"
            )
            self.waiter.click_when(
                classes=("button_white",),
                prefer_bottom=False,
                timeout_s=2.3,
                texts=("VIEW RESULTS",),
                forbid_texts=("BACK",),
                allow_greedy_click=False,
                clicks=random.randint(3, 4),
                tag="daily_race_view_results_white",
            )
            sleep(2.0)
            nav.random_center_tap(
                self.ctrl, img, clicks=random.randint(3, 4), dev_frac=0.20
            )
            sleep(2.0)

            # Then green to continue
            if self.waiter.click_when(
                classes=("button_green",),
                prefer_bottom=True,
                timeout_s=2.0,
                tag="daily_race_after_results_green",
            ):
                logger_uma.info("[DailyRace] Results: continued")

            # check for shop, reuse the nav method
            did_shop = nav.handle_shop_exchange_on_clock_row(
                self.waiter,
                self.yolo_engine,
                self.ctrl,
                tag_prefix="daily_race_shop",
                ensure_enter=True,
            )
            if did_shop:
                logger_uma.info("[DailyRace] Completed shop exchange flow")
            else:
                if not self.waiter.click_when(
                    classes=("button_pink",),
                    texts=("RACE AGAIN",),
                    prefer_bottom=False,
                    timeout_s=2.2,
                    clicks=1,
                    allow_greedy_click=False,
                    tag="team_trials_race_again",
                ):
                    logger_uma.info("[TeamTrials] RACE AGAIN NOT FOUND")
                    finalized = True
                    break
                else:
                    sleep(2.0)
                    if self.waiter.seen(
                        classes=("button_green",),
                        texts=("OK",),
                        tag="agent_nav_daily_race_ok",
                    ):
                        logger_uma.info("[DailyRace] OK seen no more dailys")
                        # Click in button_white using the waiter
                        self.waiter.click_when(
                            classes=("button_white",),
                            prefer_bottom=True,
                            timeout_s=2.0,
                            tag="daily_race_ok",
                        )
                        sleep(1.5)
                        # Click in button_advance using the waiter
                        self.waiter.click_when(
                            classes=("button_advance",),
                            prefer_bottom=True,
                            timeout_s=2.0,
                            tag="daily_race_advance",
                        )
                        sleep(2)
                        if isinstance(self.ctrl, ScrcpyController) or (
                            BlueStacksController is not None
                            and isinstance(self.ctrl, BlueStacksController)
                        ):
                            sleep(4.0)
                        # Click object with class ui_home
                        self.waiter.click_when(
                            classes=("ui_home",),
                            prefer_bottom=True,
                            timeout_s=2.0,
                            tag="daily_race_home",
                        )
                        finalized = True
                        race_again = False
                    continue
        return finalized
