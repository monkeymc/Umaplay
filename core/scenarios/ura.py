from __future__ import annotations

from core.actions.ura import training_check, training_policy
from .registry import registry

COMPUTE_VALUES_FN = training_check.compute_support_values
DECIDE_FN = training_policy.decide_action_training


def get_policy():
    return COMPUTE_VALUES_FN, DECIDE_FN


registry.set_default(COMPUTE_VALUES_FN, DECIDE_FN)
registry.register("ura", COMPUTE_VALUES_FN, DECIDE_FN)
