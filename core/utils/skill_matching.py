# core/utils/skill_matching.py
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from core.utils.text import (
    fix_common_ocr_confusions,
    fuzzy_ratio,
    tokenize_ocr_text,
)


_DATASET_ROOT = Path(__file__).resolve().parents[2] / "datasets" / "in_game"
_SKILLS_JSON = _DATASET_ROOT / "skills.json"
_OVERRIDES_JSON = _DATASET_ROOT / "skill_matching_overrides.json"


@dataclass
class _SkillRule:
    require_tokens: Set[str] = field(default_factory=set)
    forbid_tokens: Set[str] = field(default_factory=set)
    require_any_groups: List[Set[str]] = field(default_factory=list)

    def ensure_sets(self) -> None:
        self.require_tokens = set(self.require_tokens)
        self.forbid_tokens = set(self.forbid_tokens)
        self.require_any_groups = [set(group) for group in self.require_any_groups if group]


class SkillMatcher:
    _singleton: Optional["SkillMatcher"] = None

    def __init__(
        self,
        *,
        rules: Dict[str, _SkillRule],
        target_tokens: Dict[str, Set[str]],
    ) -> None:
        self._rules = rules
        self._target_tokens = target_tokens

    @classmethod
    def from_dataset(cls) -> "SkillMatcher":
        if cls._singleton is None:
            cls._singleton = cls._build()
        return cls._singleton

    @staticmethod
    def _normalize_name(name: str) -> str:
        text = fix_common_ocr_confusions(name or "")
        text = text.strip().lower()
        if not text:
            return ""
        text = " ".join(text.split())
        table = str.maketrans("", "", "·•|[](){}:;,.!?\"'`’“”○◎×")
        return text.translate(table)

    @classmethod
    def _build(cls) -> "SkillMatcher":
        skills = cls._load_skills()
        overrides = cls._load_overrides()

        target_tokens: Dict[str, Set[str]] = {}
        for name in skills:
            norm = cls._normalize_name(name)
            target_tokens[name] = set(tokenize_ocr_text(norm))

        rules: Dict[str, _SkillRule] = {name: _SkillRule() for name in skills}

        # Apply manual overrides first.
        for entry in overrides:
            require = cls._expand_tokens(entry.get("require_tokens", []))
            forbid = cls._expand_tokens(entry.get("forbid_tokens", []))
            require_any = cls._expand_token_groups(entry.get("require_any", []))
            for target in entry.get("targets", []):
                rules.setdefault(target, _SkillRule())
                rules[target].require_tokens.update(require)
                rules[target].forbid_tokens.update(forbid)
                if require_any:
                    rules[target].require_any_groups.extend(require_any)

        # Auto-require unique tokens and forbid conflicting extras.
        token_frequency: Dict[str, int] = {}
        for tokens in target_tokens.values():
            for token in tokens:
                token_frequency[token] = token_frequency.get(token, 0) + 1

        for name, tokens in target_tokens.items():
            unique = {tok for tok in tokens if token_frequency.get(tok, 0) == 1}
            if unique:
                rules[name].require_tokens.update(unique)

        skill_names = list(target_tokens.keys())
        for i, name_a in enumerate(skill_names):
            tokens_a = target_tokens[name_a]
            if not tokens_a:
                continue
            for j in range(i + 1, len(skill_names)):
                name_b = skill_names[j]
                tokens_b = target_tokens[name_b]
                if not tokens_b:
                    continue
                if tokens_a < tokens_b:
                    diff = tokens_b - tokens_a
                    if diff:
                        rules[name_a].forbid_tokens.update(diff)
                elif tokens_b < tokens_a:
                    diff = tokens_a - tokens_b
                    if diff:
                        rules[name_b].forbid_tokens.update(diff)

        for rule in rules.values():
            rule.ensure_sets()

        return cls(rules=rules, target_tokens=target_tokens)

    @staticmethod
    def _load_skills() -> List[str]:
        if not _SKILLS_JSON.exists():
            return []
        data = json.loads(_SKILLS_JSON.read_text(encoding="utf-8"))
        names = []
        for entry in data:
            name = entry.get("name") if isinstance(entry, dict) else None
            if name:
                names.append(str(name))
        return names

    @staticmethod
    def _load_overrides() -> List[Dict[str, object]]:
        if not _OVERRIDES_JSON.exists():
            return []
        data = json.loads(_OVERRIDES_JSON.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []

    @staticmethod
    def _expand_tokens(raw_tokens: Sequence[str]) -> Set[str]:
        tokens: Set[str] = set()
        for token in raw_tokens:
            tokens.update(tokenize_ocr_text(token))
        return tokens

    @staticmethod
    def _expand_token_groups(raw_groups: Sequence[Sequence[str]]) -> List[Set[str]]:
        groups: List[Set[str]] = []
        for group in raw_groups:
            aggregated: Set[str] = set()
            for token in group:
                aggregated.update(tokenize_ocr_text(token))
            if aggregated:
                groups.append(aggregated)
        return groups

    def evaluate(
        self,
        norm_text: str,
        tokens: Sequence[str],
        target: str,
        normalized_target: str,
        *,
        threshold: float,
    ) -> Tuple[bool, str, float]:
        if not norm_text:
            return False, "empty_text", 0.0

        score = fuzzy_ratio(norm_text, normalized_target) if normalized_target else 0.0
        token_set = set(tokens)
        rule = self._rules.get(target)

        if rule:
            missing_req = rule.require_tokens - token_set
            if missing_req:
                return False, f"missing_req:{','.join(sorted(missing_req))}", score
            forbidden = rule.forbid_tokens & token_set
            if forbidden:
                return False, f"forbid:{','.join(sorted(forbidden))}", score
            for group in rule.require_any_groups:
                if group and not (group & token_set):
                    return False, f"missing_any:{'/'.join(sorted(group))}", score

        if normalized_target and normalized_target in norm_text:
            return True, "contains", max(score, 1.0)

        if score >= threshold:
            return True, f"score:{score:.2f}", score

        return False, f"score:{score:.2f}", score

    def matches(
        self,
        norm_text: str,
        tokens: Sequence[str],
        target: str,
        normalized_target: str,
        *,
        threshold: float,
    ) -> bool:
        return self.evaluate(
            norm_text, tokens, target, normalized_target, threshold=threshold
        )[0]
