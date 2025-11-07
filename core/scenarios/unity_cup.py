from __future__ import annotations

from .registry import registry
from .ura import get_policy as get_ura_policy


def get_policy():
    return get_ura_policy()


registry.register("unity_cup", *get_policy())
