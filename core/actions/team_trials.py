# core/actions/team_trials.py
from __future__ import annotations

import random
from time import sleep
from typing import Tuple, List
from enum import Enum

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

class TeamTrialsState(Enum):
    UNKNOWN = "unknown"
    HOME = "home"
    GO = "go"
    BANNERS = "banners"
    RESULTS = "results"
    SHOP = "shop"


class TeamTrialsFlow:
    """
    Encapsulates Team Trials navigation, banners, race start, advances, and optional shop.
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
            "banner_opponent": 0.50,
            "race_team_trials": 0.45,
            "race_team_trials_go": 0.45,
            "shop_clock": 0.35,
            "shop_exchange": 0.35,
            "button_pink": 0.35,
            "button_advance": 0.35,
        }

    # ---------- High-level entry points ----------

    def enter_from_menu(self) -> bool:
        """Click main menu → Team Trials → 'GO'."""
        ok_menu = self.waiter.click_when(
            classes=("race_team_trials",),
            prefer_bottom=False,
            timeout_s=2.0,
            tag="team_trials_menu",
        )
        if not ok_menu:
            return False

        sleep(1.5)
        ok_go = self.waiter.click_when(
            classes=("race_team_trials_go",),
            prefer_bottom=False,
            timeout_s=2.0,
            tag="team_trials_go",
        )
        if ok_go:
            logger_uma.info("[TeamTrials] Entered 'Team Trials' → GO")
        return ok_go

    def process_banners_screen(self) -> None:
        """
        Handle the 'opponent banners' screen:
          - click a banner (bottom-most preferred)
          - pre-start button-green loops
          - start race (RACE!)
          - advance through post-race, handle shop if it appears, then try 'RACE AGAIN'
        """
        sleep(1.0)
        img, dets = nav.collect_snapshot(
            self.waiter, self.yolo_engine, tag="team_trials_banners"
        )
        banners = [d for d in dets if d["name"] == "banner_opponent"]
        if not banners:
            logger_uma.warning("[TeamTrials] No opponent banners detected")
            return

        # Click bottom-most banner (prefer_bottom semantics)
        clicked = self.waiter.click_when(
            classes=("banner_opponent",),
            prefer_bottom=True,
            timeout_s=2.0,
            clicks=random.randint(3, 4),
            tag="team_trials_banner_click",
        )
        if not clicked:
            logger_uma.warning("[TeamTrials] Could not click any opponent banner")
            return

        logger_uma.info("[TeamTrials] Clicked opponent banner")
        sleep(5)
        sleep(4)

        # Pre-start: a few green clicks (progression prompts)
        pre = nav.click_button_loop(
            self.waiter,
            classes=("button_green",),
            tag_prefix="team_trials_prestart",
            max_clicks=1,
            sleep_between_s=0.30,
            prefer_bottom=True,
            timeout_s=4.0,
        )
        logger_uma.debug(f"[TeamTrials] pre-start greens: {pre}")
        sleep(1.3)
        # Try to hit 'RACE!' (avoid CANCEL)
        started = self.waiter.click_when(
            classes=("button_green",),
            texts=("RACE!",),
            prefer_bottom=True,
            allow_greedy_click=False,
            forbid_texts=("CANCEL",),
            clicks=random.randint(1, 2),
            timeout_s=2.0,
            tag="team_trials_race_start",
        )
        if not started:
            logger_uma.warning("[TeamTrials] Couldn't press 'RACE!'")
        self._handle_post_race_sequence(ensure_enter_shop=True)

    def resume(self, *, max_steps: int = 8) -> bool:
        """
        Attempt to recover Team Trials flow regardless of the current screen.
        Returns True if any step was handled during the recovery loop.
        """
        handled_any = False
        for _ in range(max_steps):
            sleep(0.8)
            img, dets = nav.collect_snapshot(
                self.waiter, self.yolo_engine, tag="team_trials_resume"
            )
            state = self._classify_state(dets)
            logger_uma.debug(f"[TeamTrials] resume detected state={state.value}")
            if state is TeamTrialsState.UNKNOWN:
                break

            handled_any = True

            if state is TeamTrialsState.HOME:
                self._handle_home_screen()
            elif state is TeamTrialsState.GO:
                self._handle_go_screen()
            elif state is TeamTrialsState.BANNERS:
                self.process_banners_screen()
            elif state is TeamTrialsState.RESULTS:
                self._handle_results_screen()
            elif state is TeamTrialsState.SHOP:
                self._handle_shop_in_place()

            sleep(1.0)

        return handled_any

    def _classify_state(self, dets: List[DetectionDict]) -> TeamTrialsState:
        if nav.has(dets, "shop_clock", conf_min=self._thr["shop_clock"]) or nav.has(
            dets, "shop_exchange", conf_min=self._thr["shop_exchange"]
        ):
            return TeamTrialsState.SHOP

        if nav.has(
            dets, "banner_opponent", conf_min=self._thr["banner_opponent"]
        ):
            return TeamTrialsState.BANNERS

        if nav.has(
            dets, "race_team_trials_go", conf_min=self._thr["race_team_trials_go"]
        ):
            return TeamTrialsState.GO

        if nav.has(dets, "race_team_trials", conf_min=self._thr["race_team_trials"]):
            return TeamTrialsState.HOME

        if nav.has(dets, "button_pink", conf_min=self._thr["button_pink"]) or nav.has(
            dets, "button_advance", conf_min=self._thr["button_advance"]
        ):
            return TeamTrialsState.RESULTS

        return TeamTrialsState.UNKNOWN

    def _handle_home_screen(self) -> None:
        logger_uma.info("[TeamTrials] Home screen detected; clicking 'Team Race'.")
        clicked = self.waiter.click_when(
            classes=("button_pink",),
            texts=("TEAM RACE", "TEAM RACES", "VIEW RACE"),
            prefer_bottom=True,
            timeout_s=2.5,
            tag="team_trials_home_team_race",
        )
        if not clicked:
            self.waiter.click_when(
                classes=("button_green",),
                texts=("TEAM RACE",),
                prefer_bottom=True,
                timeout_s=2.5,
                tag="team_trials_home_team_race_green",
            )

    def _handle_go_screen(self) -> None:
        logger_uma.info("[TeamTrials] GO button detected; attempting to enter.")
        self.waiter.click_when(
            classes=("race_team_trials_go",),
            prefer_bottom=False,
            timeout_s=2.0,
            tag="team_trials_go_screen",
        )

    def _handle_results_screen(self) -> None:
        logger_uma.info("[TeamTrials] Results screen detected; advancing flow.")
        self._handle_post_race_sequence(ensure_enter_shop=True)

    def _handle_shop_in_place(self) -> None:
        logger_uma.info("[TeamTrials] Shop screen detected; processing exchange.")
        if nav.handle_shop_exchange_on_clock_row(
            self.waiter,
            self.yolo_engine,
            self.ctrl,
            tag_prefix="team_trials_shop_resume",
            ensure_enter=False,
        ):
            logger_uma.info("[TeamTrials] Completed shop exchange flow")
        else:
            logger_uma.warning("[TeamTrials] Unable to process shop exchange")

    def _handle_post_race_sequence(self, *, ensure_enter_shop: bool) -> None:
        sleep(4.0)
        sleep(4)
        adv = nav.advance_sequence_with_mid_taps(
            self.waiter,
            self.yolo_engine,
            self.ctrl,
            tag_prefix="team_trials_adv",
            iterations_max=6,
            advance_class="button_advance",
            advance_texts=None,
            taps_each_click=(3, 4),
            tap_dev_frac=0.20,
            sleep_after_advance=0.40,
        )
        logger_uma.debug(f"[TeamTrials] advances performed: {adv}")
        sleep(3)
        sleep(4)

        img, _ = nav.collect_snapshot(
            self.waiter, self.yolo_engine, tag="team_trials_midtap"
        )
        nav.random_center_tap(
            self.ctrl, img, clicks=random.randint(4, 5), dev_frac=0.01
        )
        sleep(1.0)
        sleep(2)

        did_shop = nav.handle_shop_exchange_on_clock_row(
            self.waiter,
            self.yolo_engine,
            self.ctrl,
            tag_prefix="team_trials_shop",
            ensure_enter=ensure_enter_shop,
        )
        if did_shop:
            logger_uma.info("[TeamTrials] Completed shop exchange flow")
        else:
            _, dets = nav.collect_snapshot(
                self.waiter, self.yolo_engine, tag="team_trials_especial_reward check"
            )

            if len(dets) == 1:
                did_next = self.waiter.click_when(
                    classes=("button_advance",),
                    prefer_bottom=True,
                    clicks=1,
                    forbid_texts=("VIEW RACE",),
                    allow_greedy_click=True,
                    timeout_s=2.3,
                    tag="team_trials_reward_next",
                )
                if did_next:
                    self.waiter.click_when(
                        classes=("button_green",),
                        prefer_bottom=True,
                        timeout_s=2.0,
                        clicks=1,
                        tag="team_trials_reward_next_green",
                    )
                    sleep(0.3)

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

    def handle_finished_prompt(self) -> None:
        """
        After all trials are consumed: click 'NO', then press advance once to exit.
        """
        logger_uma.info("[TeamTrials] Finished flow detected; cleaning up.")
        self.waiter.click_when(
            classes=("button_white",),
            texts=("NO",),
            prefer_bottom=True,
            timeout_s=2.0,
            tag="team_trials_finished_no",
        )
        sleep(0.5)
        self.waiter.click_when(
            classes=("button_advance",),
            prefer_bottom=True,
            timeout_s=2.0,
            tag="team_trials_finished_advance",
        )
