from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, Tuple

from core.types import TrainAction
from core.utils.date_uma import DateInfo, parse_career_date


def make_sv_row(
    tile_idx: int,
    *,
    sv_total: float,
    allowed: bool = True,
    failure_pct: float = 10.0,
    notes: Iterable[str] | None = None,
    sv_by_type: Dict[str, float] | None = None,
) -> Dict[str, object]:
    return {
        "tile_idx": tile_idx,
        "sv_total": sv_total,
        "allowed_by_risk": allowed,
        "failure_pct": failure_pct,
        "notes": list(notes or []),
        "sv_by_type": sv_by_type or {},
    }


@dataclass(frozen=True)
class PolicyScenario:
    description: str
    sv_rows: Tuple[Dict[str, object], ...]
    mood: Tuple[str, int]
    turns_left: int
    date: DateInfo
    energy_pct: int
    prioritize_g1: bool
    stats: Dict[str, int]
    expected_action: TrainAction
    expected_tile: int | None


def _summer_soft_skip() -> PolicyScenario:
    sv_rows = (
        make_sv_row(0, sv_total=1.8),
        make_sv_row(1, sv_total=1.3),
        make_sv_row(4, sv_total=0.9, notes=["rainbow"], sv_by_type={}),
    )
    return PolicyScenario(
        description="Summer in next turn with middling energy prefers WIT soft skip",
        sv_rows=sv_rows,
        mood=("GOOD", 4),
        turns_left=12,
        date=parse_career_date("Classic Year Late Jun"),
        energy_pct=78,
        prioritize_g1=False,
        stats={"SPD": 500, "STA": 480, "PWR": 420, "GUTS": 350, "WIT": 310},
        expected_action=TrainAction.TRAIN_MAX,
        expected_tile=0,
    )


def _low_sv_rest() -> PolicyScenario:
    sv_rows = (
        make_sv_row(0, sv_total=0.4),
        make_sv_row(1, sv_total=0.3),
        make_sv_row(4, sv_total=0.2),
    )
    return PolicyScenario(
        description="Low SV with low energy triggers rest",
        sv_rows=sv_rows,
        mood=("NORMAL", 3),
        turns_left=18,
        date=parse_career_date("Classic Year Early May"),
        energy_pct=28,
        prioritize_g1=False,
        stats={"SPD": 520, "STA": 510, "PWR": 480, "GUTS": 320, "WIT": 290},
        expected_action=TrainAction.REST,
        expected_tile=None,
    )


def _finale_hint_priority() -> PolicyScenario:
    sv_rows = (
        make_sv_row(0, sv_total=1.9),
        make_sv_row(4, sv_total=1.6, notes=["hint"], sv_by_type={"hint_bluegreen": 0.6}),
    )
    return PolicyScenario(
        description="Final season prioritises hint tiles",
        sv_rows=sv_rows,
        mood=("GOOD", 4),
        turns_left=3,
        date=parse_career_date("Final Season"),
        energy_pct=65,
        prioritize_g1=False,
        stats={"SPD": 980, "STA": 880, "PWR": 750, "GUTS": 420, "WIT": 400},
        expected_action=TrainAction.TRAIN_MAX,
        expected_tile=4,
    )


def iter_policy_scenarios() -> Iterator[PolicyScenario]:
    """Yield baseline URA scenarios to guard regressions."""
    yield from (
        _summer_soft_skip(),
        _low_sv_rest(),
        _finale_hint_priority(),
    )
