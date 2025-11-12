---
date: 2025-11-11T01:56:00-05:00
topic: Weak turn, junior mood override, and lobby pre-check for URA and Unity Cup
status: research_complete
---

# RESEARCH — weak-turn-double-mood-lookup-sv

## Research Question
Add three cross-scenario, UI-configurable policy features without code duplication: (1) weak-turn SV threshold, (2) junior-year minimal mood override, and (3) lobby "check first" pre-check that can skip infirmary/planned races when a high-value training opportunity exists.

## Summary (≤ 10 bullets)
- Centralize new knobs in Settings and per-preset config; avoid scenario forks by using scenario-keyed defaults.
- Implement a base LobbyFlow pre-check helper that peeks at training best SV and returns to lobby safely.
- Honor absolute guards: auto-rest minimum and summer-prep rest remain unmodified by the pre-check toggle.
- Add planned/goal race pre-checks: allow training if best SV ≥ scenario threshold; enforce a hard deadline (e.g., ≤5 turns) for critical goals.
- Extend training policy to consume `weak_turn_sv` and `junior_minimal_mood` (applied only in junior year).
- Scenario defaults: URA weak-turn 1.0, pre-check race SV 2.5; Unity Cup weak-turn 1.75, pre-check race SV 4.0.
- Preserve existing risk gating and hints; do not change scoring functions.
- Minimal surface changes: new Settings keys, preset extraction, one shared lobby helper, small wiring in both scenarios.
- Backward-compatible; toggles default off so current behavior is unchanged.

## Detailed Findings (by area)
### Area: Settings and Preset wiring
- Why relevant: New knobs must be read by both scenarios and overridable via Web UI presets.
- Files & anchors (path:line_start–line_end):
  - `core/settings.py:143–177` — common policy settings (REFERENCE_STATS, PRIORITY_STATS, AUTO_REST_MINIMUM, MINIMAL_MOOD, ACTIVE_SCENARIO, overlay options).
- Proposed additions:
  - `WEAK_TURN_SV_BY_SCENARIO = {"ura": 1.0, "unity_cup": 1.75}`
  - `RACE_PRECHECK_SV_BY_SCENARIO = {"ura": 2.5, "unity_cup": 4.0}`
  - `LOBBY_PRECHECK_ENABLE: bool = False` (preset boolean)
  - `JUNIOR_MINIMAL_MOOD: str | None = None` (if set, used only during junior year)
  - Enhance `Settings.extract_runtime_preset(...)` to read `weakTurnSv`, `racePrecheckSv`, `lobbyPrecheckEnable`, `juniorMinimalMood` (scenario overrides allowed).

### Area: Lobby flows (Unity Cup and URA)
- Why relevant: Injection points for pre-check logic before infirmary and planned/goal races.
- Files & anchors:
  - Unity Cup: `core/actions/unity_cup/lobby.py:101–221` — full `process_turn()` ladder, including planned race guard, infirmary, rest, and transition to training.
  - URA: `core/actions/ura/lobby.py:97–216` — same structure; early goal race checks `_maybe_do_goal_race()`.
- Proposed shared helper in base `LobbyFlow` (new method):
  - `_peek_training_best_sv(min_sv_gate: float | None = None) -> tuple[float, dict]`
    - Steps: click training, call `scan_training_screen(...)` + `get_compute_support_values()`, compute best allowed_by_risk SV and its tile, then click BACK to return to lobby; include guardrails/timeouts.
    - Return best SV and optional metadata (tile, notes). If screen nav fails, return `(0.0, {"reason": "peek_failed"})`.
- Pre-check gating (toggle-controlled) to apply in both `process_turn` ladders:
  - Do NOT run pre-check if `energy <= auto_rest_minimum` (absolute rest) or if summer-prep rest gate is active (energy ≤50 and summer ≤2 turns).
  - Before consuming planned race or early goal race: if `precheckEnable` and `bestSV >= RACE_PRECHECK_SV_BY_SCENARIO[scenario]`, skip race this turn and go training instead; for critical goals, enforce a hard deadline (e.g., `turns_left <= 5` → race regardless).
  - Before infirmary: if `precheckEnable` and `bestSV >= SUPER_HIGH_SV` (use same SV threshold as race pre-check for simplicity), prefer training and defer infirmary to next turn; otherwise proceed to infirmary.

### Area: Training policy (both scenarios)
- Why relevant: Incorporate weak-turn and junior-mood overrides without forking code.
- Files & anchors:
  - Unity Cup: `core/actions/unity_cup/training_policy.py:454–758` — late-stage mood, summer, WIT, energy, race fallback and final fallbacks.
  - URA: `core/actions/ura/training_policy.py:460–760` — equivalent branches with different bins.
  - Shared callsite: `core/actions/training_policy.py:80–108` — passes minimal_mood and other knobs to scenario policies.
- Proposed signature additions (both scenario functions):
  - Add `weak_turn_sv: float | None = None`, `junior_minimal_mood: str | None = None`.
  - Inside function:
    - If `is_junior_year(di)` and `junior_minimal_mood`, substitute `minimal_mood` for the mood-gate.
    - Use `weak_turn_sv` for the weak-turn fallback: when no better options and energy is modest (existing ladder uses `<= 70`), prefer REST/WIT when `best_allowed_any < weak_turn_sv` (instead of hard-coded late bins).

### Area: Scoring system
- Why relevant: Determines SV; confirm no code duplication required here.
- Files & anchors:
  - Unity Cup scoring: `core/actions/unity_cup/training_check.py:200–352` — cameos, hints, rainbow combo, spirits, dynamic risk, greedy flag.
  - URA scoring: `core/actions/ura/training_check.py:9–150` — similar structure with different constants.
- Outcome: No changes required. Pre-check uses existing compute functions.

## 360° Around Target(s)
- Target file(s):
  - `core/actions/lobby.py` (add `_peek_training_best_sv` in base class)
  - `core/actions/unity_cup/lobby.py` and `core/actions/ura/lobby.py` (call pre-check helper at the right steps)
  - `core/actions/unity_cup/training_policy.py` and `core/actions/ura/training_policy.py` (accept new params and apply logic)
  - `core/actions/training_policy.py` (thread preset values down to scenario policies)
  - `core/settings.py` (add defaults, preset extraction)
  - Optional: `core/utils/event_processor` and web UI preset schema (to expose new fields)
- Dependency graph (depth 2):
  - `core/actions/training_policy.py` → `scan_training_screen`, `get_compute_support_values`, `get_decide_action_training`
  - `core/actions/*/lobby.py` → base `LobbyFlow`, `extract_*` utils, `RaceIndex`, `Waiter`
  - `core/actions/*/training_policy.py` → `Settings`, `date_uma`, `training_policy_utils`

## Open Questions / Ambiguities
- Where should the "critical goal hard deadline" be configured? Proposal: `Settings.GOAL_RACE_HARD_DEADLINE_TURNS = 5` with preset override.
- For planned races, how should "tentative" be stored? Options:
  1) Extend `plan_races` values to objects: `{ "name": "XXX", "tentative": true }`.
  2) Keep `plan_races` as-is and add `TENTATIVE_RACE_KEYS: set[str]` to presets.
- Should the infirmary pre-check use a separate SV threshold from race pre-check? Default to same; allow optional `infirmaryPrecheckSv` later if needed.
- Junior minimal mood values: accept strings in `{"bad","normal","good","great"}` (normalized to existing MOOD_MAP keys)?
- Performance: A peek implies an extra navigation to training then back. Acceptable? We can cache `bestSV` for the current date key to avoid repeated scans.

## Suggested Next Step
- Draft PLAN.md with concrete code edits:
  - Add new Settings keys and preset extraction.
  - Implement `LobbyFlow._peek_training_best_sv()` (navigate → scan → compute → back), store last peek result by date_key.
  - Insert pre-checks in both scenario `process_turn()` flows (order: planned/goal race → infirmary; respecting rest/summer absolutes).
  - Update both scenario training policies to accept `weak_turn_sv` and `junior_minimal_mood` and apply in mood/late fallback.
  - Extend web preset schema and UI to expose: `weakTurnSv`, `lobbyPrecheckEnable`, `racePrecheckSv`, `juniorMinimalMood`, and optional per-race tentative toggle.
  - Add tests: simulate lobby frames where planned race exists vs. high SV; verify hard deadline forces race; verify junior mood override triggers recreation only in Y1.
