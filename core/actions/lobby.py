# core/actions/lobby.py
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Tuple

from core.controllers.base import IController
from core.perception.extractors.state import (
    extract_career_date,
    extract_mood,
    extract_infirmary_on,
    extract_skill_points,
    extract_goal_text,
    extract_energy_pct,
    extract_stats,
    extract_turns
)
from core.utils.logger import logger_uma
from core.utils.race_index import RaceIndex, date_key_from_dateinfo
from core.utils.text import fuzzy_contains
from core.utils.waiter import Waiter
from core.utils.yolo_objects import collect

from core.utils.date_uma import (
    DateInfo,
    date_cmp,
    date_index,
    date_is_pre_debut,
    date_is_regular_year,
    date_is_terminal,
    date_merge,
    is_summer_in_two_or_less_turns,
    is_summer,
    parse_career_date
)

@dataclass
class LobbyState:
    goal: Optional[str] = None
    energy: Optional[int] = None
    skill_pts: int = 0
    infirmary_on: Optional[bool] = None
    turn: int = -1
    career_date_raw: Optional[str] = None
    date_info: Optional[object] = None
    is_summer: Optional[bool] = None
    mood: Tuple[str, float] = ("UNKNOWN", -1.0)
    stats = {"SPD": -1, "STA": -1, "PWR": -1, "GUTS": -1, "WIT": -1}
    planned_race_name: Optional[str] = None

@dataclass
class LobbyConfig:
    imgsz: int = 832
    conf: float = 0.51
    iou: float = 0.45
    poll_interval_s: float = 0.25
    default_timeout_s: float = 4.0

class LobbyFlow:
    """
    Encapsulates all Lobby decisions & navigation.
    Composes RaceFlow and centralizes waits via a single Waiter.
    """

    def __init__(
        self,
        ctrl: IController,
        ocr,
        waiter: Waiter,
        *,
        minimum_skill_pts: int = 500,
        auto_rest_minimum: int = 24,
        prioritize_g1: bool = False,
        process_on_demand = True,
        interval_stats_refresh = 5,
        max_critical_turn = 7,
        plan_races = {}
    ) -> None:
        self.ctrl = ctrl
        self.ocr = ocr
        self.minimum_skill_pts = int(minimum_skill_pts)
        self.auto_rest_minimum = int(auto_rest_minimum)
        self.prioritize_g1 = bool(prioritize_g1)
        self.process_on_demand = bool(process_on_demand)
        self.interval_stats_refresh = interval_stats_refresh
        self._stats_refresh_counter = 0
        self.max_critical_turn = max_critical_turn

        self.state = LobbyState()
        self._skip_race_once = False

        self.waiter = waiter
        self.last_turns_left_prediction = None
        self._last_date_key: Optional[str] = None
        self.plan_races = plan_races

    # --------------------------
    # Public entry point
    # --------------------------
    def process_turn(self):
        """
        Evaluate the Lobby and take the next action.
        Returns a short outcome string:
          - "RACED"          → we entered/finished a race flow
          - "INFIRMARY"      → we went to infirmary
          - "RESTED"         → we chose rest/recreation
          - "TO_TRAINING"    → we navigated to the training screen
          - "CONTINUE"       → we did a minor click or nothing

        optional extra message
        """
        img, dets = collect(self.ctrl, imgsz=self.waiter.cfg.imgsz, conf=self.waiter.cfg.conf, iou=self.waiter.cfg.iou, tag="lobby_state")

        if not self.process_on_demand:
            self._update_state(img, dets)  # -> Very expensive, calculate as you need better
            
        # --- Critical goal logic & early racing opportunities ---

        
        if self.process_on_demand:
            self._process_date_info(img, dets)
            logger_uma.info(f"Date: {self.state.date_info} | raw: {self.state.career_date_raw}")

        if self.process_on_demand:
            self.state.energy = extract_energy_pct(img, dets)

        # --- Race planning (explicit list takes precedence; else G1 if available) ---
        self._plan_race_today()

        # If we have a planned race today, go race (subject to early-guard rules)
        if self.state.planned_race_name:
            # First-Junior-Day guard (no races available there)
            is_first_junior_date = (
                bool(self.state.date_info)
                and self.state.date_info.year_code == 1
                and self.state.date_info.month == 7
                and self.state.date_info.half == 1
            )
            if not is_first_junior_date and not self._skip_race_once:
                reason = f"Planned race: {self.state.planned_race_name}"
                return "TO_RACE", reason
            else:
                logger_uma.debug("[lobby] Planned race suppressed by first-junior-day/skip flag.")


        if self.state.turn <= self.max_critical_turn:
            if not self._skip_race_once and self.state.energy > 2:
                # [Optimization] 10 steps for goal, or unknown turns or -1 turns, check goal
                outcome_bool, reason = self._maybe_do_goal_race(img, dets)
                if outcome_bool:
                    return "TO_RACE", reason

        else:
            if self.state.turn and self.state.turn > 0:
                # [Optimization] predict turns
                self.state.turn -= 1  # predicting the turn to save resources

        # After special-case goal racing, clear the one-shot skip guard.
        self._skip_race_once = False

        if self.process_on_demand:
            self.state.infirmary_on = extract_infirmary_on(img, dets, threshold=0.60)

        # --- Infirmary handling (only outside summer) ---
        if self.state.infirmary_on and (self.state.is_summer is False):
            if self._go_infirmary():
                return "INFIRMARY", "Infirmary to remove blue condition"

        # --- Energy management (rest) ---
        if self.state.energy is not None:
            if self.state.energy <= self.auto_rest_minimum:
                reason = "Energy too low, resting"
                if self._go_rest(reason=reason):
                    return "RESTED", reason
            elif self.state.energy <= 50 and self.state.date_info and is_summer_in_two_or_less_turns(self.state.date_info):
                
                reason = "Resting to prepare for summer"
                if self._go_rest(reason=reason):
                    return "RESTED", reason

        if self.process_on_demand:
            self.state.mood = extract_mood(self.ocr, img, dets, conf_min=0.3)
        
        if self.state.mood[-1] < 0:
            logger_uma.warning("UNKNOWN mood!")
        # --- Mood (for training policy)---
        # Navigate to Training if nothing else


        if self._go_training_screen_from_lobby(img, dets):
            return "TO_TRAINING", "No critical stuff going to train"

        return "CONTINUE", "Unknown"

    def _update_stats(self, img, dets) -> None:
        """
        Smart, monotonic-ish stat updater with refresh gating and noise guards.

        Rules (per stat key in {SPD, STA, PWR, GUTS, WIT}):
        - Ignore invalid reads (-1) and out-of-range values.
        - If previous is -1, accept the first valid value.
        - Accept normal increases up to MAX_UP_STEP per refresh.
        - For larger upward jumps, require the same value to repeat
            PERSIST_FRAMES times before accepting (prevents OCR spikes).
        - Allow small decreases up to MAX_DOWN_STEP (rare debuffs / OCR wobble).
            Larger drops are ignored.
        """
        KEYS = ("SPD", "STA", "PWR", "GUTS", "WIT")
        STAT_MIN, STAT_MAX = 0, 1200
        MAX_UP_STEP = 150          # typical per-turn cap; tune if you see legit bigger jumps
        MAX_DOWN_STEP = 60         # allow tiny decreases; block bigger drops
        PERSIST_FRAMES = 2         # confirm large jumps across this many refreshes

        # lazy init of helper state
        if not hasattr(self, "_stats_last_pred"):
            self._stats_last_pred = {k: -1 for k in KEYS}   # last raw OCR per key
        if not hasattr(self, "_stats_pending"):             # pending large jump candidates
            self._stats_pending = {k: None for k in KEYS}
        if not hasattr(self, "_stats_pending_count"):
            self._stats_pending_count = {k: 0 for k in KEYS}

        # Refresh gating (preserve your optimization)
        if self._stats_refresh_counter == 0 or self._stats_refresh_counter % self.interval_stats_refresh == 0:
            observed = extract_stats(self.ocr, img, dets)  # dict[str,int]
            current  = dict(self.state.stats or {})        # copy to modify safely
            changed  = []

            for key in KEYS:
                new_val = int(observed.get(key, -1))
                prev    = int(current.get(key, -1))

                # remember last prediction for debugging/telemetry
                self._stats_last_pred[key] = new_val

                # reject invalids early
                if new_val < STAT_MIN or new_val > STAT_MAX:
                    continue
                if new_val == -1:
                    logger_uma.debug(f"[stats] {key}: invalid read (-1), keeping {prev}")
                    continue
                if prev == -1:
                    # first valid observation
                    current[key] = new_val
                    self._stats_pending[key] = None
                    self._stats_pending_count[key] = 0
                    changed.append((key, -1, new_val))
                    continue

                delta = new_val - prev

                # small negative change allowed; big drop rejected
                if delta < 0:
                    if abs(delta) <= MAX_DOWN_STEP:
                        current[key] = new_val
                        self._stats_pending[key] = None
                        self._stats_pending_count[key] = 0
                        changed.append((key, prev, new_val))
                    else:
                        logger_uma.debug(f"[stats] {key}: rejecting large drop {prev}->{new_val} (Δ={delta})")
                    continue

                # non-negative delta
                if delta <= MAX_UP_STEP:
                    # normal progression
                    current[key] = new_val
                    self._stats_pending[key] = None
                    self._stats_pending_count[key] = 0
                    changed.append((key, prev, new_val))
                else:
                    # large upward jump → require persistence
                    pend = self._stats_pending[key]
                    if pend == new_val:
                        self._stats_pending_count[key] += 1
                    else:
                        self._stats_pending[key] = new_val
                        self._stats_pending_count[key] = 1

                    if self._stats_pending_count[key] >= PERSIST_FRAMES:
                        current[key] = new_val
                        changed.append((key, prev, new_val))
                        logger_uma.debug(f"[stats] {key}: accepted confirmed big jump {prev}->{new_val} (Δ={delta})")
                        self._stats_pending[key] = None
                        self._stats_pending_count[key] = 0
                    else:
                        logger_uma.debug(
                            f"[stats] {key}: holding big jump {prev}->{new_val} (Δ={delta}); "
                            f"need {PERSIST_FRAMES - self._stats_pending_count[key]} more confirm(s)"
                        )

            # commit
            self.state.stats = current
            if changed:
                chs = ", ".join(f"{k}:{a}->{b}" for k, a, b in changed)
                logger_uma.info(f"[stats] update: {chs}")
        else:
            logger_uma.debug("[Optimization] Reusing previously calculated stats until new refresh interval")
            time.sleep(1.2)

        # advance counter
        self._stats_refresh_counter += 1

    def _update_state(self, img, dets) -> None:
        # Skill points, goal & energy
        self.state.skill_pts = extract_skill_points(self.ocr, img, dets)
        self.state.goal = extract_goal_text(self.ocr, img, dets)
        self.state.energy = extract_energy_pct(self.ocr, img, dets)

        self._update_stats(img, dets)
        # Turns & career date parsing
        self._process_turns_left(img, dets)
        self._process_date_info(img, dets)
        # Infirmary & mood
        self.state.infirmary_on = extract_infirmary_on(img, dets, threshold=0.60)
        self.state.mood = extract_mood(self.ocr, img, dets, conf_min=0.3)

    def _process_date_info(self, img, dets) -> None:
        """
        1) OCR -> raw string
        2) Parse to DateInfo (may be partial)
        3) Accept only if not earlier than current state (monotonic)
        4) Merge missing fields sensibly; compute is_summer
        5) Keep last candidate for debugging/telemetry
        """
        raw = extract_career_date(self.ocr, img, dets)
        cand = parse_career_date(raw) if raw else None

        prev: Optional[DateInfo] = getattr(self.state, "date_info", None)

        # Store for debugging even if we reject
        self.state.career_date_raw = raw

        # If nothing parsed, do nothing (keep previous stable)
        if cand is None:
            logger_uma.debug("Date OCR parse failed; keeping previous date_info unchanged.")
            return

        # If we already reached Final Season, only accept Final→Final
        if date_is_terminal(prev):
            if cand.year_code == 4:
                self.state.date_info = cand
                self.state.is_summer = is_summer(cand)
            else:
                logger_uma.debug("Ignoring non-final date after Final Season lock.")
            return

        # Pre-debut handling: allow 0→(1..3/4), but never accept (1..3)→0
        if prev and date_is_regular_year(prev) and date_is_pre_debut(cand):
            logger_uma.debug(f"Ignoring backward date {cand.as_key()} after {prev.as_key()}.")
            return

        # Monotonic acceptance
        if not prev:
            # First observation: accept even if partial
            accepted = cand
            reason = "initial"
        else:
            cmp = date_cmp(cand, prev)
            if cmp < 0:
                # candidate is earlier -> reject
                logger_uma.debug(f"Rejecting earlier date: {cand.as_key()} < {prev.as_key()}")
                return

            # (Optional) sanity guard against gigantic jumps in one frame
            idx_prev = date_index(prev)
            idx_new  = date_index(cand)
            if (idx_prev is not None and idx_new is not None) and (idx_new - idx_prev > 6):
                
                if str(prev.as_key()).strip() == 'Y3-Dec-2' and str(cand.year_code) == 'Y4':
                    # ok change to final season
                    pass
                else:
                    # more than ~3 months (6 halves) in one hop → likely OCR glitch; require persistence
                    logger_uma.debug(
                        f"Suspicious jump {prev.as_key()} -> {cand.as_key()} (Δ={idx_new - idx_prev}). "
                        "Holding previous; will accept if persists on next frame."
                    )
                    # You can remember this candidate and require 2 consecutive hits to accept.
                    self._pending_date_jump = cand
                    return
            # If we stored a pending jump and it repeats, accept now
            if hasattr(self, "_pending_date_jump") and self._pending_date_jump:
                if date_cmp(cand, self._pending_date_jump) == 0:
                    reason = "confirmed jump"
                    accepted = cand
                    self._pending_date_jump = None
                else:
                    reason = "monotonic (no pending)"
                    accepted = cand
                    self._pending_date_jump = None
            else:
                reason = "monotonic"
                accepted = cand

        # Merge missing fields with previous when compatible (keeps half when month unchanged)
        merged = date_merge(prev, accepted)

        # Commit to state
        self.state.date_info = merged
        self.state.is_summer = is_summer(merged) if merged else None

        prev_key  = prev.as_key() if prev else "None"
        merged_key = merged.as_key() if merged else "None"
        logger_uma.debug(f"[date] prev: {prev}. Cand: {cand}. accepted: {accepted}")
        logger_uma.info(f"[date] {reason}: {prev_key} -> {merged_key}")

        # If OCR produced the same compact key (no visible change) advance the date by +1 half.
        # Examples:
        #   Y1-Jun-1 -> Y1-Jun-2
        #   Y2-Dec-2 -> Y3-Jan-1
        #   Y3-Dec-2 -> Y4 (Final Season)
        try:
            if merged_key == prev_key and self.state.date_info and self.state.date_info.year_code not in (0, 4):
                di = self.state.date_info
                if di.year_code in (1, 2, 3) and (di.month is not None) and (di.half in (1, 2)):
                    y, m, h = di.year_code, int(di.month), int(di.half)
                    if h == 1:
                        # Early -> Late (same month)
                        new_y, new_m, new_h = y, m, 2
                    else:
                        # Late -> Early next month/year (or Final Season after Y3-Dec-2)
                        if m == 12:
                            if y in (1, 2):
                                new_y, new_m, new_h = y + 1, 1, 1
                                logger_uma.info("Naive date update, adding +1 half +1 year and reset")
                            else:
                                # Senior Late Dec -> Final Season (no month/half)
                                self.state.date_info = DateInfo(raw=di.raw, year_code=4, month=None, half=None)
                                self.state.is_summer = is_summer(self.state.date_info)
                                logger_uma.info("[date] No change detected; auto-advanced half: %s -> Y4", merged_key)
                                return
                        else:
                            new_y, new_m, new_h = y, m + 1, 1

                    advanced = DateInfo(raw=di.raw, year_code=new_y, month=new_m, half=new_h)
                    self.state.date_info = advanced
                    self.state.is_summer = is_summer(advanced)
                    logger_uma.info("[date] No change detected; auto-advanced half: %s -> %s",
                                    merged_key, advanced.as_key())
        except Exception as _adv_e:
            logger_uma.debug(f"[date] auto-advance skipped due to error: {_adv_e}")

    def _plan_race_today(self) -> None:
        """
        Decide (and cache) whether today has a planned race; explicit date->name
        in Settings.RACES wins over PRIORITIZE_G1 detection.
        """
        di = self.state.date_info
        key = date_key_from_dateinfo(di) if di else None
        self._last_date_key = key
        self.state.planned_race_name = None
        if not key:
            return

        # 1) explicit plan wins
        if key in self.plan_races:
            name = str(self.plan_races[key]).strip()
            if not RaceIndex.valid_date_for_race(name, key):
                logger_uma.warning(
                    "[lobby] RACES plan '%s' is not present on %s in dataset; "
                    "will attempt OCR match anyway.", name, key
                )
            self.state.planned_race_name = name
            return

    def _process_turns_left(self, img, dets):
        new_turn = extract_turns(self.ocr, img, dets)
        if new_turn != -1:

            ref_turn = self.last_turns_left_prediction or self.state.turn or -1
            diff = abs(ref_turn - new_turn)
            if diff < 5 or ref_turn == -1 or self.state.turn <= 2:
                # accept only if new change is not to big, or if last detected turn was near to finish turns left
                self.state.turn = new_turn
            elif self.state.turn > 1:
                logger_uma.debug(f"Naive prediction. Last turn was: {self.state.turn}, so now it should be at most {self.state.turn - 1}")
                self.state.turn -= 1
        elif self.state.turn > 0:
            # Naive prediction
            logger_uma.debug(f"Naive prediction. Last turn was: {self.state.turn}, so now it should be at most {self.state.turn - 1}")
            self.state.turn -= 1
        self.last_turns_left_prediction = new_turn

    def _maybe_do_goal_race(self, img, dets) -> bool:
        """Implements the critical-goal race logic from your old Lobby branch."""

        if self.process_on_demand:
            self.state.goal = extract_goal_text(self.ocr, img, dets)
            self._process_turns_left(img, dets)

        goal = (self.state.goal or "").lower()

        there_is_progress_text = fuzzy_contains(goal, "progress", threshold=0.58)
        critical_goal_fans = (
            there_is_progress_text
            or (fuzzy_contains(goal, "go", 0.58) and fuzzy_contains(goal, "fan", 0.58) and not fuzzy_contains(goal, "achieve", 0.58))
        )
        critical_goal_g1 = there_is_progress_text and (
            (fuzzy_contains(goal, "g1", 0.58) or fuzzy_contains(goal, "gl", 0.58))
            or fuzzy_contains(goal, "place within", 0.58)
            or (fuzzy_contains(goal, "place", 0.58) and fuzzy_contains(goal, "top", 0.58) and fuzzy_contains(goal, "time", 0.58))
        )

        # Skip racing right at the first junior date (matching your original constraint)
        is_first_junior_date = (
            bool(self.state.date_info)
            and self.state.date_info.year_code == 1
            and self.state.date_info.month == 7
            and self.state.date_info.half == 1
        )

        if is_first_junior_date or self._skip_race_once:
            return False, "It is first day, no races available"

        if self.state.turn <= self.max_critical_turn:
            # Critical G1
            if critical_goal_g1:
                return True, f"[lobby] Critical goal G1 | turn={self.state.turn}"
            # Critical Fans
            elif critical_goal_fans:
                return True, f"[lobby] Critical goal FANS | turn={self.state.turn}"

        return False, "Unknown"

    # --------------------------
    # Click helpers (Lobby targets)
    # --------------------------
    def _go_rest(self, *, reason: str) -> bool:
        logger_uma.info(f"[lobby] {reason}")
        # Prefer explicit REST; if summer, also accept the summer rest tile
        click = self.waiter.click_when(
            classes=("lobby_rest", "lobby_rest_summer"),
            prefer_bottom=True,
            timeout_s=2.5,
            tag="lobby_rest",
        )
        if click:
            time.sleep(3)
        return click

    def _go_recreate(self, *, reason: str = "Mood is low, recreating") -> bool:
        logger_uma.info(f"[lobby] {reason}")
        click = self.waiter.click_when(
            classes=("lobby_recreation", "lobby_rest_summer"),
            prefer_bottom=True,
            timeout_s=2.5,
            tag="lobby_recreate",
        )
        if click:
            time.sleep(3)
        return click

    def _go_skills(self) -> bool:
        logger_uma.info("[lobby] Opening Skills")
        clicked = self.waiter.click_when(
            classes=("lobby_skills",),
            prefer_bottom=True,
            timeout_s=2.5,
            tag="lobby_skills",
        )
        if clicked:
            time.sleep(1)
        return clicked

    def _go_infirmary(self) -> bool:
        logger_uma.info("[lobby] Infirmary ON → going to infirmary")
        click = self.waiter.click_when(
            classes=("lobby_infirmary",),
            prefer_bottom=True,
            timeout_s=2.5,
            tag="lobby_infirmary",
        )
        if click:
            time.sleep(2)
        return click

    def _go_training_screen_from_lobby(self, img, dets) -> bool:
        logger_uma.info("[lobby] No critical actions → go Train")
        clicked = self.waiter.click_when(
            classes=("lobby_training",),
            prefer_bottom=True,
            timeout_s=2.5,
            tag="lobby_training",
        )
        clicked = True
        if clicked:
            # This replaces a time.sleep... time.sleep(1.2)
            # If the machine is ultra powerful, then you should neet a time.sleep(1.2)
            # Meanwhile we wait for animation we calculate stats
            # TODO: PROCESS IN PARALLEL
            if self.process_on_demand and dets is not None:
                self._update_stats(img, dets)
                self._stats_refresh_counter += 1
            
        return clicked

    def _go_back(self) -> bool:
        # Minimal, OCR-gated BACK
        ok = self.waiter.click_when(
            classes=("button_white",),
            texts=("BACK",),
            prefer_bottom=True,
            timeout_s=2.0,
            tag="lobby_back",
        )
        if ok:
            logger_uma.info("[lobby] GO BACK")
            time.sleep(0.4)
        return ok
