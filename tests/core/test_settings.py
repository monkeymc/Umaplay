from __future__ import annotations

import importlib
from typing import Dict, Any

import pytest


def _minimal_general(active_scenario: str | None = None) -> Dict[str, Any]:
    general: Dict[str, Any] = {
        "mode": "steam",
        "windowTitle": "Umamusume",
        "fastMode": False,
        "tryAgainOnFailedGoal": True,
        "maxFailure": 20,
        "acceptConsecutiveRace": True,
        "advanced": {
            "hotkey": "F2",
            "debugMode": True,
            "useExternalProcessor": False,
            "externalProcessorUrl": "http://127.0.0.1:8001",
            "autoRestMinimum": 26,
            "undertrainThreshold": 6,
            "topStatsFocus": 3,
            "skillCheckInterval": 3,
            "skillPtsDelta": 60,
        },
    }
    if active_scenario is not None:
        general["activeScenario"] = active_scenario
    return general


def _scenario_branch(preset_id: str, *, minimum_skill_pts: int) -> Dict[str, Any]:
    return {
        "presets": [
            {
                "id": preset_id,
                "name": "Preset",
                "priorityStats": ["SPD", "STA", "PWR", "GUTS", "WIT"],
                "targetStats": {"SPD": 1, "STA": 1, "PWR": 1, "GUTS": 1, "WIT": 1},
                "minimalMood": "NORMAL",
                "juniorStyle": None,
                "skillsToBuy": [],
                "skillPtsCheck": minimum_skill_pts,
                "plannedRaces": {},
            }
        ],
        "activePresetId": preset_id,
    }


@pytest.fixture
def fresh_settings():
    module = importlib.import_module("core.settings")
    importlib.reload(module)
    yield module.Settings
    importlib.reload(module)


def test_apply_config_sets_default_active_scenario(fresh_settings):
    cfg = {
        "general": _minimal_general(),
        "scenarios": {
            "ura": _scenario_branch("ura", minimum_skill_pts=600),
            "unity_cup": _scenario_branch("unity", minimum_skill_pts=700),
        },
    }

    fresh_settings.apply_config(cfg)

    assert getattr(fresh_settings, "ACTIVE_SCENARIO") == "ura"
    assert getattr(fresh_settings, "MINIMUM_SKILL_PTS") == 600


def test_apply_config_respects_configured_active_scenario(fresh_settings):
    cfg = {
        "general": _minimal_general("unity_cup"),
        "scenarios": {
            "ura": _scenario_branch("ura", minimum_skill_pts=500),
            "unity_cup": _scenario_branch("unity", minimum_skill_pts=650),
        },
    }

    fresh_settings.apply_config(cfg)

    assert getattr(fresh_settings, "ACTIVE_SCENARIO") == "unity_cup"
    assert getattr(fresh_settings, "MINIMUM_SKILL_PTS") == 650


def test_apply_config_falls_back_when_branch_missing(fresh_settings):
    cfg = {
        "general": _minimal_general("unity_cup"),
        "scenarios": {
            "ura": _scenario_branch("ura", minimum_skill_pts=620),
        },
    }

    fresh_settings.apply_config(cfg)

    assert getattr(fresh_settings, "ACTIVE_SCENARIO") == "unity_cup"
    # Should fall back to URA presets since Unity Cup branch is missing
    assert getattr(fresh_settings, "MINIMUM_SKILL_PTS") == 620


def test_apply_config_legacy_presets_structure_still_supported(fresh_settings):
    cfg = {
        "general": _minimal_general("unity_cup"),
        "presets": _scenario_branch("legacy", minimum_skill_pts=555)["presets"],
        "activePresetId": "legacy",
    }

    fresh_settings.apply_config(cfg)

    assert getattr(fresh_settings, "ACTIVE_SCENARIO") == "unity_cup"
    assert getattr(fresh_settings, "MINIMUM_SKILL_PTS") == 555


def test_apply_config_aliases_aoharu_to_unity_cup(fresh_settings):
    cfg = {
        "general": _minimal_general("aoharu"),
        "scenarios": {
            "ura": _scenario_branch("ura", minimum_skill_pts=610),
            "unity_cup": _scenario_branch("unity", minimum_skill_pts=740),
        },
    }

    fresh_settings.apply_config(cfg)

    assert getattr(fresh_settings, "ACTIVE_SCENARIO") == "unity_cup"
    assert getattr(fresh_settings, "ACTIVE_AGENT_NAME") == fresh_settings.AGENT_NAME_UNITY_CUP
    assert getattr(fresh_settings, "ACTIVE_YOLO_WEIGHTS") == fresh_settings.YOLO_WEIGHTS_UNITY_CUP
