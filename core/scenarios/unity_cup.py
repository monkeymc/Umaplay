# core\scenarios\unity_cup.py
from __future__ import annotations

from core.actions.unity_cup.training_check import compute_support_values
# from core.actions.unity_cup.training_policy import decide_action_training
# from .registry import registry

COMPUTE_VALUES_FN = compute_support_values
DECIDE_FN = decide_action_training


def get_policy():
    return COMPUTE_VALUES_FN, DECIDE_FN


registry.set_default(COMPUTE_VALUES_FN, DECIDE_FN)
registry.register("unity_cup", COMPUTE_VALUES_FN, DECIDE_FN)
