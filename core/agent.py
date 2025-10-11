# core/agent.py
from __future__ import annotations

from time import sleep

from core.actions.claw import ClawGame
from core.actions.events import EventFlow
from core.actions.lobby import LobbyFlow
from core.actions.race import RaceFlow
from core.actions.skills import SkillsFlow
from core.actions.training_policy import (
    TrainAction,
    click_training_tile,
    check_training,
)
from core.controllers.base import IController
from core.perception.analyzers.screen import classify_screen
from core.perception.extractors.state import (
    extract_energy_pct,
    extract_goal_text,
    extract_skill_points,
    find_best,
)
from core.perception.ocr.interface import OCRInterface
from core.perception.yolo.interface import IDetector
from core.settings import Settings
from core.utils.logger import logger_uma
from typing import Optional
from core.utils.text import fuzzy_contains
from core.utils.waiter import PollConfig, Waiter
from core.actions.race import ConsecutiveRaceRefused
from core.utils.abort import abort_requested
from core.utils.event_processor import CATALOG_JSON, Catalog, UserPrefs
from core.utils.race_index import RaceIndex

class Player:
    def __init__(
        self,
        ctrl: IController,
        ocr: OCRInterface,
        yolo_engine: IDetector,
        *,
        minimum_skill_pts: int = 700,
        prioritize_g1: bool = False,
        auto_rest_minimum=26,
        plan_races: dict | None = None,
        waiter_config: PollConfig = PollConfig(
            imgsz=Settings.YOLO_IMGSZ,
            conf=Settings.YOLO_CONF,
            iou=Settings.YOLO_IOU,
            poll_interval_s=0.5,
            timeout_s=4.0,
            tag="player",
        ),
        skill_list=[
            "Concentration",
            "Focus",
            "Professor of Curvature",
            "Swinging Maestro",
            "Corner Recovery",
            "Corner Acceleration",
            "Straightaway Recovery",
            "Homestretch Haste",
            "Straightaway Acceleration",
        ],
        interval_stats_refresh=3,
        select_style=None,
        event_prefs: UserPrefs | None = None,
    ) -> None:
        self.ctrl = ctrl
        self.ocr = ocr
        self.yolo_engine = yolo_engine
        self.is_running = False
        self.imgsz = Settings.YOLO_IMGSZ
        self.conf = Settings.YOLO_CONF
        self.iou = Settings.YOLO_IOU
        self.prioritize_g1 = bool(prioritize_g1)
        self._skip_training_race_once = False
        self.plan_races = dict(plan_races or {})

        # Vision params used by Waiter & flows
        self.skill_list = skill_list or []

        self.auto_rest_minimum = auto_rest_minimum

        # Shared Waiter for the whole agent
        self.waiter = Waiter(self.ctrl, self.ocr, self.yolo_engine, waiter_config)

        # Flows
        self.race = RaceFlow(self.ctrl, self.ocr, self.yolo_engine, self.waiter)
        self.lobby = LobbyFlow(
            self.ctrl,
            self.ocr,
            self.yolo_engine,
            self.waiter,
            minimum_skill_pts=minimum_skill_pts,
            auto_rest_minimum=auto_rest_minimum,
            prioritize_g1=prioritize_g1,
            interval_stats_refresh=interval_stats_refresh,
            plan_races=self.plan_races,
        )
        self.skills_flow = SkillsFlow(
            self.ctrl, self.ocr, self.yolo_engine, self.waiter
        )

        catalog = Catalog.load(CATALOG_JSON)
        # Prefer prefs coming from config.json (passed by main); fallback to legacy file.
        self.event_flow = EventFlow(
            self.ctrl, self.ocr, self.yolo_engine, self.waiter, catalog, event_prefs
        )

        self.claw_game = ClawGame(self.ctrl, self.yolo_engine)
        self.claw_turn = 0

        self._iterations_turn = 0
        self._minimum_skill_pts = int(minimum_skill_pts)
        self.patience = 0
        self.select_style = select_style
        # Skills optimization tracking
        self._last_skill_check_turn: int | None = None
        self._last_skill_pts_seen: int | None = None
        self._last_skill_buy_succeeded: bool = False
        self._planned_skip_release_pending: bool = False
        self._planned_skip_release_key: Optional[str] = None
        self._planned_skip_cooldown: int = 0
        self._first_race_day = True

    def _desired_race_today(self) -> str | None:
        """
        If we have a planned race for today's date (Y{year}-{MM}-{half}),
        return its name; otherwise None.
        """
        di = getattr(self.lobby.state, "date_info", None)
        if not di or di.month is None or (getattr(di, "half", None) not in (1, 2)):
            return None
        key = f"Y{di.year_code}-{int(di.month):02d}-{int(di.half)}"
        plan = getattr(self.lobby, "plan_races", None) or self.plan_races
        raw_race = plan.get(key)
        if raw_race:
            canon = RaceIndex.canonicalize(raw_race)
            logger_uma.info(
                f"[agent] Planned race for {key}: raw='{raw_race}' canon='{canon}'"
            )
            self.lobby.state.planned_race_canonical = canon or raw_race.lower()
            self.lobby.state.planned_race_name = str(raw_race)
            return str(raw_race)
        return None

    def _today_date_key(self) -> Optional[str]:
        di = getattr(self.lobby.state, "date_info", None)
        if not di or di.month is None or (getattr(di, "half", None) not in (1, 2)):
            return None
        return f"Y{di.year_code}-{int(di.month):02d}-{int(di.half)}"

    def _schedule_planned_skip_release(self) -> None:
        self._planned_skip_release_pending = True
        self._planned_skip_release_key = self._today_date_key()
        self._planned_skip_cooldown = max(self._planned_skip_cooldown, 2)
        logger_uma.info(
            "[planned_race] scheduled skip reset key=%s cooldown=%d",
            self._planned_skip_release_key,
            self._planned_skip_cooldown,
        )

    def _clear_planned_skip_release(self) -> None:
        if self._planned_skip_release_pending:
            logger_uma.info(
                "[planned_race] cleared pending skip reset key=%s",
                self._planned_skip_release_key,
            )
        self._planned_skip_release_pending = False
        self._planned_skip_release_key = None
        self._planned_skip_cooldown = 0

    def _tick_planned_skip_release(self) -> None:
        if not self._planned_skip_release_pending:
            return
        if not self.lobby._skip_race_once:
            self._clear_planned_skip_release()
            return
        if self._planned_skip_cooldown > 0:
            self._planned_skip_cooldown -= 1
            return

        current_key = self._today_date_key()
        if (
            self._planned_skip_release_key
            and current_key
            and current_key != self._planned_skip_release_key
        ):
            logger_uma.info(
                "[planned_race] date advanced (%s -> %s); releasing skip guard",
                self._planned_skip_release_key,
                current_key,
            )
            self.lobby._skip_race_once = False
            self._clear_planned_skip_release()
            return

        logger_uma.info(
            "[planned_race] releasing skip guard for key=%s",
            current_key or self._planned_skip_release_key,
        )
        self.lobby._skip_race_once = False
        self._clear_planned_skip_release()

    # --------------------------
    # Main loop
    # --------------------------
    def run(self, *, delay: float = 0.4, max_iterations: int | None = None) -> None:
        self.ctrl.focus()
        self.is_running = True

        while self.is_running:
            # Hard-stop hook (F2)
            if abort_requested():
                logger_uma.info(
                    "[agent] Abort requested; exiting main loop immediately."
                )
                break
            sleep(delay)
            img, _, dets = self.yolo_engine.recognize(
                imgsz=self.imgsz, conf=self.conf, iou=self.iou, tag="screen"
            )

            screen, _ = classify_screen(
                dets,
                lobby_conf=0.5,
                require_infirmary=True,
                training_conf=0.50,
                names_map=None,
            )

            is_lobby_summer = screen == "LobbySummer"
            unknown_screen = screen.lower() == "unknown"

            self._tick_planned_skip_release()

            if unknown_screen:
                threshold = 0.65
                if self.patience > 20:
                    # try to auto recover
                    threshold = 0.55
                # Prefer green NEXT/OK/CLOSE/RACE; no busy loops scattered elsewhere
                if self.waiter.click_when(
                    classes=(
                        "button_green",
                        "race_after_next",
                        "button_white",
                    ),  # improve the model. TODO: add text exception for this function
                    texts=("NEXT", "OK", "CLOSE", "PROCEED", "CANCEL"),
                    prefer_bottom=False,
                    allow_greedy_click=False,
                    forbid_texts=("complete", "career", "RACE", "try again"),
                    timeout_s=delay,
                    tag="agent_unknown_advance",
                    threshold=threshold,
                ):
                    self.patience = 0
                else:
                    self.patience += 1

                    if self.patience > 10 == 0:
                        # try single clean click
                        screen_width = img.width
                        screen_height = img.height
                        cx = screen_width * 0.5
                        y = screen_height * 0.1

                        self.ctrl.click_xyxy_center((cx, y, cx, y), clicks=1)
                        pass
                    pat = int(delay * 100)
                    if self.patience >= pat:
                        logger_uma.warning(
                            "Stopping the algorithm just for safeness, nothing happened in 20 iterations"
                        )
                        self.is_running = False
                        break
                continue

            if screen == "Event":
                self.claw_turn = 0
                # pass what we know about current energy (may be None if not read yet)
                self.lobby.state.energy = extract_energy_pct(img, dets)
                curr_energy = self.lobby.state.energy or 100
                decision = self.event_flow.process_event_screen(
                    img,
                    dets,
                    current_energy=curr_energy,
                    max_energy_cap=100,
                )
                logger_uma.debug(f"[Event] {decision}")
                continue

            if screen == "Training":
                self.claw_turn = 0
                self.patience = 0
                self.waiter.click_when(
                    classes=("button_white", "race_after_next"),
                    texts=("BACK",),
                    prefer_bottom=True,
                    timeout_s=1.0,
                    tag="screen_training_directly",
                )
                continue

            if screen == "Inspiration":
                self.patience = 0
                self.claw_turn = 0
                inspiration = find_best(dets, "event_inspiration", conf_min=0.4)
                if inspiration:
                    self.ctrl.click_xyxy_center(inspiration["xyxy"], clicks=1)
                continue

            if screen == "Raceday":
                self.patience = 0
                self.claw_turn = 0
                self._iterations_turn += 1
                # Optimization, only buy in Raceday (where you can actually lose the career)
                self.lobby.state.skill_pts = extract_skill_points(self.ocr, img, dets)
                logger_uma.info(
                    f"[agent] Skill Pts: {self.lobby.state.skill_pts}. Stats: {self.lobby.state.stats}"
                )

                # Skills optimization gate
                if (
                    len(self.skill_list) > 0
                    and self.lobby.state.skill_pts >= self._minimum_skill_pts
                ):
                    try:
                        current_turn = int(self.lobby.state.turn)
                    except Exception:
                        current_turn = -1
                    interval = int(Settings.SKILL_CHECK_INTERVAL)
                    delta_thr = int(Settings.SKILL_PTS_DELTA)
                    last_pts = (
                        self._last_skill_pts_seen
                        if self._last_skill_pts_seen is not None
                        else int(self.lobby.state.skill_pts)
                    )
                    pts_delta = max(0, int(self.lobby.state.skill_pts) - int(last_pts))
                    turn_gate = (interval <= 1) or (
                        current_turn >= 0 and (current_turn % max(1, interval) == 0)
                    )
                    delta_gate = pts_delta >= delta_thr
                    should_open_skills = (
                        turn_gate or delta_gate or self._last_skill_buy_succeeded
                    )
                    logger_uma.debug(
                        f"[skills] check interval={interval} turn={current_turn} turn_gate={turn_gate} delta={pts_delta} delta_gate={delta_gate} last_ok={self._last_skill_buy_succeeded}"
                    )
                    if should_open_skills or self._first_race_day:
                        self._first_race_day = False
                        self.lobby._go_skills()
                        bought = self.skills_flow.buy(self.skill_list)
                        self._last_skill_buy_succeeded = bool(bought)
                        self._last_skill_pts_seen = int(self.lobby.state.skill_pts)
                        self._last_skill_check_turn = (
                            current_turn
                            if current_turn >= 0
                            else self._last_skill_check_turn
                        )
                        logger_uma.info(f"[agent] Skills bought: {bought}")
                    else:
                        # Track last seen points even when skipping
                        self._last_skill_pts_seen = int(self.lobby.state.skill_pts)
                career_date_raw = self.lobby.state.career_date_raw or ""

                race_predebut = "predebut" in career_date_raw.lower().replace("-", "")
                logger_uma.debug(f"Race day, is predebut= {race_predebut}")

                if not race_predebut and self.select_style and not career_date_raw:
                    if not self.lobby.state.goal:
                        self.lobby.state.goal = (
                            extract_goal_text(self.ocr, img, dets) or ""
                        )

                    race_predebut = fuzzy_contains(
                        self.lobby.state.goal.lower(),
                        "junior make debut",
                        threshold=0.8,
                    )
                    logger_uma.debug(
                        f"Unknown date but  select_style= {self.select_style}. checking goal: {self.lobby.state.goal.lower()}. race debut?:{race_predebut}"
                    )

                if race_predebut:
                    # Enter or confirm race, then run RaceFlow
                    # Run RaceFlow; it will ensure navigation into Raceday if needed
                    ok = self.race.run(
                        prioritize_g1=False,
                        select_style=self.select_style,
                        from_raceday=True,
                        reason="Pre-debut (race day)",
                    )
                    if not ok:
                        raise RuntimeError("Couldn't race")
                    # Mark raced on current date-key to avoid double-race if date OCR doesn't tick
                    self.lobby.mark_raced_today(self._today_date_key())
                    continue
                else:
                    ok = self.race.run(
                        prioritize_g1=False,
                        select_style=None,
                        from_raceday=True,
                        reason="Normal (race day)",
                    )
                    if not ok:
                        raise RuntimeError("Couldn't race")
                    self.lobby.mark_raced_today(self._today_date_key())
                    continue

            if screen == "Lobby" or is_lobby_summer:
                self.patience = 0
                self.claw_turn = 0
                self._iterations_turn += 1
                outcome, reason = self.lobby.process_turn()

                if outcome == "TO_RACE":
                    if "G1" in reason.upper():
                        logger_uma.info(reason)
                        try:
                            ok = self.race.run(
                                prioritize_g1=True,
                                is_g1_goal=True,
                                reason=self.lobby.state.goal,
                            )
                        except ConsecutiveRaceRefused:
                            logger_uma.info(
                                "[lobby] Consecutive race refused → backing out; set skip guard."
                            )
                            self.lobby._go_back()
                            self.lobby._skip_race_once = True
                            continue
                        if not ok:
                            logger_uma.error(
                                "[lobby] Couldn't race (G1 target). Backing out; set skip guard."
                            )
                            self.lobby._go_back()
                            self.lobby._skip_race_once = True
                            continue
                        self.lobby.mark_raced_today(self._today_date_key())
                    elif "PLAN" in reason.upper():
                        desired_race_name = self._desired_race_today()
                        if desired_race_name:
                            # Planned race
                            logger_uma.info(
                                "[planned_race] attempting desired='%s' key=%s skip=%s",
                                desired_race_name,
                                self._today_date_key(),
                                self.lobby._skip_race_once,
                            )
                            try:
                                ok = self.race.run(
                                    prioritize_g1=self.prioritize_g1,
                                    is_g1_goal=False,
                                    desired_race_name=desired_race_name,
                                    date_key=self._today_date_key(),
                                    reason=f"Planned race: {desired_race_name}",
                                )
                            except ConsecutiveRaceRefused:
                                logger_uma.info(
                                    "[lobby] Consecutive race refused on planned race → back & skip once."
                                )
                                self.lobby._go_back()
                                self.lobby._skip_race_once = True
                                logger_uma.info(
                                    "[planned_race] skip_guard=1 after refusal desired='%s' key=%s",
                                    desired_race_name,
                                    self._today_date_key(),
                                )
                                self._schedule_planned_skip_release()
                                continue
                            if not ok:
                                logger_uma.error(
                                    f"[race] Couldn't race {desired_race_name}"
                                )
                                self.lobby._go_back()
                                self.lobby._skip_race_once = True
                                logger_uma.info(
                                    "[planned_race] skip_guard=1 after failure desired='%s' key=%s",
                                    desired_race_name,
                                    self._today_date_key(),
                                )
                                self._schedule_planned_skip_release()
                                # TODO: smart Continue with training instead of continue
                                continue

                            # Clean planned
                            self.lobby.mark_raced_today(self._today_date_key())
                            logger_uma.info(
                                "[planned_race] completed desired='%s' key=%s",
                                desired_race_name,
                                self._today_date_key(),
                            )
                            self._clear_planned_skip_release()

                    elif "FANS" in reason.upper():
                        logger_uma.info(reason)
                        try:
                            ok = self.race.run(
                                prioritize_g1=self.prioritize_g1,
                                is_g1_goal=False,
                                reason=self.lobby.state.goal,
                            )
                        except ConsecutiveRaceRefused:
                            logger_uma.info(
                                "[lobby] Consecutive race refused → back & skip once."
                            )
                            self.lobby._go_back()
                            self.lobby._skip_race_once = True
                            continue
                        if not ok:
                            logger_uma.error(
                                "[lobby] Couldn't race (fans target). Backing out; set skip guard."
                            )
                            self.lobby._go_back()
                            self.lobby._skip_race_once = True
                            continue
                        self.lobby.mark_raced_today(self._today_date_key())

                if outcome == "TO_TRAINING":
                    logger_uma.info(
                        f"[lobby] goal='{self.lobby.state.goal}' | energy={self.lobby.state.energy} | "
                        f"skill_pts={self.lobby.state.skill_pts} | turn={self.lobby.state.turn} | "
                        f"summer={self.lobby.state.is_summer} | mood={self.lobby.state.mood} | stats={self.lobby.state.stats} |"
                    )
                    # sleep(1.0)
                    self._handle_training()
                    continue

                # For other outcomes ("INFIRMARY", "RESTED", "CONTINUE") we just loop
                continue

            if screen == "FinalScreen":
                self.claw_turn = 0
                # Only if skill list defined
                if len(self.skill_list) > 0 and self.lobby._go_skills():
                    sleep(1.0)
                    bought = self.skills_flow.buy(self.skill_list)
                    self._last_skill_buy_succeeded = bool(bought)
                    logger_uma.info(f"[agent] Skills bought: {bought}")
                    self.is_running = False  # end of career
                    logger_uma.info("Detected end of career")

                    # pick = det_filter(dets, ["lobby_skills"])[-1]
                    # x1 = pick["xyxy"][0]
                    # y1 = pick["xyxy"][1]
                    # x2 = pick["xyxy"][2]
                    # y2 = pick["xyxy"][3]

                    # btn_width = abs(x2 - x1)
                    # x1 += btn_width + btn_width // 10
                    # x2 += btn_width + btn_width // 10
                    # self.ctrl.click_xyxy_center((x1, y1, x2, y2), clicks=1, jitter=1)
                    continue

            if screen == "ClawMachine":
                self.claw_turn += 1
                logger_uma.debug(
                    f"Claw Machine detected... starting to play. Claw turn: {self.claw_turn}"
                )
                if self.claw_game.play_once(tag_prefix="claw"):
                    logger_uma.debug("Claw Machine triggered sucessfully")
                else:
                    logger_uma.error("Couldn't trigger Claw Machine")
                sleep(3)
                continue

    # --------------------------
    # Training handling (acts on decisions from policy)
    # --------------------------
    def _handle_training(self) -> None:
        """
        Act on the training decision:
         - If a tile action: click the tile.
         - If REST/RECREATION/RACE: go back to lobby and execute via LobbyFlow/RaceFlow.
         - If race fails as a training action, re-run the decision once with skip_race=True.
        """
        if not self.is_running:
            return
        # Initial decision (no skip)
        decision = check_training(self, skip_race=self._skip_training_race_once)
        if decision is None:
            return

        if not self.is_running:
            return
        self._skip_training_race_once = False
        action = decision.action
        tidx = decision.tile_idx
        training_state = decision.training_state

        tile_actions_train = {
            TrainAction.TRAIN_MAX.value,
            TrainAction.TRAIN_WIT.value,
            TrainAction.TRAIN_DIRECTOR.value,
            TrainAction.TAKE_HINT.value,
        }
        action_is_in_last_screen = action.value in (
            TrainAction.REST.value,
            TrainAction.RECREATION.value,
            TrainAction.RACE.value,
        )

        # Tile actions within the training screen
        if action.value in tile_actions_train and tidx is not None:
            ok = click_training_tile(self.ctrl, training_state, tidx)
            if not ok:
                logger_uma.error(
                    "[training] Failed to click training tile idx=%s", tidx
                )
            return

        # Actions that require going back to the lobby
        if action_is_in_last_screen:
            # Return to lobby from training
            if not self.lobby._go_back():
                raise RuntimeError("Couldn't return to previous screen from training")

            if action.value == TrainAction.REST.value:
                if not self.lobby._go_rest(reason="Resting..."):
                    logger_uma.error("[training] ERROR when trying to rest")
                return

            if action.value == TrainAction.RECREATION.value:
                if not self.lobby._go_recreate(reason="Recreating..."):
                    logger_uma.error("[training] ERROR when trying to recreate")
                return

            if action.value == TrainAction.RACE.value:
                # Try to race from lobby (RaceFlow will navigate into Raceday)
                try:
                    if self.race.run(
                        prioritize_g1=self.prioritize_g1,
                        reason="Training policy → race",
                    ):
                        return
                except ConsecutiveRaceRefused:
                    logger_uma.info(
                        "[training] Consecutive race refused → back to training and skip once."
                    )
                    self.lobby._go_back()
                    self.lobby._skip_race_once = True
                    self._skip_training_race_once = True
                    if self.lobby._go_training_screen_from_lobby(None, None):
                        decision2 = check_training(self, skip_race=True)
                        if (
                            decision2
                            and decision2.action.value in tile_actions_train
                            and decision2.tile_idx is not None
                        ):
                            click_training_tile(
                                self.ctrl, decision2.training_state, decision2.tile_idx
                            )
                    return

                # Race failed → go back, revisit training once with skip_race=True
                logger_uma.warning(
                    "[training] Couldn't race from training policy; retrying decision without racing (Also, suitable G1 probably wasn't found)."
                )
                self.lobby._go_back()
                self.lobby._skip_race_once = True
                self._skip_training_race_once = True

                # Navigate back to training screen explicitly, then decide again (skip_race)
                if self.lobby._go_training_screen_from_lobby(None, None):
                    # sleep(1.2)
                    decision2 = check_training(self, skip_race=True)
                    if decision2 is None:
                        return
                    # If the second decision is a tile action, click it
                    if (
                        decision2.action.value in tile_actions_train
                        and decision2.tile_idx is not None
                    ):
                        click_training_tile(
                            self.ctrl, decision2.training_state, decision2.tile_idx
                        )
                    else:
                        logger_uma.info(
                            "[training] Second decision after failed race: %s",
                            decision2.action.value,
                        )
                return

        # Fallback: nothing to do
        logger_uma.debug("[training] No actionable decision.")

    # ------------- Hard-stop helper -------------
    def emergency_stop(self) -> None:
        """Cooperative, best-effort immediate stop hook."""
        self.is_running = False
        try:
            # Release any possible held inputs if controller exposes such methods
            if hasattr(self.ctrl, "release_all"):
                self.ctrl.release_all()  # type: ignore[attr-defined]
        except Exception:
            pass
