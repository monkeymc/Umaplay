from __future__ import annotations

import importlib
import contextlib
import types

import pytest


@pytest.fixture
def module():
    scenario_prompt = importlib.import_module("core.ui.scenario_prompt")
    importlib.reload(scenario_prompt)
    yield scenario_prompt


def test_choose_active_scenario_uses_last_value(module):
    captured_default: dict[str, str] = {}

    def fake_prompt(default: str) -> str:
        captured_default["value"] = default
        return "unity_cup"

    result = module.choose_active_scenario(last_scenario="unity_cup", prompt=fake_prompt)

    assert captured_default["value"] == "unity_cup"
    assert result == "unity_cup"


def test_choose_active_scenario_unknown_last_falls_back_to_ura(module):
    captured_default: dict[str, str] = {}

    def fake_prompt(default: str) -> str:
        captured_default["value"] = default
        return "ura"

    result = module.choose_active_scenario(last_scenario="unknown", prompt=fake_prompt)

    assert captured_default["value"] == "ura"
    assert result == "ura"


def test_choose_active_scenario_cancelled(module):
    def fake_prompt(default: str) -> str:
        raise module.ScenarioSelectionCancelled()

    with pytest.raises(module.ScenarioSelectionCancelled):
        module.choose_active_scenario(last_scenario="ura", prompt=fake_prompt)
