from __future__ import annotations

from core.actions.ura import training_check, training_policy
from .registry import registry

SCAN_FN = training_check.scan_training_screen
DECIDE_FN = training_policy.decide_action_training


def get_policy():
    return SCAN_FN, DECIDE_FN


registry.set_default(SCAN_FN, DECIDE_FN)
registry.register("ura", SCAN_FN, DECIDE_FN)
