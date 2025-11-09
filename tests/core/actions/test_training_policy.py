# tests/core/actions/test_training_policy.py
from __future__ import annotations

import pytest

from core.actions.ura.training_policy import decide_action_training
from tests.fixtures.training_policy import iter_policy_scenarios


@pytest.mark.parametrize(
    "scenario",
    list(iter_policy_scenarios()),
    ids=lambda case: case.description,
)
def test_decide_action_training_regressions(scenario):
    action, tile, reason = decide_action_training(
        list(scenario.sv_rows),
        mood=scenario.mood,
        turns_left=scenario.turns_left,
        career_date=scenario.date,
        energy_pct=scenario.energy_pct,
        prioritize_g1=scenario.prioritize_g1,
        stats=scenario.stats,
        race_if_no_good_value=False,
    )

    assert action == scenario.expected_action, f"{scenario.description}: {reason}"
    assert tile == scenario.expected_tile, f"{scenario.description}: {reason}"
