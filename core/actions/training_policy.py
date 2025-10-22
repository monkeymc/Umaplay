# core\actions\training_policy.py
from __future__ import annotations

import enum
import random
import re
from dataclasses import dataclass
from time import sleep
from typing import Any, Dict, List, Optional, Sequence, Tuple, cast

from PIL import Image
from core.actions.training_check import compute_support_values, scan_training_screen
from core.constants import DEFAULT_TILE_TO_TYPE, MOOD_MAP
from core.types import MoodName
from core.utils.date_uma import (
    DateInfo,
    is_final_season,
    is_junior_year,
    is_pre_debut,
    is_summer,
    is_summer_in_next_turn,
    is_summer_in_two_or_less_turns,
    near_mood_up_event,
    parse_career_date,
)
from core.utils.logger import logger_uma
from core.settings import Constants, Settings
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
    else:
        mtxt = str(mood).upper()

    if mtxt in MOOD_MAP:
        mood_key: MoodName = cast(MoodName, mtxt)
    else:
        mood_key = "UNKNOWN"
    return (mtxt, MOOD_MAP[mood_key])


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
        sv_by_type = r.get("sv_by_type") or {}
        hint_value = float(sv_by_type.get("hint_bluegreen", 0.0)) + float(
            sv_by_type.get("hint_orange_max", 0.0)
        )
        if hint_value > 1e-6:
            out.append(int(r["tile_idx"]))
            continue

        notes = r.get("notes") or []
        if any(
            ("hint" in note.lower())
            and ("+0.00" not in note)
            and ("skipped" not in note.lower())
            for note in notes
        ):
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
    mood,
    turns_left,
    career_date: DateInfo,
    energy_pct: int,
    prioritize_g1: bool,
    stats={},
    reference_stats={
        "SPD": 1150,
        "STA": 900,
        "PWR": 700,
        "GUTS": 300,
        "WIT": 400,
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
    # Runtime settings from preset
    race_if_no_good_value: bool = False,
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
    sv_by_tile = {int(r["tile_idx"]): float(r.get("sv_total", 0.0)) for r in sv_rows}

    # -------- Cap-aware filtering (do not train stats already at/above reference) --------
    def _stat_of_tile(idx: int) -> str:
        return str(tile_to_type.get(int(idx), "")).upper()

    try:
        capped_stats = set()
        for k, target in (reference_stats or {}).items():
            kU = str(k).upper()
            cur = int(stats.get(kU, -1))
            if cur >= 0 and int(target) > 0 and cur >= int(target):
                capped_stats.add(kU)
    except Exception:
        capped_stats = set()

    raw_hint_tiles = _tiles_with_hint(sv_rows)
    hint_override_stats = set()
    if Settings.HINT_IS_IMPORTANT:
        for t in raw_hint_tiles:
            stat = _stat_of_tile(int(t))
            if not stat:
                continue
            passes_risk = any(
                (r.get("tile_idx") == t) and r.get("allowed_by_risk", False)
                for r in sv_rows
            )
            if stat in capped_stats and passes_risk:
                hint_override_stats.add(stat)

    def _exclude_capped(rows):
        return [
            r
            for r in rows
            if (
                (stat := _stat_of_tile(int(r["tile_idx"]))) not in capped_stats
                or stat in hint_override_stats
            )
        ]

    allowed_rows_filtered = _exclude_capped(allowed_rows)

    # WIT helpers respect caps too
    wit_capped_without_hint = "WIT" in capped_stats and "WIT" not in hint_override_stats
    best_wit_any = (
        None
        if wit_capped_without_hint
        else _best_wit_tile(
            sv_rows, allowed_only=True, min_sv=0.0, tile_to_type=tile_to_type
        )
    )
    best_wit_low = (
        None
        if wit_capped_without_hint
        else _best_wit_tile(
            sv_rows,
            allowed_only=True,
            min_sv=low_pick_sv_gate,
            tile_to_type=tile_to_type,
        )
    )

    # Hinted tiles that pass risk and are uncapped (or explicitly allowed via hint override)
    hint_tiles = [
        t
        for t in raw_hint_tiles
        if any(
            (r["tile_idx"] == t) and r.get("allowed_by_risk", False) for r in sv_rows
        )
        and (
            _stat_of_tile(int(t)) not in capped_stats
            or _stat_of_tile(int(t)) in hint_override_stats
        )
    ]
    best_allowed_tile_25 = _best_tile(
        allowed_rows_filtered,
        min_sv=max_pick_sv_top,
        prefer_types=priority_stats,
        tile_to_type=tile_to_type,
    )
    best_allowed_tile_20 = _best_tile(
        allowed_rows_filtered,
        min_sv=next_pick_sv_top,
        prefer_types=priority_stats,
        tile_to_type=tile_to_type,
    )
    best_allowed_any = _best_tile(
        allowed_rows_filtered,
        min_sv=-1.0,
        prefer_types=priority_stats,
        tile_to_type=tile_to_type,
    )

    top3_stats = [s.upper() for s in priority_stats[:3]]

    def _best_tile_for_stats(
        rows: Sequence[Dict], stats_subset: Sequence[str], min_sv: float = -1.0
    ) -> Tuple[Optional[int], float]:
        if not stats_subset:
            return None, 0.0
        stats_set = {s.upper() for s in stats_subset}
        pool = [
            r
            for r in rows
            if _stat_of_tile(int(r["tile_idx"])) in stats_set
            and float(r.get("sv_total", 0.0)) >= min_sv
        ]
        if not pool:
            return None, 0.0
        rbest = max(pool, key=lambda rr: float(rr.get("sv_total", 0.0)))
        return int(rbest["tile_idx"]), float(rbest.get("sv_total", 0.0))

    top3_tile_idx, top3_tile_sv = _best_tile_for_stats(
        allowed_rows_filtered, top3_stats, -1.0
    )
    top3_tile_stat = _stat_of_tile(int(top3_tile_idx)) if top3_tile_idx is not None else None

    PRIORITY_SV_DIFF_THRESHOLD = 0.75
    PRIORITY_TOP3_MIN_SV = 0.5
    PRIORITY_EXCEPTIONAL_SV = 4.1

    def _apply_priority_guard(candidate_idx: Optional[int], *, context: str) -> Optional[int]:
        if candidate_idx is None or top3_tile_idx is None:
            return candidate_idx
        candidate_stat = _stat_of_tile(int(candidate_idx))
        if candidate_stat in top3_stats:
            return candidate_idx
        candidate_sv = sv_of(candidate_idx)
        if candidate_sv >= PRIORITY_EXCEPTIONAL_SV:
            because(
                f"Priority guard skipped: {candidate_stat} SV {candidate_sv:.2f} ≥ {PRIORITY_EXCEPTIONAL_SV:.2f} considered exceptional"
            )
            return candidate_idx
        diff = candidate_sv - top3_tile_sv
        if top3_tile_sv >= PRIORITY_TOP3_MIN_SV and diff <= PRIORITY_SV_DIFF_THRESHOLD:
            because(
                f"Priority guard: {context} best option {candidate_stat} SV {candidate_sv:.2f} is only {diff:.2f} above top-3 {top3_tile_stat} SV {top3_tile_sv:.2f} → prefer top-3 stat"
            )
            return top3_tile_idx
        return candidate_idx

    def sv_of(idx: Optional[int]) -> float:
        return sv_by_tile.get(int(idx), 0.0) if idx is not None else 0.0

    # -----------------------------
    # Top of the flow
    # -----------------------------

    # -------------------------------------------------
    # Distribution-aware nudge (before step 1)
    # If a top-3 priority stat is undertrained vs. reference distribution
    # by ≥ (UNDERTRAIN_THRESHOLD)% and its best SV is within 1.5 of the best overall, pick it.
    # -------------------------------------------------
    # Use the configurable threshold from Settings, defaulting to 6% if not set
    UNDERTRAIN_DELTA = (
        getattr(Settings, "UNDERTRAIN_THRESHOLD", 6.0) / 100.0
    )  # Convert percentage to decimal
    MAX_SV_GAP = 1.25

    try:
        # Consider only known stats (ignore -1/0)
        keys = ["SPD", "STA", "PWR", "GUTS", "WIT"]
        known_keys = [k for k in keys if max(0, int(stats.get(k, -1))) > 0]

        # If hint is important ignore undertrain stat check, prioritize hint
        if known_keys and not (Settings.HINT_IS_IMPORTANT and len(hint_tiles) > 0):
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
                # Get the top N stats to focus on, based on priority_stats or default order
                default_priority = ["SPD", "STA", "WIT", "PWR", "GUTS"]
                effective_priority = (
                    priority_stats if priority_stats else default_priority
                )
                top_n = effective_priority[: Settings.TOP_STATS_FOCUS]

                # Log which stats we're focusing on
                logger_uma.debug(
                    f"Focusing on top {Settings.TOP_STATS_FOCUS} stats: {top_n}"
                )

                # Find stats that are undertrained and in our focus list
                cand = [
                    (k, deltas[k])
                    for k in known_keys
                    if k in top_n and deltas[k] >= UNDERTRAIN_DELTA
                ]

                # If no candidates in top N, consider all stats but with lower priority
                if (
                    not cand and Settings.TOP_STATS_FOCUS < 5
                ):  # Only if we're not already considering all
                    cand = [
                        (k, deltas[k] * 0.5)  # Reduce priority for non-focus stats
                        for k in known_keys
                        if deltas[k] >= UNDERTRAIN_DELTA
                    ]

                if cand:
                    logger_uma.debug(f"Undertrain candidates: {cand}")
                    # Sort by how undertrained they are (highest gap first)
                    cand.sort(key=lambda kv: kv[1], reverse=True)
                    under_stat, gap = cand[0]

                    # Log decision making
                    if len(cand) > 1:
                        logger_uma.debug(
                            f"Selected {under_stat} (gap: {gap:.2f}) from candidates: "
                            f"{', '.join(f'{k}({v:.2f})' for k, v in cand)}"
                        )

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

                    # respect caps here by using allowed_rows_filtered
                    under_idx, under_sv = _best_tile_of_type(
                        allowed_rows_filtered, under_stat, -1.0, tile_to_type
                    )

                    gap_top_under = top_allowed_sv - under_sv
                    flexible_gap = MAX_SV_GAP

                    # Wit h at least some value, default >= 0.5
                    if under_idx is not None and under_sv and under_sv > 0:
                        if gap > UNDERTRAIN_DELTA * 1.5:
                            # accept more gap respect to best play
                            flexible_gap += 0.25
                        if gap > UNDERTRAIN_DELTA and (
                            (top_allowed_idx is None or gap_top_under < flexible_gap)
                            and under_sv >= max(0.5, low_pick_sv_gate / 2)
                        ):
                            because(
                                f"Undertrained {under_stat} by {gap:.1%} vs reference; "
                                f"choosing its best SV {under_sv:.2f} (overall best {top_allowed_sv:.2f}, current gap between best option and undertrained option={gap_top_under:.2f} < flexible_gap={flexible_gap}). So let's train under stat tile"
                            )
                            return (
                                TrainAction.TRAIN_MAX,
                                under_idx,
                                "; ".join(reasons),
                            )
                    else:
                        because(
                            f"Undertrained {under_stat} by {gap:.1%} vs reference; "
                            f"but the TOP option is better with SV {top_allowed_sv:.2f}, gap={gap} ) or is not worth it to train under_stat"
                        )
                else:
                    logger_uma.debug(
                        f"No undertrain candidates, Threshold: {UNDERTRAIN_DELTA}. Keys: {known_keys}. Stats checked: {top_n}"
                    )
    except Exception as _e:
        # Be permissive—never break the policy due to stats math
        because(f"Distribution check skipped due to stats error: {_e}")
        logger_uma.error(f"Distribution check skipped due to stats error: {_e}")
    # 1) If max SV option is >= 2.5 → select TRAIN_MAX (tie → priority order)
    if best_allowed_tile_25 is not None:
        because(
            f"Top SV ≥ {max_pick_sv_top} allowed by risk → pick tile {best_allowed_tile_25}"
        )
        target_tile = _apply_priority_guard(
            best_allowed_tile_25, context=f"SV ≥ {max_pick_sv_top}"
        )
        return (TrainAction.TRAIN_MAX, target_tile, "; ".join(reasons))

    # URA Finale branch
    if is_final_season(di):
        # No rest allowed for now
        if hint_tiles:
            hinted = max(hint_tiles, key=lambda t: sv_of(t))
            because("URA Finale: take available hint to get more discounts")
            return (TrainAction.TAKE_HINT, hinted, "; ".join(reasons))

        # Re-target inheritance thresholds in final season:
        # 1) For top-3 priority stats, pick the first whose current value < 600.
        #    (Ignore caps here; thresholds outrank reference targets in URA.)
        top3_prio = [s.upper() for s in (priority_stats or [])][:3]

        def _best_tile_of_type(rows, stat: str, min_sv: float, tmap: Dict[int, str]):
            pool = [
                r
                for r in rows
                if str(tmap.get(int(r["tile_idx"]), "")).upper() == stat.upper()
                and float(r.get("sv_total", 0.0)) >= min_sv
            ]
            if not pool:
                return None, 0.0
            rbest = max(pool, key=lambda rr: float(rr.get("sv_total", 0.0)))
            return int(rbest["tile_idx"]), float(rbest.get("sv_total", 0.0))

        # (a) push any top-3 stat to 600 first
        for stat_name in top3_prio:
            curv = int(stats.get(stat_name, -1))
            if curv >= 0 and curv < 600:
                idx600, sv600 = _best_tile_of_type(
                    allowed_rows, stat_name, -1.0, tile_to_type
                )
                if idx600 is not None:
                    because(
                        f"URA Finale: raise {stat_name} towards 600 (cur={curv}) → tile {idx600}"
                    )
                    return (TrainAction.TRAIN_MAX, idx600, "; ".join(reasons))

        # (b) if all ≥ 600, pick the top-3 stat closest to 1200 but < 1170
        near_candidates = []
        for stat_name in top3_prio:
            curv = int(stats.get(stat_name, -1))
            if curv >= 0 and curv < 1170:
                near_candidates.append((stat_name, curv))
        if near_candidates:
            # Choose the one with the largest current value (closest to 1200)
            target_stat = max(near_candidates, key=lambda kv: kv[1])[0]
            idx1170, sv1170 = _best_tile_of_type(
                allowed_rows, target_stat, -1.0, tile_to_type
            )
            if idx1170 is not None:
                because(
                    f"URA Finale: push {target_stat} closer to 1200 (cur={int(stats.get(target_stat, -1))}) but <1170 → tile {idx1170}"
                )
                return (TrainAction.TRAIN_MAX, idx1170, "; ".join(reasons))

        # (c) last resort in URA: WIT soft-skip if available (uses cap-aware best_wit_low above)
        if best_wit_low is not None:
            because("URA Finale: no threshold targets; soft-skip with WIT")
            return (TrainAction.TRAIN_WIT, best_wit_low, "; ".join(reasons))

    because(
        "Not a IMPRESIVE option to train (>= 2.5 in SV)"
    )
    # 2) Mood check → recreation
    minimal_mood_key = str(minimal_mood).upper()
    mood_lookup_key: MoodName = (
        cast(MoodName, minimal_mood_key)
        if minimal_mood_key in MOOD_MAP
        else "UNKNOWN"
    )
    min_mood_score = MOOD_MAP.get(mood_lookup_key, 3)
    if (
        mood_score != -1
        and mood_score < min_mood_score
        and mood_score < MOOD_MAP["GREAT"]
    ):
        because(
            f"Mood {mood_txt} below minimal {minimal_mood} and < GREAT → recreation"
        )
        return (TrainAction.RECREATION, None, "; ".join(reasons))
    else:
        because("Mood may be ok for now, so skipping recreation unless SV is low...")

    # 3) Summer close? (1 turn) → TRAIN_WIT if rest is excesive
    if is_summer_in_next_turn(di):
        because("Summer is in next turn")
        if energy_pct >= 75 and energy_pct <= 96:
            idx = _best_wit_tile(
                sv_rows, allowed_only=True, min_sv=0.0, tile_to_type=tile_to_type
            )
            if idx is not None:
                because(
                    f"Summer in 1 turn and energy {energy_pct} % → recover a little with soft-skip with WIT"
                )
                return (TrainAction.TRAIN_WIT, idx, "; ".join(reasons))
        elif energy_pct <= 70:
            because(
                f"Summer in 1 turn and energy {energy_pct} % → recover a lot with soft-skip with WIT"
            )
            return (TrainAction.REST, None, "; ".join(reasons))
        else:
            because(f"Summer in 1 turn and energy {energy_pct} % → skipping rest")

    # 4) Summer within ≤2 turns and (energy<=90 and WIT SV>=1) → TRAIN_WIT
    if is_summer_in_two_or_less_turns(di) and energy_pct <= 90:
        because("Summer is in ≤2 turns away")
        idx = _best_wit_tile(
            sv_rows, allowed_only=True, min_sv=0.50, tile_to_type=tile_to_type
        )
        if idx is not None:
            because("Valuable WIT found for summer, SV >= 0.5")
            return (TrainAction.TRAIN_WIT, idx, "; ".join(reasons))
        else:
            because("No valuable WIT found for summer, SV < 0.5")

    # 6) If max SV option >= 2.0 → TRAIN_MAX
    if best_allowed_tile_20 is not None:
        because(
            f"Top SV ≥ {next_pick_sv_top} allowed by risk → tile {best_allowed_tile_20}"
        )
        target_tile = _apply_priority_guard(
            best_allowed_tile_20, context=f"SV ≥ {next_pick_sv_top}"
        )
        return (TrainAction.TRAIN_MAX, target_tile, "; ".join(reasons))

    # 7) If prioritize G1 and not Junior Year AND there is a G1 today → RACE
    if (
        prioritize_g1
        and not is_junior_year(di)
        and di.month is not None
        and not skip_race
        and not is_final_season(di)
    ):
        dk = date_key_from_dateinfo(di)
        if dk and RaceIndex.has_g1(dk):
            # Check if we should skip racing due to no good training options
            if not race_if_no_good_value:
                # Check if we have any good training options (SV > 0)
                has_good_training = any(
                    float(r.get("sv_total", 0)) > 0 for r in allowed_rows_filtered
                )

                if not has_good_training:
                    # Find the best training option even if it's not great
                    best_tile = _best_tile(
                        allowed_rows_filtered,
                        min_sv=0,  # Consider any training option
                        prefer_types=priority_stats,
                        tile_to_type=tile_to_type,
                    )
                    if best_tile is not None:
                        best_sv = next(
                            (
                                r.get("sv_total", 0)
                                for r in allowed_rows_filtered
                                if r.get("tile_idx") == best_tile
                            ),
                            0,
                        )
                        because(
                            f"No good training options (best SV: {best_sv:.2f} ≤ 0.1) and race_if_no_good_value is disabled"
                        )
                        return (TrainAction.TRAIN_MAX, best_tile, "; ".join(reasons))
                    # If no training options at all, fall through to race

            because("Prioritize G1 enabled, G1 available today → try race")
            return (TrainAction.RACE, None, "; ".join(reasons))

    # Director rule (approximation—see)
    #    If Director is present and not max (color != yellow), date is within windows,
    #    AND the tile's stat is within the top-3 priority stats → TRAIN_DIRECTOR
    director_idx, director_color = _director_tile_and_color(sv_rows)
    if director_idx is not None and di.year_code == 3:
        if (di.month in (1, 2, 3) and director_color in ("blue",)) or (
            di.month in (9, 10, 11, 12) and director_color not in ("yellow", "max")
        ):
            # Validate index and map tile -> stat
            if isinstance(sv_rows, list) and 0 <= director_idx < len(sv_rows):
                dir_stat = str(tile_to_type.get(int(director_idx), "")).upper()
                top3_priorities = [s.upper() for s in (priority_stats or [])][:3]

                # Require Director tile to be one of the top-3 priority stats
                if dir_stat in top3_priorities or director_color in ("orange", ):
                    # Also skip if this stat is capped already
                    if dir_stat in capped_stats and director_color not in ("orange",):
                        because(
                            f"Director present but {dir_stat} already at/above target and is not orange → skip Director rule"
                        )
                    else:
                        # Still respect risk for that tile:
                        if any(
                            (r.get("tile_idx") == director_idx)
                            and r.get("allowed_by_risk", False)
                            for r in sv_rows
                        ):
                            because(
                                f"We should train with Director for extra bonuses; director color={director_color}; "
                                f"tile stat={dir_stat} in top-3 priorities {top3_priorities}; risk ok → tile {director_idx}"
                            )
                            return (
                                TrainAction.TRAIN_DIRECTOR,
                                director_idx,
                                "; ".join(reasons),
                            )
                else:
                    because(
                        f"Director present but tile stat {dir_stat} not in top-3 priorities {top3_priorities} → skip Director rule"
                    )
    
    any_wit_rb = _any_wit_rainbow(sv_rows, tile_to_type=tile_to_type)
    idx_wit_1_5 = _best_wit_tile(
        sv_rows,
        allowed_only=True,
        min_sv=1.5,
        tile_to_type=tile_to_type,
    )
    if any_wit_rb and idx_wit_1_5 is not None:
        because("WIT has rainbow support and SV ≥ 1.5 → Skip turn with good wit value")
        return (TrainAction.TRAIN_WIT, idx_wit_1_5, "; ".join(reasons))

    # 8) If energy <= 35% → REST
    if energy_pct <= energy_rest_gate_lo:
        because(f"Energy {energy_pct}% ≤ {energy_rest_gate_lo}% → rest")
        return (TrainAction.REST, None, "; ".join(reasons))

    # 9) Soft-skip: WIT SV >= 1.5 or WIT rainbow → TRAIN_WIT
    if any_wit_rb:
        if best_wit_any is not None:
            because("WIT has rainbow support → Skip turn with little energy recover")
            return (TrainAction.TRAIN_WIT, best_wit_any, "; ".join(reasons))
    else:
        
        if idx_wit_1_5 is not None:
            because(
                f"Decent WIT SV ≥ {late_pick_sv_top} and risk ok → WIT (aka skip turn)"
            )
            return (TrainAction.TRAIN_WIT, idx_wit_1_5, "; ".join(reasons))

    # 11)
    if best_wit_low is not None:
        because("The best decision is to SKIP turn with WIT training")
        return (TrainAction.TRAIN_WIT, best_wit_low, "; ".join(reasons))

    because("There is no value in training WIT unless no good option in top 3 stats")
    # 12) If max SV ≥ 1.5 → TRAIN_MAX
    best_allowed_tile_15 = _best_tile(
        allowed_rows_filtered,
        min_sv=late_pick_sv_top,
        prefer_types=priority_stats,
        tile_to_type=tile_to_type,
    )
    if best_allowed_tile_15 is not None:
        because(
            f"Top training SV ≥ {late_pick_sv_top} allowed by risk → tile {best_allowed_tile_15}"
        )
        target_tile = _apply_priority_guard(
            best_allowed_tile_15, context=f"SV ≥ {late_pick_sv_top}"
        )
        return (TrainAction.TRAIN_MAX, target_tile, "; ".join(reasons))

    # 13) Mood < Great and NOT near mood-up window → RECREATION
    if (mood_score < MOOD_MAP["GREAT"]) and not near_mood_up_event(di):

        if is_summer(di) and energy_pct <= 65:
            because(
                "Summer, Mood < GREAT and energy <= 60% → recreation for future better training bonus"
            )
            return (TrainAction.RECREATION, None, "; ".join(reasons))
        elif not is_summer(di) and energy_pct <= 90:
            because(
                "Mood < GREAT and not near mood-up window and energy <= 90% → recreation for future better training bonus"
            )
            return (TrainAction.RECREATION, None, "; ".join(reasons))

    # 14) Summer gate: if NOT summer and energy >= 70 and NOT Junior Pre-Debut → RACE
    if (
        (not is_summer(di))
        and (energy_pct >= energy_race_gate)
        and (not is_pre_debut(di) or not is_junior_year(di))
        and not is_final_season(di)
    ):
        if (
            not (is_junior_year(di) or is_pre_debut(di) or is_final_season(di))
            and not skip_race
        ):
            # Check if we should skip racing due to no good training options
            if not race_if_no_good_value:
                # Check if we have any good training options (SV > 0)
                has_good_training = any(
                    float(r.get("sv_total", 0)) >= 0 for r in allowed_rows_filtered
                )

                if has_good_training:
                    # Find the best training option even if it's not great
                    best_tile = _best_tile(
                        allowed_rows_filtered,
                        min_sv=0,  # Consider any training option
                        prefer_types=priority_stats,
                        tile_to_type=tile_to_type,
                    )
                    if best_tile is not None:
                        target_tile = _apply_priority_guard(
                            best_tile, context="race fallback (no good training)"
                        )
                        target_sv = sv_of(target_tile)
                        because(
                            f"No good training options (best SV: {target_sv:.2f} ≤ 0.1) and race_if_no_good_value is disabled"
                        )
                        return (TrainAction.TRAIN_MAX, target_tile, "; ".join(reasons))
                    # If no training options at all, fall through to race

            because(
                f"Not summer, energy ≥ {energy_race_gate}% and not Junior Pre-Debut → try race (collect skill pts + minimal stat)"
            )
            return (TrainAction.RACE, None, "; ".join(reasons))
        else:
            if skip_race:
                because("Racing is skipped for external reasons")
            else:
                because(
                    "Racing is canceled either for energy, coming summer or debut/junior year"
                )
    else:
        because(
            "Racing now is not recommended, either for future events of due to energy issue"
        )

    # 15) If max SV ≥ 1 and the stat is within first 3 priorities → TRAIN_MAX
    best_allowed_tile_10 = _best_tile(
        allowed_rows_filtered,
        min_sv=low_pick_sv_gate,
        prefer_types=priority_stats[:3],
        tile_to_type=tile_to_type,
    )
    if best_allowed_tile_10 is not None:
        because(
            f"Selecting any train SV ≥ {low_pick_sv_gate} on top-3 priority stat → tile {best_allowed_tile_10}"
        )
        target_tile = _apply_priority_guard(
            best_allowed_tile_10, context=f"SV ≥ {low_pick_sv_gate}"
        )
        return (TrainAction.TRAIN_MAX, target_tile, "; ".join(reasons))
    else:
        because("No training options in top-3 priorities with at least a SV of 1")

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
        target_tile = _apply_priority_guard(best_allowed_any, context="fallback")
        return (TrainAction.TRAIN_MAX, target_tile, "; ".join(reasons))

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
        tile_idx = int(r['tile_idx'])
        tile_type = Constants.map_tile_idx_to_type.get(tile_idx, f"Unknown[{tile_idx}]")
        logger_uma.info(
            f"View [{tile_idx}] {tile_type}: "
            f"SV={r['sv_total']:.2f}  "
            f"fail={r['failure_pct']}% (≤ {r['risk_limit_pct']}% ? {r['allowed_by_risk']})  "
            f"greedy={r['greedy_hit']}"
        )
        for note in r["notes"]:
            logger_uma.info(f"   - {note}")

    # 3) Build policy inputs from live player state and config
    mood = player.lobby.state.mood if player.lobby else ("UNKNOWN", -1)
    turns_left = player.lobby.state.turn if player.lobby else -1
    career_date = player.lobby.state.date_info if player.lobby else None
    energy_pct = player.lobby.state.energy if player.lobby else None
    stats = player.lobby.state.stats if player.lobby else None

    # Get the current preset's runtime settings from the last applied config
    preset_settings = Settings.extract_runtime_preset(
        getattr(Settings, "_last_config", {}) or {}
    )
    race_if_no_good_value = preset_settings.get("raceIfNoGoodValue", False)

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
        reference_stats=Settings.REFERENCE_STATS,
        priority_stats=Settings.PRIORITY_STATS,
        minimal_mood=Settings.MINIMAL_MOOD,
        skip_race=bool(skip_race),
        race_if_no_good_value=race_if_no_good_value,
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
