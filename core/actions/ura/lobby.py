# core/actions/lobby.py
from __future__ import annotations

from collections import deque
import statistics
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
    extract_turns,
)
from core.perception.is_button_active import ActiveButtonClassifier
from core.perception.yolo.interface import IDetector
from core.settings import Settings
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
    parse_career_date,
    date_is_confident,
)
@dataclass
class LobbyState:
    goal: Optional[str] = None
    energy: Optional[int] = None
    skill_pts: int = 0
    infirmary_on: Optional[bool] = None
    turn: int = -1
    career_date_raw: Optional[str] = None
    date_info: Optional[DateInfo] = None
    is_summer: Optional[bool] = None
    mood: Tuple[str, float] = ("UNKNOWN", -1.0)
    stats = {"SPD": -1, "STA": -1, "PWR": -1, "GUTS": -1, "WIT": -1}
    planned_race_name: Optional[str] = None
    planned_race_canonical: Optional[str] = None



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
        yolo_engine: IDetector,
        waiter: Waiter,
        *,
        minimum_skill_pts: int = 500,
        auto_rest_minimum: int = 24,
        prioritize_g1: bool = False,
        process_on_demand=True,
        interval_stats_refresh=1,
        max_critical_turn=8,
        plan_races={},
    ) -> None:
        self.ctrl = ctrl
        self.ocr = ocr
        self.yolo_engine = yolo_engine
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
        self._date_stable_count: int = (
            0  # how long current accepted date has been stable
        )
        self._date_artificial: bool = (
            False  # last accepted date was auto-advanced (imputed)
        )
        self._pending_date_jump = (
            None  # keep forward pending (exists already in codepath)
        )
        self._pending_date_back = None  # pending backward correction candidate
        self._pending_date_back_count: int = 0
        self._last_turn_at_date_update: Optional[int] = (
            None  # turns value when we last updated date
        )
        self._raced_keys_recent: set[str] = (
            set()
        )  # keys we already raced on (avoid double-race if OCR didn’t tick)
        self._skip_guard_key: Optional[str] = None  # date key that armed skip guard

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
        img, dets = collect(
            self.yolo_engine,
            imgsz=self.waiter.cfg.imgsz,
            conf=self.waiter.cfg.conf,
            iou=self.waiter.cfg.iou,
            tag="lobby_state",
        )

        if not self.process_on_demand:
            self._update_state(
                img, dets
            )  # -> Very expensive, calculate as you need better

        # --- Critical goal logic & early racing opportunities ---

        if self.process_on_demand:
            self._process_date_info(img, dets)
            logger_uma.info(
                f"Date: {self.state.date_info} | raw: {self.state.career_date_raw}"
            )

        if self.process_on_demand:
            self.state.energy = extract_energy_pct(img, dets)

        # --- Race planning (explicit list takes precedence; else G1 if available) ---
        self._plan_race_today()

        current_date_key = (
            date_key_from_dateinfo(self.state.date_info)
            if self.state and getattr(self.state, "date_info", None)
            else None
        )
        if (
            self._skip_race_once
            and self._skip_guard_key
            and current_date_key
            and current_date_key != self._skip_guard_key
        ):
            logger_uma.info(
                "[planned_race] skip guard released: %s -> %s",
                self._skip_guard_key,
                current_date_key,
            )
            self._skip_race_once = False
            self._skip_guard_key = None

        # If we have a planned race today, go race (subject to early-guard rules)
        if self.state.planned_race_name:
            # First-Junior-Day guard (no races available there)
            is_first_junior_date = (
                bool(self.state.date_info)
                and date_is_confident(self.state.date_info)
                and self.state.date_info.year_code == 1
                and self.state.date_info.month == 7
                and self.state.date_info.half == 1
            )
            guard_extra = {
                "first_junior": is_first_junior_date,
                "skip_guard": self._skip_race_once,
            }
            self._log_planned_race_decision(
                action="guard_evaluate",
                plan_name=self.state.planned_race_name,
                extra=guard_extra,
            )
            if not is_first_junior_date and not self._skip_race_once:
                reason = f"Planned race: {self.state.planned_race_name}"
                self._log_planned_race_decision(
                    action="enter_race",
                    plan_name=self.state.planned_race_name,
                    reason="guard_passed",
                    extra=guard_extra,
                )
                self._skip_race_once = False
                return "TO_RACE", reason
            else:
                suppression_reasons = []
                if is_first_junior_date:
                    suppression_reasons.append("first_junior_date")
                if self._skip_race_once:
                    suppression_reasons.append("skip_guard")
                self._log_planned_race_decision(
                    action="guard_suppressed",
                    plan_name=self.state.planned_race_name,
                    reason=",".join(suppression_reasons) or "unknown",
                    extra=guard_extra,
                )
                logger_uma.debug(
                    "[lobby] Planned race suppressed by first-junior-day/skip flag."
                )
            self._skip_race_once = False
            self._skip_guard_key = None

        if self.process_on_demand:
            self._process_turns_left(img, dets)

        if self.state.turn <= self.max_critical_turn:
            if not self._skip_race_once and self.state.energy is not None and self.state.energy > 2:
                # [Optimization] 10 steps for goal, or unknown turns or -1 turns, check goal
                outcome_bool, reason = self._maybe_do_goal_race(img, dets)
                if outcome_bool:
                    return "TO_RACE", reason

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
                reason = f"Energy too low, resting: auto_rest_minimum={self.auto_rest_minimum}"
                if self._go_rest(reason=reason):
                    return "RESTED", reason
            elif (
                self.state.energy <= 50
                and self.state.date_info
                and is_summer_in_two_or_less_turns(self.state.date_info)
            ):
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
        Smart, monotonic-ish stat updater with refresh gating, noise guards,
        and recovery from early misreads.

        Rules (per stat key in {SPD, STA, PWR, GUTS, WIT}):
          - Ignore invalid reads (-1) and out-of-range values.
          - If previous is -1, accept the first valid value.
          - Accept normal increases up to MAX_UP_STEP per refresh.
          - For larger upward jumps, require the same value to repeat
            PERSIST_FRAMES times before accepting (prevents OCR spikes),
            EXCEPT during a short warm-up window or if the previous value was
            artificial (imputed) — in those cases accept immediately to fix
            early misreads like 103→703.
          - Allow small decreases up to MAX_DOWN_STEP (rare debuffs / wobble).
          - If at least one of the 5 stats is still -1, force a refresh even
            if we are between interval gates.
          - If a stat remains -1 while others are valid, fill it with the
            average of the known ones and mark it *artificial* so any later
            real read will overwrite it unconditionally.
        """
        KEYS = ("SPD", "STA", "PWR", "GUTS", "WIT")
        STAT_MIN, STAT_MAX = 0, 1200
        MAX_UP_STEP = 150  # typical per-turn cap; tune if you see legit bigger jumps
        MAX_DOWN_STEP = 60  # allow tiny decreases; block bigger drops
        PERSIST_FRAMES_UP = 2  # confirm large upward jumps across this many refreshes
        PERSIST_FRAMES_DOWN = (
            2  # confirm large downward corrections across this many refreshes
        )
        WARMUP_FRAMES = 2  # after accepting a value, allow big fixes for a few frames
        SUSPECT_FRAMES = 5  # after a big upward jump is accepted, allow big downward correction for a while
        HIST_LEN = 5  # how many recent raw reads to keep per stat
        CORR_TOL = 80  # tolerance near baseline/median to treat as a correction (not a real drop)

        # lazy init of helper state
        if not hasattr(self, "_stats_last_pred"):
            self._stats_last_pred = {k: -1 for k in KEYS}  # last raw OCR per key
        if not hasattr(self, "_stats_pending"):  # pending large jump candidates
            self._stats_pending = {k: None for k in KEYS}
        # pending big downward corrections
        if not hasattr(self, "_stats_pending_down"):
            self._stats_pending_down = {k: None for k in KEYS}
        if not hasattr(self, "_stats_pending_down_count"):
            self._stats_pending_down_count = {k: 0 for k in KEYS}
        if not hasattr(self, "_stats_pending_count"):
            self._stats_pending_count = {k: 0 for k in KEYS}
        if not hasattr(self, "_stats_stable_count"):
            # how long the currently accepted value has been kept
            self._stats_stable_count = {k: 0 for k in KEYS}
        if not hasattr(self, "_stats_artificial"):
            # keys whose current value was imputed (avg). Real reads must overwrite immediately.
            self._stats_artificial = set()
        # track "suspect" state after accepting a big upward jump
        if not hasattr(self, "_stats_suspect_until"):
            self._stats_suspect_until = {k: 0 for k in KEYS}
        if not hasattr(self, "_stats_prejump_value"):
            self._stats_prejump_value = {k: None for k in KEYS}
        # small history of raw valid reads to compute medians
        if not hasattr(self, "_stats_history"):
            self._stats_history = {k: deque(maxlen=HIST_LEN) for k in KEYS}

        # Refresh gating (preserve optimization) + force if any unknowns
        any_missing = any((self.state.stats or {}).get(k, -1) == -1 for k in KEYS)
        if (
            self._stats_refresh_counter == 0
            or self._stats_refresh_counter % self.interval_stats_refresh == 0
            or any_missing
        ):
            observed = extract_stats(self.ocr, img, dets)  # dict[str,int]
            current = dict(self.state.stats or {})  # copy to modify safely
            prev_snapshot = dict(current)
            changed = []

            for key in KEYS:
                new_val = int(observed.get(key, -1))
                prev = int(current.get(key, -1))
                prev_was_artificial = key in self._stats_artificial

                # remember last prediction for debugging/telemetry
                self._stats_last_pred[key] = new_val

                # reject invalids early
                if new_val < STAT_MIN or new_val > STAT_MAX:
                    continue
                if new_val == -1:
                    logger_uma.debug(
                        f"[stats] {key}: invalid read (-1), keeping {prev}"
                    )
                    continue
                # keep history of valid raw reads
                self._stats_history[key].append(new_val)
                if prev == -1:
                    # first valid observation
                    current[key] = new_val
                    self._stats_artificial.discard(key)
                    self._stats_pending[key] = None
                    self._stats_pending_count[key] = 0
                    self._stats_pending_down[key] = None
                    self._stats_pending_down_count[key] = 0
                    self._stats_stable_count[key] = 0
                    self._stats_suspect_until[key] = 0
                    self._stats_prejump_value[key] = None
                    changed.append((key, -1, new_val))
                    continue

                delta = new_val - prev

                # small negative change allowed; big drop rejected
                if delta < 0:
                    drop = abs(delta)
                    if drop <= MAX_DOWN_STEP:
                        current[key] = new_val
                        self._stats_artificial.discard(key)
                        self._stats_pending[key] = None
                        self._stats_pending_count[key] = 0
                        self._stats_pending_down[key] = None
                        self._stats_pending_down_count[key] = 0
                        self._stats_stable_count[key] = 0
                        self._stats_suspect_until[key] = max(
                            0, self._stats_suspect_until[key] - 1
                        )
                        changed.append((key, prev, new_val))
                    else:
                        # Large downward move. Treat as a possible correction if:
                        #  - previous was artificial, OR
                        #  - we are inside a suspect window after a big upward jump
                        #    and the new value is close to the pre-jump baseline, OR
                        #  - it persists across a few frames and is closer to the median of recent raw reads.
                        accept = False
                        reason = "blocked"

                        if prev_was_artificial:
                            accept, reason = True, "prev artificial"
                        elif self._stats_suspect_until.get(key, 0) > 0:
                            base = self._stats_prejump_value.get(key, prev)
                            if (
                                base is not None
                                and abs(new_val - int(base)) <= CORR_TOL
                            ):
                                accept, reason = (
                                    True,
                                    f"suspect-window correction to ~{base}",
                                )
                        else:
                            # persistence gate + median support
                            pend = self._stats_pending_down[key]
                            if pend == new_val:
                                self._stats_pending_down_count[key] += 1
                            else:
                                self._stats_pending_down[key] = new_val
                                self._stats_pending_down_count[key] = 1
                            if (
                                self._stats_pending_down_count[key]
                                >= PERSIST_FRAMES_DOWN
                            ):
                                med = (
                                    statistics.median(self._stats_history[key])
                                    if self._stats_history[key]
                                    else new_val
                                )
                                if abs(new_val - med) <= CORR_TOL or abs(
                                    prev - med
                                ) > abs(new_val - med):
                                    accept, reason = (
                                        True,
                                        f"median≈{int(med)} persistence",
                                    )

                        if accept:
                            current[key] = new_val
                            self._stats_artificial.discard(key)
                            self._stats_pending[key] = None
                            self._stats_pending_count[key] = 0
                            self._stats_pending_down[key] = None
                            self._stats_pending_down_count[key] = 0
                            self._stats_stable_count[key] = 0
                            self._stats_suspect_until[key] = 0
                            self._stats_prejump_value[key] = None
                            changed.append((key, prev, new_val))
                            logger_uma.debug(
                                f"[stats] {key}: accepted big downward correction {prev}->{new_val} ({reason})"
                            )
                        else:
                            logger_uma.debug(
                                f"[stats] {key}: holding large drop {prev}->{new_val} (Δ={delta})"
                            )
                    continue

                # non-negative delta
                if delta <= MAX_UP_STEP:
                    # normal progression
                    current[key] = new_val
                    self._stats_artificial.discard(key)
                    self._stats_pending[key] = None
                    self._stats_pending_count[key] = 0
                    self._stats_pending_down[key] = None
                    self._stats_pending_down_count[key] = 0
                    self._stats_stable_count[key] = 0
                    # normal moves are not "suspect"
                    self._stats_suspect_until[key] = max(
                        0, self._stats_suspect_until[key] - 1
                    )

                    changed.append((key, prev, new_val))
                else:
                    # large upward jump
                    # Accept immediately if:
                    #  - we are in warm-up for this key (value just accepted recently), or
                    #  - the previous value was artificial (imputed placeholder).
                    if (
                        self._stats_stable_count.get(key, 0) < WARMUP_FRAMES
                        or prev_was_artificial
                    ):
                        current[key] = new_val
                        self._stats_artificial.discard(key)
                        self._stats_pending[key] = None
                        self._stats_pending_count[key] = 0
                        self._stats_pending_down[key] = None
                        self._stats_pending_down_count[key] = 0
                        self._stats_stable_count[key] = 0
                        # Mark as suspect so we can accept a later big correction down.
                        self._stats_suspect_until[key] = SUSPECT_FRAMES
                        self._stats_prejump_value[key] = prev
                        changed.append((key, prev, new_val))
                        logger_uma.debug(
                            f"[stats] {key}: accepted big correction {prev}->{new_val} (Δ={delta})"
                        )
                    else:
                        # require persistence
                        pend = self._stats_pending[key]
                        if pend == new_val:
                            self._stats_pending_count[key] += 1
                        else:
                            self._stats_pending[key] = new_val
                            self._stats_pending_count[key] = 1

                        if self._stats_pending_count[key] >= PERSIST_FRAMES_UP:
                            current[key] = new_val
                            changed.append((key, prev, new_val))
                            logger_uma.debug(
                                f"[stats] {key}: accepted confirmed big jump {prev}->{new_val} (Δ={delta})"
                            )
                            self._stats_pending[key] = None
                            self._stats_pending_count[key] = 0
                            self._stats_stable_count[key] = 0
                            self._stats_artificial.discard(key)
                            # big confirmed upward jump → open suspect window
                            self._stats_suspect_until[key] = SUSPECT_FRAMES
                            self._stats_prejump_value[key] = prev
                        else:
                            logger_uma.debug(
                                f"[stats] {key}: holding big jump {prev}->{new_val} (Δ={delta}); "
                                f"need {PERSIST_FRAMES_UP - self._stats_pending_count[key]} more confirm(s)"
                            )

            # If some stats are still unknown, impute with the average of known ones
            missing_keys = [k for k in KEYS if current.get(k, -1) == -1]
            known_vals = [current[k] for k in KEYS if current.get(k, -1) != -1]
            if missing_keys and known_vals:
                avg_val = int(round(sum(known_vals) / max(1, len(known_vals))))
                avg_val = max(STAT_MIN, min(STAT_MAX, avg_val))
                for k in missing_keys:
                    current[k] = avg_val
                    self._stats_artificial.add(k)
                logger_uma.debug(f"[stats] imputed {missing_keys} with avg={avg_val}")

            # update stability counters (keys that didn’t change grow older)
            for k in KEYS:
                if current.get(k, -1) != -1 and current.get(k) == prev_snapshot.get(k):
                    self._stats_stable_count[k] = self._stats_stable_count.get(k, 0) + 1
                else:
                    # when a value changes, shrink suspect window a bit
                    if self._stats_suspect_until.get(k, 0) > 0:
                        self._stats_suspect_until[k] = max(
                            0, self._stats_suspect_until[k] - 1
                        )

            # commit
            self.state.stats = current
            if changed:
                chs = ", ".join(f"{k}:{a}->{b}" for k, a, b in changed)
                logger_uma.info(f"[stats] update: {chs}")

        else:
            logger_uma.debug(
                "[Optimization] Reusing previously calculated stats until new refresh interval"
            )
            time.sleep(1.2)

        # advance counter
        self._stats_refresh_counter += 1

    def _update_state(self, img, dets) -> None:
        # Skill points, goal & energy
        self.state.skill_pts = extract_skill_points(self.ocr, img, dets)
        self.state.goal = extract_goal_text(self.ocr, img, dets)
        self.state.energy = extract_energy_pct(img, dets)

        self._update_stats(img, dets)
        # Turns & career date parsing
        self._process_turns_left(img, dets)
        self._process_date_info(img, dets)
        # Infirmary & mood
        self.state.infirmary_on = extract_infirmary_on(img, dets, threshold=0.60)
        self.state.mood = extract_mood(self.ocr, img, dets, conf_min=0.3)

    def _process_date_info(self, img, dets) -> None:
        """
        Robust date updater with:
          • Warm-up acceptance for backward corrections (like stats big-jump fix).
          • 'Artificial' flag to allow overwriting auto-advanced dates.
          • Turn-aware auto-advance when OCR returns nothing but a day was consumed.
        """
        WARMUP_FRAMES = 2
        PERSIST_FRAMES = 2
        MAX_SUSP_JUMP_HALVES = 6  # same spirit as forward jump guard
        raw = extract_career_date(self.ocr, img, dets)
        cand = parse_career_date(raw) if raw else None

        prev: Optional[DateInfo] = getattr(self.state, "date_info", None)

        # Store for debugging even if we reject
        self.state.career_date_raw = raw

        # If OCR produced nothing, consider turn-based auto-advance (day consumed)
        if cand is None:
            logger_uma.debug("Date OCR parse failed/empty.")
            if prev and (prev.year_code in (1, 2, 3)):
                try:
                    curr_turn = int(self.state.turn)
                except Exception:
                    curr_turn = -1
                lt = self._last_turn_at_date_update
                # day likely progressed if turns decreased since last accepted date
                if (lt is not None) and (curr_turn >= 0) and (curr_turn < lt):
                    di = prev
                    # advance by +1 half safely (reuse same logic as below)
                    y, m, h = di.year_code, di.month, di.half
                    advanced: Optional[DateInfo] = None
                    if y in (1, 2, 3) and (m is not None):
                        if h == 1:
                            advanced = DateInfo(
                                raw=di.raw, year_code=y, month=m, half=2
                            )
                        else:
                            if m == 12:
                                if y in (1, 2):
                                    advanced = DateInfo(
                                        raw=di.raw, year_code=y + 1, month=1, half=1
                                    )
                                else:
                                    # Senior Late Dec -> Final Season
                                    advanced = DateInfo(
                                        raw=di.raw, year_code=4, month=None, half=None
                                    )
                            else:
                                advanced = DateInfo(
                                    raw=di.raw, year_code=y, month=m + 1, half=1
                                )
                    if advanced:
                        self.state.date_info = advanced
                        self.state.is_summer = is_summer(advanced)
                        self._date_stable_count = 0
                        self._date_artificial = True
                        self._last_turn_at_date_update = curr_turn
                        # new key → clear raced-today memory
                        new_key = self.state.date_info.as_key()
                        if new_key != self._last_date_key:
                            self._raced_keys_recent.clear()
                            self._last_date_key = new_key
                        logger_uma.info(
                            "[date] Auto-advanced by turns: %s -> %s",
                            prev.as_key(),
                            advanced.as_key(),
                        )
                        return
            # Nothing to do, keep previous
            return

        # If we already reached Final Season, only accept Final→Final
        if date_is_terminal(prev):
            if cand.year_code == 4:
                self.state.date_info = cand
                self.state.is_summer = is_summer(cand)
                self._date_stable_count = 0
                self._date_artificial = False
                self._last_turn_at_date_update = (
                    self.state.turn if isinstance(self.state.turn, int) else None
                )
                # new key guard
                new_key = self.state.date_info.as_key()
                if new_key != self._last_date_key:
                    self._raced_keys_recent.clear()
                    self._last_date_key = new_key
            else:
                logger_uma.debug("Ignoring non-final date after Final Season lock.")
            return

        # Pre-debut handling: allow 0→(1..3/4), but never accept (1..3)→0
        if prev and date_is_regular_year(prev) and date_is_pre_debut(cand):
            logger_uma.debug(
                f"Ignoring backward date {cand.as_key()} after {prev.as_key()}."
            )
            return

        # Monotonic acceptance (with warm-up/backfix)
        if not prev:
            # First observation: accept even if partial
            accepted = cand
            reason = "initial"
        else:
            cmp = date_cmp(cand, prev)
            if cmp < 0:
                # Backward correction. Allow if we just accepted prev (warm-up) or prev was artificial.
                idx_prev = date_index(prev)
                idx_new = date_index(cand)
                big_back = (
                    (idx_prev is not None)
                    and (idx_new is not None)
                    and ((idx_prev - idx_new) > MAX_SUSP_JUMP_HALVES)
                )
                if self._date_artificial or (self._date_stable_count < WARMUP_FRAMES):
                    accepted = cand
                    reason = "backfix (warmup/artificial)"
                    self._pending_date_back = None
                    self._pending_date_back_count = 0
                else:
                    # require persistence for suspicious backward jumps
                    if big_back:
                        if (
                            self._pending_date_back
                            and date_cmp(cand, self._pending_date_back) == 0
                        ):
                            self._pending_date_back_count += 1
                        else:
                            self._pending_date_back = cand
                            self._pending_date_back_count = 1
                        need = PERSIST_FRAMES - self._pending_date_back_count
                        if self._pending_date_back_count >= PERSIST_FRAMES:
                            accepted = cand
                            reason = "backfix (confirmed)"
                            self._pending_date_back = None
                            self._pending_date_back_count = 0
                        else:
                            logger_uma.debug(
                                f"Holding backward jump {prev.as_key()} -> {cand.as_key()} ; need {need} confirm(s)"
                            )
                            return
                    else:
                        # small/backward but reasonable → accept
                        accepted = cand
                        reason = "backfix (small)"
            else:
                # cmp >= 0 → monotonic or equal; proceed
                pass
            # (Optional) sanity guard against gigantic jumps in one frame
            idx_prev = date_index(prev)
            idx_new = date_index(cand)
            if (idx_prev is not None and idx_new is not None) and (
                idx_new - idx_prev > 6
            ):
                # Legitimate boundary: Senior Dec (Early/Late) → Final Season
                if (
                    prev.year_code == 3
                    and prev.month == 12
                    and (prev.half in (1, 2) or prev.half is None)
                    and cand.year_code == 4
                ):
                    # Accept immediately (no persistence required).
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
        self._date_stable_count = 0
        # accepted from OCR → not artificial
        self._date_artificial = False
        self._last_turn_at_date_update = (
            self.state.turn if isinstance(self.state.turn, int) else None
        )
        # new key guard
        new_key_for_accept = merged.as_key() if merged else None
        if new_key_for_accept and new_key_for_accept != self._last_date_key:
            self._raced_keys_recent.clear()
            self._last_date_key = new_key_for_accept
        prev_key = prev.as_key() if prev else "None"
        merged_key = merged.as_key() if merged else "None"
        logger_uma.debug(f"[date] prev: {prev}. Cand: {cand}. accepted: {accepted}")
        logger_uma.info(f"[date] {reason}: {prev_key} -> {merged_key}")

        # If OCR produced the same compact key (no visible change) advance the date by +1 half.
        # Examples:
        #   Y1-Jun-1 -> Y1-Jun-2
        #   Y2-Dec-2 -> Y3-Jan-1
        #   Y3-Dec-2 -> Y4 (Final Season)
        try:
            # IF merged_key and prev_key are the same, probably the prediction now is correct
            if (
                merged_key == "None"
                and self.state.date_info
                and self.state.date_info.year_code not in (0, 4)
            ):
                di = self.state.date_info
                if (
                    di.year_code in (1, 2, 3)
                    and (di.month is not None)
                    and (di.half in (1, 2))
                ):
                    y, m, h = di.year_code, int(di.month), int(di.half)
                    if h == 1:
                        # Early -> Late (same month)
                        new_y, new_m, new_h = y, m, 2
                    else:
                        # Late -> Early next month/year (or Final Season after Y3-Dec-2)
                        if m == 12:
                            if y in (1, 2):
                                new_y, new_m, new_h = y + 1, 1, 1
                                logger_uma.info(
                                    "Naive date update, adding +1 half +1 year and reset"
                                )
                            else:
                                # Senior Late Dec -> Final Season (no month/half)
                                self.state.date_info = DateInfo(
                                    raw=di.raw, year_code=4, month=None, half=None
                                )
                                self.state.is_summer = is_summer(self.state.date_info)
                                logger_uma.info(
                                    "[date] No change detected; auto-advanced half: %s -> Y4",
                                    merged_key,
                                )
                                self._date_stable_count = 0
                                self._date_artificial = True
                                self._last_turn_at_date_update = (
                                    self.state.turn
                                    if isinstance(self.state.turn, int)
                                    else None
                                )
                                # new key → clear raced-today memory
                                if self.state.date_info.as_key() != self._last_date_key:
                                    self._raced_keys_recent.clear()
                                    self._last_date_key = self.state.date_info.as_key()

                                return
                        else:
                            new_y, new_m, new_h = y, m + 1, 1

                    advanced = DateInfo(
                        raw=di.raw, year_code=new_y, month=new_m, half=new_h
                    )

                    self.state.date_info = advanced
                    self.state.is_summer = is_summer(advanced)
                    self._date_stable_count = 0
                    self._date_artificial = True
                    self._last_turn_at_date_update = (
                        self.state.turn if isinstance(self.state.turn, int) else None
                    )
                    # new key → clear raced-today memory
                    if self.state.date_info.as_key() != self._last_date_key:
                        self._raced_keys_recent.clear()
                        self._last_date_key = self.state.date_info.as_key()

                    logger_uma.info(
                        "[date] No change detected; auto-advanced half: %s -> %s",
                        merged_key,
                        advanced.as_key(),
                    )
        except Exception as _adv_e:
            logger_uma.debug(f"[date] auto-advance skipped due to error: {_adv_e}")
        else:
            # If we got here without committing a new date (i.e., different accepted path),
            # increase stability counter.
            if self.state.date_info:
                self._date_stable_count += 1

    def _log_planned_race_decision(
        self,
        *,
        action: str,
        reason: Optional[str] = None,
        plan_name: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> None:
        di = getattr(self.state, "date_info", None)
        date_key = date_key_from_dateinfo(di) if di else None
        date_label = di.as_key() if di else None
        payload = [
            f"action={action}",
            f"plan={plan_name or self.state.planned_race_name or '-'}",
        ]
        if reason:
            payload.append(f"reason={reason}")
        payload.extend(
            [
                f"date_key={date_key or '-'}",
                f"date_label={date_label or '-'}",
                f"raw={self.state.career_date_raw or '-'}",
                f"skip={self._skip_race_once}",
                f"artificial={self._date_artificial}",
                f"stable={self._date_stable_count}",
                f"turn={self.state.turn}",
            ]
        )
        if extra:
            for key, value in extra.items():
                payload.append(f"{key}={value}")
        logger_uma.info("[planned_race] %s", " ".join(str(p) for p in payload))

    def _plan_race_today(self) -> None:
        """
        Decide (and cache) whether today has a planned race; explicit date->name
        in Settings.RACES wins over PRIORITIZE_G1 detection.
        """
        di = self.state.date_info
        key = date_key_from_dateinfo(di) if di else None
        self._last_date_key = key
        self.state.planned_race_name = None
        self.state.planned_race_canonical = None
        if not key:
            return

        # 1) explicit plan wins
        #    but skip if we already raced on this key (OCR didn’t tick yet)
        if (key in self.plan_races) and (key not in self._raced_keys_recent):
            raw_name = str(self.plan_races[key]).strip()
            canon = RaceIndex.canonicalize(raw_name)
            if not RaceIndex.valid_date_for_race(canon or raw_name, key):
                logger_uma.warning(
                    "[lobby] RACES plan '%s' is not present on %s in dataset; "
                    "will attempt OCR match anyway.",
                    raw_name,
                    key,
                )
            self.state.planned_race_name = raw_name
            self.state.planned_race_canonical = canon or raw_name.lower()
            self._log_planned_race_decision(
                action="plan_selected",
                plan_name=raw_name,
                extra={"already_raced": False},
            )
            return
        if key in self.plan_races and key in self._raced_keys_recent:
            name = str(self.plan_races[key]).strip()
            self._log_planned_race_decision(
                action="plan_already_completed",
                plan_name=name,
                extra={"already_raced": True},
            )
            return

        self._log_planned_race_decision(action="plan_missing_for_date", extra={"date_key": key})

    # Allow Agent to mark that we already raced for this date key
    def mark_raced_today(self, date_key: Optional[str]) -> None:
        if not date_key:
            return
        self._raced_keys_recent.add(date_key)
        # one-shot guard this loop as well
        self._skip_race_once = True
        self._skip_guard_key = date_key

    def _process_turns_left(self, img, dets):
        new_turn = extract_turns(self.ocr, img, dets)
        if new_turn != -1:
            ref_turn = self.last_turns_left_prediction or self.state.turn or -1
            diff = abs(ref_turn - new_turn)
            if diff < 5 or ref_turn == -1 or self.state.turn <= 2:
                # accept only if new change is not to big, or if last detected turn was near to finish turns left
                self.state.turn = new_turn
            elif self.state.turn > 1:
                logger_uma.debug(
                    f"Naive prediction. Last turn was: {self.state.turn}, so now it should be at most {self.state.turn - 1}"
                )
                self.state.turn -= 1
        elif self.state.turn > 0:
            # Naive prediction
            logger_uma.debug(
                f"Naive prediction. Last turn was: {self.state.turn}, so now it should be at most {self.state.turn - 1}"
            )
            self.state.turn -= 1
        self.last_turns_left_prediction = new_turn

    def _maybe_do_goal_race(self, img, dets) -> Tuple[bool, str]:
        """Implements the critical-goal race logic from your old Lobby branch."""

        if self.process_on_demand:
            self.state.goal = extract_goal_text(self.ocr, img, dets)

        goal = (self.state.goal or "").lower()

        there_is_progress_text = fuzzy_contains(goal, "progress", threshold=0.58)
        
        # Detect "Win Maiden race" or similar race-winning goals
        critical_goal_win_race = (
            fuzzy_contains(goal, "win", 0.58)
            and fuzzy_contains(goal, "maiden", 0.58)
            and fuzzy_contains(goal, "race", 0.58)
        )
        
        critical_goal_fans = there_is_progress_text or critical_goal_win_race or (
            fuzzy_contains(goal, "go", 0.58)
            and fuzzy_contains(goal, "fan", 0.58)
            and not fuzzy_contains(goal, "achieve", 0.58)
        )
        critical_goal_g1 = there_is_progress_text and (
            (fuzzy_contains(goal, "g1", 0.58) or fuzzy_contains(goal, "gl", 0.58))
            or fuzzy_contains(goal, "place within", 0.58)
            or (
                fuzzy_contains(goal, "place", 0.58)
                and fuzzy_contains(goal, "top", 0.58)
                and fuzzy_contains(goal, "time", 0.58)
            )
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
                return True, f"[lobby] Critical goal FANS/MAIDEN | turn={self.state.turn}"

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
            time.sleep(2)
            # Tazuna recreation screen possible elements: recreation_row, support_tazuna, button_white
            # Check if there are 2 recreation_row if that is the case click in the top first

            # Collect the current screen state
            img, dets = collect(
                self.yolo_engine,
                imgsz=self.waiter.cfg.imgsz,
                conf=self.waiter.cfg.conf,
                iou=self.waiter.cfg.iou,
                tag="recreation_screen"
            )
            
            # Check for recreation rows in detections
            recreation_rows = [d for d in dets if d.get('name') == 'recreation_row']
            
            if recreation_rows:
                # Sort rows by y-coordinate (top to bottom)
                recreation_rows.sort(key=lambda r: r['xyxy'][1])
                
                # Try each row until we find an active one or run out of rows
                for row in recreation_rows:                    
                    # Check if the row is active
                    crop = img.crop(row['xyxy'])
                    clf = ActiveButtonClassifier.load(Settings.IS_BUTTON_ACTIVE_CLF_PATH)
                    is_active = clf.predict(crop)
                    
                    if is_active:
                        # Click the active row
                        self.ctrl.click_xyxy_center(row['xyxy'])
                        logger_uma.info("[lobby] Selected active recreation row")
                        time.sleep(0.5)  # Wait for any animation
                        break
                    else:
                        logger_uma.info("[lobby] Skipping inactive recreation row")
                
            time.sleep(2)
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
            # After back, wait for animation to end
            time.sleep(1)
        return ok
