# core\scenarios\registry.py
from __future__ import annotations

from typing import Callable

from core.settings import Settings

PolicyCallable = Callable[..., tuple]


class ScenarioPolicyRegistry:
    """Minimal indirection layer for training policies per scenario."""

    def __init__(self) -> None:
        self._fallback_policy: tuple[PolicyCallable, PolicyCallable] | None = None
        self._scenarios: dict[str, tuple[PolicyCallable, PolicyCallable]] = {}

    def set_default(self, scan: PolicyCallable, decide: PolicyCallable) -> None:
        self._fallback_policy = (scan, decide)

    def register(self, scenario: str, scan: PolicyCallable, decide: PolicyCallable) -> None:
        self._scenarios[scenario] = (scan, decide)

    def resolve(self, scenario: str | None = None) -> tuple[PolicyCallable, PolicyCallable]:
        key = (scenario or Settings.ACTIVE_SCENARIO or "ura").lower()
        alias = "unity_cup" if key == "aoharu" else key
        if alias in self._scenarios:
            return self._scenarios[alias]
        if self._fallback_policy is None:
            raise RuntimeError("ScenarioPolicyRegistry has no fallback policy registered")
        return self._fallback_policy


registry = ScenarioPolicyRegistry()
