from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, Optional


class PalMemoryManager:
    """Lightweight runtime persistence for PAL availability and chain snapshots.

    Stored schema (JSON):
    {
      "version": 1,
      "created_at": <unix>,
      "updated_at": <unix>,
      "updated_utc": "...",
      "scenario": "ura|unity_cup|...",
      "last_pal_available": true|false,
      "last_date_key": "Yx-Mm-Hh"|null,
      "last_turn": <int|null>,
      "chains": {
         "support_tazuna": {"step": 1, "last_date": "...", "last_turn": 12},
         "support_kashimoto": {"step": 2, "last_date": "...", "last_turn": 23},
         ...
      }
    }
    """

    VERSION = 1

    def __init__(self, path: Path, *, scenario: Optional[str] = None) -> None:
        self.path = path
        self.scenario: Optional[str] = (str(scenario).strip().lower() if scenario else None)
        self._data: Dict[str, object] = self._empty()
        self.load()

    # ---------------- Public API ----------------
    def load(self) -> None:
        if not self.path.exists():
            self._data = self._empty()
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self._data = self._empty()
            return
        self._data = self._merge_with_defaults(raw)
        stored_scenario = self._data.get("scenario")
        if self.scenario and stored_scenario and stored_scenario != self.scenario:
            self._data = self._empty()
            self.save()
        elif self.scenario and not stored_scenario:
            self._data["scenario"] = self.scenario
            self.save()

    def save(self) -> None:
        self._data["version"] = self.VERSION
        now = time.time()
        self._data["updated_at"] = now
        self._data["updated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
        if self.scenario is not None:
            self._data["scenario"] = self.scenario
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def reset(self) -> None:
        self._data = self._empty()
        try:
            if self.path.exists():
                self.path.unlink()
        finally:
            self.save()

    def record_availability(
        self,
        present: bool,
        *,
        date_key: Optional[str] = None,
        turn: Optional[int] = None,
        commit: bool = True,
    ) -> None:
        present = bool(present)
        self._data["last_pal_available"] = present
        if date_key is not None:
            self._data["last_date_key"] = date_key
        if turn is not None:
            try:
                self._data["last_turn"] = int(turn)
            except Exception:
                pass
        # If PAL is not available anymore (icon absent or chains ended),
        # clear optimistic next_energy flags to avoid stale positives.
        if not present:
            chains = self._data.get("chains")
            if isinstance(chains, dict):
                for k, entry in list(chains.items()):
                    if isinstance(entry, dict):
                        # Reset next_energy and do not advertise unknown step as actionable
                        if "next_energy" in entry:
                            entry["next_energy"] = False
                        # Optional: if a chain never had a step recorded, remove it
                        if entry.get("step") is None and "next_energy" in entry:
                            try:
                                del chains[k]
                            except Exception:
                                pass
        if commit:
            self.save()

    def record_chain_snapshot(
        self,
        support_name: str,
        steps: int,
        *,
        date_key: Optional[str] = None,
        turn: Optional[int] = None,
        next_energy: Optional[bool] = None,
        commit: bool = True,
    ) -> None:
        name = (support_name or "").strip()
        if not name:
            return
        if steps is None:
            steps = 0
        try:
            steps = int(steps)
        except Exception:
            steps = 0
        chains = self._data.get("chains")
        if not isinstance(chains, dict):
            chains = {}
            self._data["chains"] = chains
        entry = chains.get(name) or {}
        entry["step"] = steps
        if date_key is not None:
            entry["last_date"] = date_key
        if turn is not None:
            try:
                entry["last_turn"] = int(turn)
            except Exception:
                pass
        if next_energy is not None:
            entry["next_energy"] = bool(next_energy)
        chains[name] = entry
        if commit:
            self.save()

    def get_chain_step(self, support_name: str) -> Optional[int]:
        chains = self._data.get("chains")
        if not isinstance(chains, dict):
            return None
        entry = chains.get(support_name)
        if not isinstance(entry, dict):
            return None
        try:
            return int(entry.get("step"))
        except Exception:
            return None

    def export(self) -> Dict[str, object]:
        return json.loads(json.dumps(self._data))

    def any_next_energy(self) -> bool:
        # Require PAL availability in the last lobby snapshot
        if not bool(self._data.get("last_pal_available")):
            return False
        chains = self._data.get("chains")
        if not isinstance(chains, dict):
            return False
        for entry in chains.values():
            if isinstance(entry, dict) and entry.get("next_energy"):
                return True
        return False

    # -------- Run metadata compatibility (similar to SkillMemoryManager) --------
    def set_run_metadata(
        self,
        *,
        preset_id: Optional[str] = None,
        date_key: Optional[str] = None,
        date_index: Optional[int] = None,
        scenario: Optional[str] = None,
        commit: bool = True,
    ) -> None:
        changed = False
        if preset_id is not None and preset_id != self._data.get("preset_id"):
            self._data["preset_id"] = preset_id
            changed = True
        if date_key is not None and date_key != self._data.get("date_key"):
            self._data["date_key"] = date_key
            changed = True
        if date_index is not None:
            try:
                stored = int(self._data.get("date_index")) if self._data.get("date_index") is not None else None
            except Exception:
                stored = None
            if stored is None or int(date_index) > stored:
                self._data["date_index"] = int(date_index)
                changed = True
        scenario_value = (scenario or self.scenario)
        if scenario_value is not None:
            scenario_value = str(scenario_value).strip().lower()
            if scenario_value != self._data.get("scenario"):
                self._data["scenario"] = scenario_value
                changed = True
        if changed:
            now = time.time()
            self._data["updated_at"] = now
            self._data["updated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
            if commit:
                self.save()

    def get_run_metadata(self) -> Dict[str, object]:
        return {
            "preset_id": self._data.get("preset_id"),
            "date_key": self._data.get("date_key"),
            "date_index": self._data.get("date_index"),
            "created_at": self._data.get("created_at"),
            "updated_at": self._data.get("updated_at"),
            "updated_utc": self._data.get("updated_utc"),
        }

    def is_compatible_run(
        self,
        *,
        preset_id: Optional[str] = None,
        date_key: Optional[str] = None,
        date_index: Optional[int] = None,
        scenario: Optional[str] = None,
        stale_seconds: Optional[int] = None,
    ) -> bool:
        stored_preset = self._data.get("preset_id")
        if stored_preset and preset_id and stored_preset != preset_id:
            return False
        stored_date = self._data.get("date_key")
        stored_index = self._safe_int(self._data.get("date_index"))
        if stored_date and date_key:
            if stored_index is not None and date_index is not None:
                if int(date_index) < stored_index:
                    return False
            elif stored_date != date_key:
                return False
        elif stored_date and date_key is None:
            # Allow only if not stale
            if self._is_stale_gap(threshold=stale_seconds or 6 * 60 * 60):
                return False

        scenario_value = scenario if scenario is not None else self.scenario
        if scenario_value is not None:
            scenario_value = str(scenario_value).strip().lower()
        stored_scenario = self._data.get("scenario")
        if isinstance(stored_scenario, str):
            stored_scenario = stored_scenario.strip().lower() or None
        else:
            stored_scenario = None
        if scenario_value and stored_scenario and stored_scenario != scenario_value:
            return False
        if scenario_value and not stored_scenario:
            return False
        if stored_scenario and not scenario_value:
            return False
        if self._is_stale_gap(threshold=stale_seconds or 6 * 60 * 60):
            if stored_date and date_key and stored_date == date_key:
                pass
            else:
                return False
        return True

    # ---------------- Internals ----------------
    def _empty(self) -> Dict[str, object]:
        now = time.time()
        return {
            "version": self.VERSION,
            "created_at": now,
            "updated_at": now,
            "updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            "scenario": self.scenario,
            "last_pal_available": False,
            "last_date_key": None,
            "last_turn": None,
            "chains": {},
        }

    def _merge_with_defaults(self, payload: object) -> Dict[str, object]:
        data = self._empty()
        if not isinstance(payload, dict):
            return data
        if isinstance(payload.get("preset_id"), str):
            data["preset_id"] = payload.get("preset_id")
        if isinstance(payload.get("date_key"), str):
            data["date_key"] = payload.get("date_key")
        try:
            if payload.get("date_index") is not None:
                data["date_index"] = int(payload.get("date_index"))
        except Exception:
            pass
        if isinstance(payload.get("scenario"), str):
            data["scenario"] = payload["scenario"].strip().lower() or None
        if isinstance(payload.get("last_pal_available"), bool):
            data["last_pal_available"] = bool(payload["last_pal_available"])
        if isinstance(payload.get("last_date_key"), str):
            data["last_date_key"] = payload["last_date_key"]
        try:
            if payload.get("last_turn") is not None:
                data["last_turn"] = int(payload.get("last_turn"))
        except Exception:
            data["last_turn"] = None
        chains = payload.get("chains")
        if isinstance(chains, dict):
            cleaned: Dict[str, Dict[str, object]] = {}
            for name, entry in chains.items():
                if not isinstance(name, str) or not isinstance(entry, dict):
                    continue
                ce: Dict[str, object] = {}
                try:
                    if entry.get("step") is not None:
                        ce["step"] = int(entry.get("step"))
                except Exception:
                    ce["step"] = 0
                if isinstance(entry.get("last_date"), str):
                    ce["last_date"] = entry.get("last_date")
                try:
                    if entry.get("last_turn") is not None:
                        ce["last_turn"] = int(entry.get("last_turn"))
                except Exception:
                    pass
                cleaned[name] = ce
            data["chains"] = cleaned
        return data

    # -------- helpers (ported from SkillMemoryManager) --------
    @staticmethod
    def _safe_int(value: Optional[object], *, default: Optional[int] = None) -> Optional[int]:
        if value is None:
            return default
        try:
            return int(value)
        except Exception:
            return default

    @staticmethod
    def _is_number(value: object) -> bool:
        if value is None:
            return False
        try:
            float(value)
            return True
        except Exception:
            return False

    def _is_stale_gap(self, threshold: Optional[float] = None) -> bool:
        limit = threshold if threshold is not None else float(6 * 60 * 60)
        if limit <= 0:
            return False
        updated = self._data.get("updated_at")
        if not self._is_number(updated):
            return True
        try:
            age = time.time() - float(updated)
        except Exception:
            return True
        return age >= limit
