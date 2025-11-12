# core\actions\training_policy.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

from PIL import Image
from core.actions.training_check import scan_training_screen

from core.types import TrainAction
from core.utils.logger import logger_uma
from core.settings import Constants, Settings
from core.scenarios import registry
# ---------- Action Enum ----------

@dataclass
class TrainingDecision:
    action: "TrainAction"
    tile_idx: Optional[int]
    why: str
    training_state: Any
    last_img: Optional[Image.Image]
    last_parsed: Optional[List[dict]]
    sv_rows: List[dict]

# ---------- Main decision function ----------


def get_compute_support_values():
    """Resolve the correct compute_support_values function based on active scenario."""
    compute_fn, _ = registry.resolve(Settings.ACTIVE_SCENARIO)
    return compute_fn


def get_decide_action_training():
    """Resolve the scenario-specific decide_action_training function."""
    _, decide_fn = registry.resolve(Settings.ACTIVE_SCENARIO)
    return decide_fn

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
    sv_rows = get_compute_support_values()(training_state)
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

    weak_turn_sv_raw = preset_settings.get("weakTurnSv", Settings.WEAK_TURN_SV)
    try:
        weak_turn_sv = float(weak_turn_sv_raw)
    except (TypeError, ValueError):
        weak_turn_sv = float(Settings.WEAK_TURN_SV)

    junior_minimal_mood_raw = preset_settings.get("juniorMinimalMood")
    if isinstance(junior_minimal_mood_raw, str) and junior_minimal_mood_raw.strip():
        junior_minimal_mood = junior_minimal_mood_raw.strip().upper()
    else:
        junior_minimal_mood = Settings.JUNIOR_MINIMAL_MOOD

    # 4) Decide the action (no side effects here)
    action, tidx, why = get_decide_action_training()(
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
        weak_turn_sv=weak_turn_sv,
        junior_minimal_mood=junior_minimal_mood,
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
