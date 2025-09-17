# core\actions\training_policy.py
from __future__ import annotations

import enum
import random
import re
from dataclasses import dataclass
from time import sleep
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image
from core.actions.training_check import compute_support_values, scan_training_screen
from core.constants import DEFAULT_TILE_TO_TYPE, MOOD_MAP
from core.utils.date_uma import DateInfo, is_final_season, is_junior_year, is_pre_debut, is_summer, is_summer_in_next_turn, is_summer_in_two_or_less_turns, near_mood_up_event, parse_career_date
from core.utils.logger import logger_uma
from core.settings import Constants
from core.utils.race_index import RaceIndex, date_key_from_dateinfo

# ---------- Action Enum ----------


class TrainAction(enum.Enum):
    """Atomic decisions for the training turn."""

    # Tile-targeting actions (return a tile_idx)
    TRAIN_MAX = "train_max"  # train the highest-SV tile (risk-allowed)
    TRAIN_WIT = "train_wit"  # specifically train WIT tile
    TRAIN_DIRECTOR = "train_director"  # train where Director is (special rule)
    TAKE_HINT = "take_hint"  # train any tile that has a hint

    # Non-tile actions (tile_idx=None)
    REST = "rest"
    RECREATION = "recreation"
    RACE = "race"
    SECURE_SKILL = "secure_skill"  # late-game safety: ensure 1200/600
    NOOP = "noop"  # fallback (should not normally happen)


# ---------- Date parsing & helpers ----------

def normalize_mood(mood: object) -> Tuple[str, int]:
    """
    Accepts either 'GOOD' or ('GOOD', 4) and returns ('GOOD', 4).
    """
    if isinstance(mood, (tuple, list)) and len(mood) >= 1:
        mtxt = str(mood[0]).upper()
        return (mtxt, MOOD_MAP.get(mtxt, -1))
    mtxt = str(mood).upper()
    return (mtxt, MOOD_MAP.get(mtxt, -1))


# ---------- Tile selection utilities ----------
def _best_tile(
    sv_rows: List[Dict],
    *,
    allowed_only: bool = True,
    min_sv: float = -1.0,
    prefer_types: Optional[Sequence[str]] = None,
    tile_to_type: Optional[Dict[int, str]] = None,
) -> Optional[int]:
    """
    Return the tile_idx with the highest SV (risk-allowed, if requested).
    Tie-break with prefer_types order if provided.
    """
    tile_to_type = tile_to_type or DEFAULT_TILE_TO_TYPE
    rows = [r for r in sv_rows if (r.get("sv_total", 0.0) >= min_sv)]
    if allowed_only:
        rows = [r for r in rows if r.get("allowed_by_risk", False)]

    if not rows:
        return None

    # Primary sort: SV desc; tie-break: by preference rank, then lowest failure
    def pref_rank(idx: int) -> int:
        if not prefer_types:
            return 999
        t = tile_to_type.get(idx, "zzz")
        return prefer_types.index(t) if t in prefer_types else 999

    rows_sorted = sorted(
        rows,
        key=lambda r: (
            -float(r.get("sv_total", 0.0)),
            pref_rank(int(r["tile_idx"])),
            float(r.get("failure_pct", 100)),
        ),
    )
    return int(rows_sorted[0]["tile_idx"])


def _best_wit_tile(
    sv_rows: List[Dict],
    *,
    allowed_only: bool = True,
    min_sv: float = 0.0,
    tile_to_type: Optional[Dict[int, str]] = None,
) -> Optional[int]:
    tile_to_type = tile_to_type or DEFAULT_TILE_TO_TYPE
    rows = [r for r in sv_rows if tile_to_type.get(int(r["tile_idx"])) == "WIT"]
    if allowed_only:
        rows = [r for r in rows if r.get("allowed_by_risk", False)]
    rows = [r for r in rows if r.get("sv_total", 0.0) >= min_sv]
    if not rows:
        return None
    rows_sorted = sorted(
        rows,
        key=lambda r: (
            -float(r.get("sv_total", 0.0)),
            float(r.get("failure_pct", 100)),
        ),
    )
    return int(rows_sorted[0]["tile_idx"])


def _any_wit_rainbow(
    sv_rows: List[Dict], tile_to_type: Optional[Dict[int, str]] = None
) -> bool:
    """
    Weak heuristic: look for 'rainbow:' in notes for WIT tile.
    (Works with the notes produced by your compute_support_values.)
    """
    tile_to_type = tile_to_type or DEFAULT_TILE_TO_TYPE
    for r in sv_rows:
        if tile_to_type.get(int(r["tile_idx"])) != "WIT":
            continue
        for note in r.get("notes") or []:
            if "rainbow" in note.lower():
                return True
    return False


def _tiles_with_hint(sv_rows: List[Dict]) -> List[int]:
    out = []
    for r in sv_rows:
        if any("hint" in (note.lower()) for note in (r.get("notes") or [])):
            out.append(int(r["tile_idx"]))
    return out


def _director_tile_and_color(
    sv_rows: List[Dict],
) -> Tuple[Optional[int], Optional[str]]:
    """
    Very light inference from notes: "Director (blue): +0.50" etc.
    Returns (tile_idx, color) or (None, None).
    """
    for r in sv_rows:
        for note in r.get("notes") or []:
            m = re.search(r"director\s*\((blue|green|orange|yellow|max)\)", note, re.I)
            if m:
                return int(r["tile_idx"]), m.group(1).lower()
    return None, None


# ---------- Main decision function ----------


def decide_action_training(
    sv_rows: List[Dict],
    *,
    mood,  # 'GOOD' or ('GOOD', 4)
    turns_left,
    career_date: DateInfo,
    energy_pct: int,
    prioritize_g1: bool,
    stats={},
    reference_stats={
        "SPD": 1150,
        "STA": 1000,
        "PWR": 530,
        "GUTS": 270,
        "WIT": 250,
    },
    # Tie-break context
    tile_to_type: Optional[Dict[int, str]] = None,
    priority_stats: Optional[Sequence[str]] = None,
    # Policy thresholds (can be tuned in config later)
    minimal_mood: str = "NORMAL",  # below this → recreation (if also < 'GREAT')
    max_pick_sv_top: float = 2.5,
    next_pick_sv_top: float = 2.0,
    late_pick_sv_top: float = 1.5,
    low_pick_sv_gate: float = 1.0,
    energy_rest_gate_lo: int = 35,  # early branch
    energy_rest_gate_mid: int = 50,  # URA branch
    energy_race_gate: int = 68,  # summer / late branch
    skip_race=False,
) -> Tuple[TrainAction, Optional[int], str]:
    """
    Return the decided action and the target tile index (or None when not applicable).
    The flow mirrors your diagrams; 'events check' nodes are ignored here.
    """

    # Normalize helpers
    tile_to_type = tile_to_type or DEFAULT_TILE_TO_TYPE
    priority_stats = list(
        priority_stats or ["SPD", "STA", "WIT", "PWR", "GUTS"]
    )  # sensible default
    for i in range(len(priority_stats)):
        priority_stats[i] = priority_stats[i].upper()

    for i in range(len(tile_to_type)):
        tile_to_type[i] = tile_to_type[i].upper()
    (mood_txt, mood_score) = normalize_mood(mood)

    if isinstance(career_date, str):
        di = parse_career_date(career_date)
    else:
        di = career_date

    # Collect reasoning as we go
    reasons: List[str] = []

    def because(msg: str) -> None:
        reasons.append(msg)

    # Convenience views
    allowed_rows = [r for r in sv_rows if r.get("allowed_by_risk", False)]
    best_allowed_tile_25 = _best_tile(
        allowed_rows,
        min_sv=max_pick_sv_top,
        prefer_types=priority_stats,
        tile_to_type=tile_to_type,
    )
    best_allowed_tile_20 = _best_tile(
        allowed_rows,
        min_sv=next_pick_sv_top,
        prefer_types=priority_stats,
        tile_to_type=tile_to_type,
    )
    best_allowed_any = _best_tile(
        allowed_rows,
        min_sv=-1.0,
        prefer_types=priority_stats,
        tile_to_type=tile_to_type,
    )
    best_wit_any = _best_wit_tile(
        sv_rows, allowed_only=True, min_sv=0.0, tile_to_type=tile_to_type
    )

    best_wit_low = _best_wit_tile(
        sv_rows, allowed_only=True, min_sv=low_pick_sv_gate, tile_to_type=tile_to_type
    )
    sv_by_tile = {int(r["tile_idx"]): float(r.get("sv_total", 0.0)) for r in sv_rows}

    def sv_of(idx: Optional[int]) -> float:
        return sv_by_tile.get(int(idx), 0.0) if idx is not None else 0.0

    # -----------------------------
    # Top of the flow
    # -----------------------------

    # -------------------------------------------------
    # Distribution-aware nudge (before step 1)
    # If a top-3 priority stat is undertrained vs. reference distribution
    # by ≥ 7% and its best SV is within 1.5 of the best overall, pick it.
    # -------------------------------------------------
    UNDERTRAIN_DELTA = 0.07  # ≥ 7% gap vs reference share
    MAX_SV_GAP = 1.5

    try:
        # Consider only known stats (ignore -1/0)
        keys = ["SPD", "STA", "PWR", "GUTS", "WIT"]
        known_keys = [k for k in keys if max(0, int(stats.get(k, -1))) > 0]

        if known_keys:
            # Normalize reference to the same subset
            ref_sum = sum(max(0, int(reference_stats.get(k, 0))) for k in known_keys)
            cur_sum = sum(max(0, int(stats.get(k, 0))) for k in known_keys)

            if ref_sum > 0 and cur_sum > 0:
                ref_dist = {
                    k: max(0, int(reference_stats.get(k, 0))) / ref_sum
                    for k in known_keys
                }
                cur_dist = {
                    k: max(0, int(stats.get(k, 0))) / cur_sum for k in known_keys
                }
                deltas = {
                    k: ref_dist[k] - cur_dist[k] for k in known_keys
                }  # +ve → undertrained
                logger_uma.debug(f"STATS deltas respect 'ideal' distribution: {deltas}")
                top3 = [
                    t.upper()
                    for t in (
                        priority_stats[:3] if priority_stats else ["SPD", "STA", "WIT"]
                    )
                ]
                cand = [
                    (k, deltas[k])
                    for k in known_keys
                    if k in top3 and deltas[k] >= UNDERTRAIN_DELTA
                ]

                if cand:
                    # Most undertrained among top-3 priorities
                    cand.sort(key=lambda kv: kv[1], reverse=True)
                    under_stat, gap = cand[0]

                    # Best allowed overall
                    top_allowed_idx = best_allowed_any
                    top_allowed_sv = sv_of(top_allowed_idx)

                    # Best allowed tile for that specific stat
                    def _best_tile_of_type(
                        rows, stat: str, min_sv: float, tmap: Dict[int, str]
                    ):
                        pool = [
                            r
                            for r in rows
                            if str(tmap.get(int(r["tile_idx"]), "")).upper()
                            == stat.upper()
                            and float(r.get("sv_total", 0.0)) >= min_sv
                        ]
                        if not pool:
                            return None, 0.0
                        rbest = max(pool, key=lambda rr: float(rr.get("sv_total", 0.0)))
                        return int(rbest["tile_idx"]), float(rbest.get("sv_total", 0.0))

                    under_idx, under_sv = _best_tile_of_type(
                        allowed_rows, under_stat, -1.0, tile_to_type
                    )

                    gap_top_under = top_allowed_sv - under_sv
                    flexible_gap = MAX_SV_GAP

                    # Wit h at least some value, default >= 0.5
                    if under_idx is not None:
                        if gap > UNDERTRAIN_DELTA * 1.5:
                            # accept more gap respect to best play
                            flexible_gap += 0.5
                        if gap > UNDERTRAIN_DELTA and (
                            (top_allowed_idx is None or gap_top_under < flexible_gap)
                            and under_sv >= max(0.5, low_pick_sv_gate / 2)
                        ):
                            because(
                                f"Undertrained {under_stat} by {gap:.1%} vs reference; "
                                f"choosing its best SV {under_sv:.2f} (overall best {top_allowed_sv:.2f}, flexible_gap < {flexible_gap})"
                            )
                            return (
                                TrainAction.TRAIN_MAX,
                                under_idx,
                                "; ".join(reasons),
                            )
                    else:
                        because(
                            f"Undertrained {under_stat} by {gap:.1%} vs reference; "
                            f"but the TOP option is better {top_allowed_sv:.2f}, gap={gap} ) or is not worth it to train under_stat"
                        )
    except Exception as _e:
        # Be permissive—never break the policy due to stats math
        because(f"Distribution check skipped due to stats error: {_e}")
    # 1) If max SV option is >= 2.5 → select TRAIN_MAX (tie → priority order)
    if best_allowed_tile_25 is not None:
        because(
            f"Top SV ≥ {max_pick_sv_top} allowed by risk → pick tile {best_allowed_tile_25}"
        )
        return (TrainAction.TRAIN_MAX, best_allowed_tile_25, "; ".join(reasons))

    because("Not a IMPRESIVE option to train, checking for other oportunities")
    # 2) Mood check → recreation
    min_mood_score = MOOD_MAP.get(str(minimal_mood).upper(), 3)
    if (
        mood_score != -1
        and mood_score < min_mood_score
        and mood_score < MOOD_MAP["GREAT"]
    ):
        because(
            f"Mood {mood_txt} below minimal {minimal_mood} and < GREAT → recreation"
        )
        return (TrainAction.RECREATION, None, "; ".join(reasons))

    # 3) Summer close? (1 turn) and energy <= 90 → TRAIN_WIT
    if is_summer_in_next_turn(di) and energy_pct <= 90:
        idx = _best_wit_tile(
            sv_rows, allowed_only=True, min_sv=0.0, tile_to_type=tile_to_type
        )
        if idx is not None:
            because("Summer in 1 turn and energy ≤ 90% → soft-skip with WIT")
            return (TrainAction.TRAIN_WIT, idx, "; ".join(reasons))

    # 4) Summer within ≤2 turns and (energy<=90 and WIT SV>=1) → TRAIN_WIT
    if is_summer_in_two_or_less_turns(di) and energy_pct <= 90:
        idx = _best_wit_tile(
            sv_rows, allowed_only=True, min_sv=0.0, tile_to_type=tile_to_type
        )
        if idx is not None:
            because("Summer ≤2 turns away, energy ≤ 90% → WIT")
            return (TrainAction.TRAIN_WIT, idx, "; ".join(reasons))

    # 5) Director rule (approximation—see)
    #    If Director is present and not max (color != yellow), and the date is within your windows → TRAIN_DIRECTOR
    director_idx, director_color = _director_tile_and_color(sv_rows)
    if director_idx is not None and di.year_code == 3:
        if (di.month in (1, 2, 3) and director_color in ("blue",)) or (
            di.month in (9, 10, 11, 12) and director_color not in ("yellow", "max")
        ):
            if (
                sv_rows[director_idx]
                if isinstance(sv_rows, list) and director_idx < len(sv_rows)
                else True
            ):
                # Still respect risk for that tile:
                if any(
                    r["tile_idx"] == director_idx and r.get("allowed_by_risk", False)
                    for r in sv_rows
                ):
                    because(
                        f"We should train with Director for extra bonuses; director color={director_color}; risk ok → train director on tile {director_idx}"
                    )
                    return (
                        TrainAction.TRAIN_DIRECTOR,
                        director_idx,
                        "; ".join(reasons),
                    )

    # 6) If max SV option >= 2.0 → TRAIN_MAX
    if best_allowed_tile_20 is not None:
        because(
            f"Top SV ≥ {next_pick_sv_top} allowed by risk → tile {best_allowed_tile_20}"
        )
        return (TrainAction.TRAIN_MAX, best_allowed_tile_20, "; ".join(reasons))

    # 7) If prioritize G1 and not Junior Year AND there is a G1 today → RACE
    if (
        prioritize_g1
        and not is_junior_year(di)
        and di.month is not None
        and not skip_race
    ):
        dk = date_key_from_dateinfo(di)
        if dk and RaceIndex.has_g1(dk):
            because("Prioritize G1 enabled, G1 available today → try race")
            return (TrainAction.RACE, None, "; ".join(reasons))

    because("No good options in general, checking other posibilities")
    # 8) If energy <= 35% → REST
    if energy_pct <= energy_rest_gate_lo:
        because(f"Energy {energy_pct}% ≤ {energy_rest_gate_lo}% → rest")
        return (TrainAction.REST, None, "; ".join(reasons))

    # 9) Soft-skip: WIT SV >= 1.5 or WIT rainbow → TRAIN_WIT
    if _any_wit_rainbow(sv_rows, tile_to_type=tile_to_type):
        if best_wit_any is not None:
            because("WIT has rainbow support → Skip turn with little energy recover")
            return (TrainAction.TRAIN_WIT, best_wit_any, "; ".join(reasons))
    else:
        idx = _best_wit_tile(
            sv_rows,
            allowed_only=True,
            min_sv=late_pick_sv_top,
            tile_to_type=tile_to_type,
        )
        if idx is not None:
            because(
                f"Decent WIT SV ≥ {late_pick_sv_top} and risk ok → WIT (aka skip turn)"
            )
            return (TrainAction.TRAIN_WIT, idx, "; ".join(reasons))

    # 10) URA Finale branch
    if is_final_season(di):
        hint_tiles = [
            t
            for t in _tiles_with_hint(sv_rows)
            if any(
                r["tile_idx"] == t and r.get("allowed_by_risk", False) for r in sv_rows
            )
        ]
        if hint_tiles:
            # choose hinted tile with best SV
            hinted = max(hint_tiles, key=lambda t: sv_of(t))
            because("URA Finale: take available hint to get more discounts")
            return (TrainAction.TAKE_HINT, hinted, "; ".join(reasons))

        because("No hint training in final season")
        # If energy <= 50 during URA → REST
        if turns_left >= 1 and energy_pct <= energy_rest_gate_mid:
            because(
                f"URA Finale, turns_left={turns_left} and energy {energy_pct}% ≤ {energy_rest_gate_mid}% → rest"
            )
            return (TrainAction.REST, None, "; ".join(reasons))

        # Else soft skip with WIT if available (≥1)
        if best_wit_low is not None:
            because("The best decision is to skip turn with WIT training")
            return (TrainAction.TRAIN_WIT, best_wit_low, "; ".join(reasons))

        # Else secure skills plan (non-tile)
        # TODO: return (TrainAction.SECURE_SKILL, None), for now just the best
        because("URA Finale: secure skill / otherwise take best allowed training")
        return (TrainAction.TRAIN_MAX, best_allowed_any, "; ".join(reasons))

    # 11)
    if best_wit_low is not None:
        because("The best decision is to skip turn with WIT training")
        return (TrainAction.TRAIN_WIT, best_wit_low, "; ".join(reasons))

    because("There is no value in training WIT, checking other options")
    # 12) If max SV ≥ 1.5 → TRAIN_MAX
    best_allowed_tile_15 = _best_tile(
        allowed_rows,
        min_sv=late_pick_sv_top,
        prefer_types=priority_stats,
        tile_to_type=tile_to_type,
    )
    if best_allowed_tile_15 is not None:
        because(
            f"Top training SV ≥ {late_pick_sv_top} allowed by risk → tile {best_allowed_tile_15}"
        )
        return (TrainAction.TRAIN_MAX, best_allowed_tile_15, "; ".join(reasons))

    # 13) Mood < Great and NOT near mood-up window → RECREATION
    if (mood_score < MOOD_MAP["GREAT"]) and not near_mood_up_event(di):
        because(
            "Mood < GREAT and not near mood-up window → recreation for future better training bonus"
        )
        return (TrainAction.RECREATION, None, "; ".join(reasons))

    # 14) Summer gate: if NOT summer and energy >= 70 and NOT Junior Pre-Debut → RACE
    if (
        (not is_summer(di))
        and (energy_pct >= energy_race_gate)
        and (not is_pre_debut(di) or not is_junior_year(di))
        and not is_final_season(di)
    ):
        # The diagram says "and not Junior Pre Debut"
        if not (is_junior_year(di) and is_pre_debut(di)) and not skip_race:
            because(
                f"Not summer, energy ≥ {energy_race_gate}% and not Junior Pre-Debut → try race (collect skill pts + minimal stat)"
            )
            return (TrainAction.RACE, None, "; ".join(reasons))
        else:
            if skip_race:
                because("Racing is skipped for external reasons")
            else:
                because(
                    "Racing is canceled either for energy, comming summer or debut/junior year"
                )
    else:
        because(
            "Racing now is not recommended, either for future events of due to energy issue"
        )

    # 15) If max SV ≥ 1 and the stat is within first 3 priorities → TRAIN_MAX
    best_allowed_tile_10 = _best_tile(
        allowed_rows,
        min_sv=low_pick_sv_gate,
        prefer_types=priority_stats[:3],
        tile_to_type=tile_to_type,
    )
    if best_allowed_tile_10 is not None:
        because(
            f"Selecting any train SV ≥ {low_pick_sv_gate} on top-3 priority stat → tile {best_allowed_tile_10}"
        )
        return (TrainAction.TRAIN_MAX, best_allowed_tile_10, "; ".join(reasons))

    # 16) Fallback: TRAIN_WIT (skip-turn/low-value)
    if is_summer(di) and best_wit_any:
        because("Fallback (Summer): WIT to skip turn and get stats")
        return (TrainAction.TRAIN_WIT, best_wit_any, "; ".join(reasons))
    elif energy_pct <= 70:
        because(
            "Weak Turn, Opportunity cost if racing Instead of WIT, selecting rest because we can recover energy"
        )
        return (TrainAction.REST, None, "; ".join(reasons))
    elif best_allowed_any is not None:
        because("Last resort: take best allowed training")
        return (TrainAction.TRAIN_MAX, best_allowed_any, "; ".join(reasons))

    because("No allowed options → NOOP")
    return (TrainAction.NOOP, None, "; ".join(reasons))


def click_training_tile(
    ctrl,
    training_state: List[Dict],
    tile_idx: int,
    *,
    clicks_range: list = [3, 5],
    pause_after: Optional[float] = None,
) -> bool:
    """
    Click the center of the training tile at `tile_idx` using the controller.
    Expects `tile_xyxy` to be in last-screenshot coordinates (as produced by your scan).

    Returns True on success, False otherwise.
    """
    tile = None

    for t in training_state:
        if int(t.get("tile_idx", -1)) == int(tile_idx):
            tile = t
            break
    if not tile:
        logger_uma.error(
            "click_training_tile: tile_idx %s not found in training_state", tile_idx
        )
        return False

    xyxy = tile["tile_xyxy"]
    clicks = random.randint(clicks_range[0], clicks_range[1])

    # Click center in *screen* coords (helper translates last-screenshot -> screen)
    ctrl.click_xyxy_center(xyxy, clicks=clicks)

    sleep(pause_after or 0.2)
    return True


@dataclass
class TrainingDecision:
    action: "TrainAction"
    tile_idx: Optional[int]
    why: str
    training_state: Any
    last_img: Optional[Image.Image]
    last_parsed: Optional[List[dict]]
    sv_rows: List[dict]


def check_training(player, *, skip_race: bool = False) -> Optional[TrainingDecision]:
    """
    Only *decides* what to do on the Training screen.
    - Reads all state directly from `player` (no copies).
    - Returns None if we are not on the Training screen.
    - Does NOT perform clicks; the caller (Player) will act on the decision.

    The function expects:
      - player.ctrl, player.ocr
      - player.lobby.state.{energy, mood, turn, date_info}
      - player.stats (optional, used by your policy)
    """
    # 1) Snapshot the training screen and parse it
    training_state, last_img, last_parsed = scan_training_screen(
        player.ctrl,
        player.ocr,
        yolo_engine=player.yolo_engine,
        energy=(
            player.lobby.state.energy if player.lobby and player.lobby.state else None
        ),
    )

    if not training_state:
        logger_uma.error("[training] Not in training screen; cannot decide.")
        return None

    # 2) Compute SV rows
    sv_rows = compute_support_values(training_state)
    for r in sv_rows:
        logger_uma.info(
            f"View {Constants.map_tile_idx_to_type[r['tile_idx']]}: "
            f"SV={r['sv_total']:.2f}  "
            f"fail={r['failure_pct']}% (≤ {r['risk_limit_pct']}% ? {r['allowed_by_risk']})  "
            f"greedy={r['greedy_hit']}"
        )
        for note in r["notes"]:
            logger_uma.info(f"   - {note}")

    # 3) Build policy inputs from live player state
    mood = player.lobby.state.mood if player.lobby else ("UNKNOWN", -1)
    turns_left = player.lobby.state.turn if player.lobby else -1
    career_date = player.lobby.state.date_info if player.lobby else None
    energy_pct = player.lobby.state.energy if player.lobby else None
    stats = player.lobby.state.stats if player.lobby else None

    # 4) Decide the action (no side effects here)
    action, tidx, why = decide_action_training(
        sv_rows,
        mood=mood,
        turns_left=turns_left,
        career_date=career_date,
        energy_pct=energy_pct,
        prioritize_g1=player.prioritize_g1,
        stats=stats,
        tile_to_type=Constants.map_tile_idx_to_type,
        priority_stats=["SPD", "STA", "WIT", "PWR", "GUTS"],
        minimal_mood="NORMAL",
        skip_race=bool(skip_race),
    )
    logger_uma.info(
        "[training] Decision: %s  tile=%s because=|%s|", action.value, tidx, why
    )

    return TrainingDecision(
        action=action,
        tile_idx=tidx,
        why=why,
        training_state=training_state,
        last_img=last_img,
        last_parsed=last_parsed,
        sv_rows=sv_rows,
    )
