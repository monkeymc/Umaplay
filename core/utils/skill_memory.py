from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, Optional


class SkillMemoryManager:
    """Runtime persistence for skill sightings and purchases."""

    VERSION = 1
    ANY_GRADE = "__any__"
    STALE_SECONDS = 6 * 60 * 60  # 6 hours

    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: Dict[str, object] = self._empty()
        self.load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def load(self) -> None:
        """Read memory from disk if available."""
        if not self.path.exists():
            self._data = self._empty()
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            # Corrupted file → fall back to empty memory
            self._data = self._empty()
            return
        self._data = self._merge_with_defaults(raw)

    def save(self) -> None:
        """Persist memory to disk."""
        self._data["version"] = self.VERSION
        now = time.time()
        self._data["updated_at"] = now
        self._data["updated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(self._data, ensure_ascii=False, indent=2, sort_keys=True)
        self.path.write_text(serialized + "\n", encoding="utf-8")
        # Re-open file to ensure in-memory view matches on-disk structure (e.g. for watchers)
        self.load()

    def reset(self, *, persist: bool = True) -> None:
        """Reset in-memory state (optionally removing the file)."""
        self._data = self._empty()
        if persist:
            if self.path.exists():
                try:
                    self.path.unlink()
                except OSError:
                    # Ignore removal failure and fall back to writing the empty payload
                    self.save()
        else:
            now = time.time()
            self._data["updated_at"] = now
            self._data["updated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))

    def set_run_metadata(
        self,
        *,
        preset_id: Optional[str] = None,
        date_key: Optional[str] = None,
        date_index: Optional[int] = None,
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
            stored_date_index = self._safe_int(self._data.get("date_index"))
            if stored_date_index is None or date_index > stored_date_index:
                self._data["date_index"] = int(date_index)
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
    ) -> bool:
        """Return True when stored metadata does not contradict the provided snapshot."""
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
            # No fresh date info; rely on staleness guard only
            if self._is_stale_gap():
                return False

        if self._is_stale_gap():
            if stored_date and date_key and stored_date == date_key:
                pass
            else:
                return False
        return True

    def record_seen(
        self,
        skill_name: str,
        *,
        grade: Optional[str] = None,
        date_key: Optional[str] = None,
        turn: Optional[int] = None,
        commit: bool = True,
    ) -> None:
        self._record(
            bucket="skills_seen",
            skill_name=skill_name,
            grade=grade,
            date_key=date_key,
            turn=turn,
            increment=True,
            commit=commit,
        )

    def record_bought(
        self,
        skill_name: str,
        *,
        grade: Optional[str] = None,
        date_key: Optional[str] = None,
        turn: Optional[int] = None,
        commit: bool = True,
    ) -> None:
        self._record(
            bucket="skills_bought",
            skill_name=skill_name,
            grade=grade,
            date_key=date_key,
            turn=turn,
            increment=True,
            commit=commit,
        )

    def has_seen(self, skill_name: str, *, grade: Optional[str] = None) -> bool:
        return self._has("skills_seen", skill_name, grade=grade)

    def has_bought(self, skill_name: str, *, grade: Optional[str] = None) -> bool:
        return self._has("skills_bought", skill_name, grade=grade)

    def export(self) -> Dict[str, object]:
        """Return a deep copy of the current memory payload."""
        return json.loads(json.dumps(self._data))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _record(
        self,
        *,
        bucket: str,
        skill_name: str,
        grade: Optional[str],
        date_key: Optional[str],
        turn: Optional[int],
        increment: bool,
        commit: bool,
    ) -> None:
        name = (skill_name or "").strip()
        if not name:
            return
        grade_key = self._grade_key(grade)
        collection = self._data[bucket]
        assert isinstance(collection, dict)
        grade_map = collection.setdefault(name, {})
        assert isinstance(grade_map, dict)
        entry = grade_map.get(grade_key)
        now = time.time()
        if entry is None:
            entry = {
                "first_date": date_key,
                "first_turn": self._safe_int(turn),
                "last_date": date_key,
                "last_turn": self._safe_int(turn),
                "count": 1 if increment else 0,
                "updated_at": now,
            }
            grade_map[grade_key] = entry
        else:
            if entry.get("first_date") is None and date_key:
                entry["first_date"] = date_key
            if entry.get("first_turn") is None and turn is not None:
                entry["first_turn"] = self._safe_int(turn)
            if date_key:
                entry["last_date"] = date_key
            if turn is not None:
                entry["last_turn"] = self._safe_int(turn)
            if increment:
                entry["count"] = self._safe_int(entry.get("count"), default=0) + 1
            entry["updated_at"] = now
        if commit:
            self.save()

    def _has(self, bucket: str, skill_name: str, *, grade: Optional[str]) -> bool:
        name = (skill_name or "").strip()
        if not name:
            return False
        collection = self._data.get(bucket)
        if not isinstance(collection, dict):
            return False
        grade_map = collection.get(name)
        if not isinstance(grade_map, dict):
            return False
        if grade is None:
            return bool(grade_map)
        grade_key = self._grade_key(grade)
        if grade_key in grade_map:
            return True
        # Fallback: allow matches if "any" bucket was stored
        return self.ANY_GRADE in grade_map

    @staticmethod
    def _grade_key(grade: Optional[str]) -> str:
        if grade is None:
            return SkillMemoryManager.ANY_GRADE
        trimmed = grade.strip()
        return trimmed or SkillMemoryManager.ANY_GRADE

    @staticmethod
    def _safe_int(value: Optional[object], *, default: Optional[int] = None) -> Optional[int]:
        if value is None:
            return default
        try:
            return int(value)
        except Exception:
            return default

    def _empty(self) -> Dict[str, object]:
        now = time.time()
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
        return {
            "version": self.VERSION,
            "preset_id": None,
            "date_key": None,
            "date_index": None,
            "created_at": now,
            "updated_at": now,
            "updated_utc": now_iso,
            "skills_seen": {},
            "skills_bought": {},
        }

    def _merge_with_defaults(self, payload: object) -> Dict[str, object]:
        data = self._empty()
        if not isinstance(payload, dict):
            return data
        if isinstance(payload.get("preset_id"), str):
            data["preset_id"] = payload.get("preset_id")
        if isinstance(payload.get("date_key"), str):
            data["date_key"] = payload.get("date_key")
        idx_val = self._safe_int(payload.get("date_index"))
        if idx_val is not None:
            data["date_index"] = idx_val
        if self._is_number(payload.get("created_at")):
            data["created_at"] = float(payload["created_at"])
        if self._is_number(payload.get("updated_at")):
            data["updated_at"] = float(payload["updated_at"])
        utc_val = payload.get("updated_utc")
        if isinstance(utc_val, str) and utc_val:
            data["updated_utc"] = utc_val
        data["skills_seen"] = self._normalize_skill_map(payload.get("skills_seen"))
        data["skills_bought"] = self._normalize_skill_map(payload.get("skills_bought"))
        return data

    def _normalize_skill_map(self, mapping: object) -> Dict[str, Dict[str, Dict[str, object]]]:
        normalized: Dict[str, Dict[str, Dict[str, object]]] = {}
        if not isinstance(mapping, dict):
            return normalized
        for name, grade_map in mapping.items():
            if not isinstance(name, str) or not isinstance(grade_map, dict):
                continue
            cleaned_grades: Dict[str, Dict[str, object]] = {}
            for grade, info in grade_map.items():
                grade_key = self._grade_key(grade if isinstance(grade, str) else None)
                if not isinstance(info, dict):
                    continue
                cleaned_grades[grade_key] = {
                    "first_date": info.get("first_date") if isinstance(info.get("first_date"), str) else None,
                    "first_turn": self._safe_int(info.get("first_turn")),
                    "last_date": info.get("last_date") if isinstance(info.get("last_date"), str) else None,
                    "last_turn": self._safe_int(info.get("last_turn")),
                    "count": self._safe_int(info.get("count"), default=0),
                    "updated_at": float(info.get("updated_at", time.time()))
                    if self._is_number(info.get("updated_at"))
                    else time.time(),
                }
            if cleaned_grades:
                normalized[name] = cleaned_grades
        return normalized

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
        limit = threshold if threshold is not None else float(self.STALE_SECONDS)
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
