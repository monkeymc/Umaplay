from __future__ import annotations

import json
from pathlib import Path

import pytest

import server.utils as server_utils


@pytest.fixture(autouse=True)
def restore_server_utils(monkeypatch):
    # Reload after each test to avoid cross-test contamination of globals.
    import importlib

    module = importlib.import_module("server.utils")
    importlib.reload(module)
    yield
    importlib.reload(module)


@pytest.fixture
def patch_config_paths(monkeypatch, tmp_path: Path) -> Path:
    config_path = tmp_path / "config.json"
    sample_path = tmp_path / "config.sample.json"
    monkeypatch.setattr(server_utils, "CONFIG_PATH", config_path)
    monkeypatch.setattr(server_utils, "SAMPLE_CONFIG_PATH", sample_path)
    return config_path


def test_load_config_inserts_hierarchical_defaults(monkeypatch, patch_config_paths, tmp_path: Path):
    config_payload = {"version": 1, "general": {}}
    patch_config_paths.write_text(json.dumps(config_payload))

    data = server_utils.load_config()

    assert data.get("general", {}).get("activeScenario") == "ura"
    scenarios = data.get("scenarios")
    assert isinstance(scenarios, dict)
    assert "ura" in scenarios
    assert scenarios["ura"].get("presets") == []


def test_load_config_migrates_legacy_presets(monkeypatch, patch_config_paths, tmp_path: Path):
    legacy_preset = {
        "id": "legacy",
        "name": "Legacy",
        "priorityStats": ["SPD", "STA", "PWR", "GUTS", "WIT"],
        "targetStats": {"SPD": 1, "STA": 1, "PWR": 1, "GUTS": 1, "WIT": 1},
        "minimalMood": "NORMAL",
        "juniorStyle": "front",
        "skillsToBuy": [],
        "skillPtsCheck": 432,
        "plannedRaces": {},
    }
    config_payload = {
        "version": 1,
        "general": {"activeScenario": "unity_cup"},
        "presets": [legacy_preset],
        "activePresetId": "legacy",
    }
    patch_config_paths.write_text(json.dumps(config_payload))

    data = server_utils.load_config()

    scenarios = data.get("scenarios", {})
    ura_branch = scenarios.get("ura")
    assert isinstance(ura_branch, dict)
    assert any(p.get("id") == "legacy" for p in ura_branch.get("presets", []))
    assert ura_branch.get("activePresetId") == "legacy"
    # Legacy keys should no longer be present on the top level
    assert "presets" not in data
    assert "activePresetId" not in data


def test_load_config_preserves_existing_scenarios(monkeypatch, patch_config_paths, tmp_path: Path):
    config_payload = {
        "version": 1,
        "general": {"activeScenario": "unity_cup"},
        "scenarios": {
            "unity_cup": {
                "presets": [
                    {
                        "id": "cup",
                        "name": "Unity",
                        "priorityStats": ["SPD", "STA", "PWR", "GUTS", "WIT"],
                        "targetStats": {"SPD": 2, "STA": 2, "PWR": 2, "GUTS": 2, "WIT": 2},
                        "minimalMood": "NORMAL",
                        "juniorStyle": None,
                        "skillsToBuy": [],
                        "skillPtsCheck": 600,
                        "plannedRaces": {},
                    }
                ],
                "activePresetId": "cup",
            }
        },
    }
    patch_config_paths.write_text(json.dumps(config_payload))

    data = server_utils.load_config()

    scenarios = data.get("scenarios", {})
    assert "unity_cup" in scenarios
    assert scenarios["unity_cup"].get("activePresetId") == "cup"
    assert scenarios["unity_cup"].get("presets", [])[0]["id"] == "cup"
    # Ensure URA branch is still present for backwards compatibility
    assert "ura" in scenarios
