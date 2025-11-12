---
status: plan_ready
---

# PLAN

## Objectives
- Provide configurable weak-turn SV, junior-year minimal mood, and lobby pre-check toggles that apply to both URA and Unity Cup without duplicating policy code.
- Ensure the lobby pre-check honors absolute safety guards (auto rest, summer prep, goal deadlines) while opportunistically training when high SV tiles exist.
- Maintain backward compatibility: presets default to current behavior, diagrams/notes stay accurate, and automated tests cover new logic.

## Steps (general; not per-file)
### Step 1 — Expose shared toggles in Settings and presets
**Goal:** Make weak-turn SV, junior mood override, and lobby pre-check thresholds available via Settings and runtime presets.
**Actions (high level):**
- Add scenario-keyed defaults for weak-turn SV and race/infirmary pre-check SV in Settings.
- Introduce global flags/values (e.g., `lobbyPrecheckEnable`, `juniorMinimalMood`) with preset extraction + serialization logic.
- Update preset schema / event processor so Web UI can surface the new knobs (include optional per-race tentative flag container).
**Affected files (expected):**
- `core/settings.py`
- `core/utils/event_processor.py` (and related preset schema helpers)
- Web preset schema / config files (JS/JSON) if applicable
**Quick validation:**
- Load presets in dev UI; verify new fields deserialize with scenario defaults when omitted.
- Confirm Settings logs show extracted values for both URA and Unity Cup.

### Step 2 — Implement lobby pre-check flow in base class and scenarios
**Goal:** Share a training-screen peek helper and integrate pre-check decisions before races/infirmary in both scenarios.
**Actions (high level):**
- Add `_peek_training_best_sv()` (or similar) to `LobbyFlow` to navigate into training, compute best allowed SV, and return safely.
- Cache peek results per date to avoid repeated scans within the same turn.
- In URA and Unity Cup `process_turn`, gate planned race, goal race, and infirmary actions behind the pre-check toggle while respecting auto-rest and summer-prep guards.
- Enforce hard deadline for goal races (e.g., turns left ≤ configured threshold) regardless of training value; integrate tentative planned race logic if provided.
**Affected files (expected):**
- `core/actions/lobby.py`
- `core/actions/ura/lobby.py`
- `core/actions/unity_cup/lobby.py`
- Possibly race planning helpers for tentative flags
**Quick validation:**
- Run dry lobby loop with mock high SV tile: confirm log shows pre-check skip of planned race/infirmary when enabled.
- Simulate critical goal with low turns remaining: ensure race still triggers even if SV high.

### Step 3 — Thread weak-turn SV and junior mood into training policies
**Goal:** Allow both scenario training policies to use new knobs without diverging.
**Actions (high level):**
- Extend calls to `decide_action_training` with `weak_turn_sv`, `junior_minimal_mood`, and scenario-specific race pre-check thresholds (if needed).
- Update URA and Unity Cup training policy functions: apply junior mood override during mood gate, integrate weak-turn SV when deciding late fallback/rest/WIT choices.
- Keep existing thresholds for other branches; document any adjustments in policy notes.
**Affected files (expected):**
- `core/actions/training_policy.py`
- `core/actions/ura/training_policy.py`
- `core/actions/unity_cup/training_policy.py`
- Policy documentation (`docs/ai/policies/.../notes.txt`, flows) as needed
**Quick validation:**
- Unit-test scenarios where minimal mood differs between junior vs later years.
- Confirm weak-turn SV triggers rest/WIT when best training SV is below new threshold.

### Step 4 — Surface UI/preset controls and documentation
**Goal:** Ensure configurability and docs stay consistent.
**Actions (high level):**
- Update Web UI forms / preset editors to expose new fields with defaults and validation (mood enum, numeric SV).
- Revise policy diagrams/notes to mention weak-turn and pre-check behavior if user-facing docs require it.
- Add feature flag documentation in relevant guides (`docs/ai/policies`, `docs/TODO.md` cleanup, changelog entry if used).
**Affected files (expected):**
- Web UI config components (`webui/...` or similar)
- `docs/ai/policies/**/flow_*.mmd` and `notes.txt` (if needed)
- `docs/TODO.md` / changelog entries
**Quick validation:**
- Create a preset via UI toggling new options; ensure saved JSON matches expectations.
- Regenerate Mermaid diagrams; confirm no syntax errors and behavior described matches new logic.

### Step 5 — Finalization
**Goal:** Stabilize, verify, and close out.
**Actions (high level):**
- Run unit/integration tests, linting, and type checks.
- Verify logs for peek helper show balanced navigation (no stuck training screen).
- Remove temporary logging/caching hacks; ensure docs referenced in objectives updated.
**Quick validation:**
- All tests green; manual dry run through both scenarios with toggle on/off shows expected lobby/training behavior.

## Test Plan
- **Unit:**
  - Lobby pre-check helper navigation (mock controller to ensure back navigation executed).
  - Training policy decisions for junior mood override and weak-turn threshold (both scenarios).
- **Integration/E2E:**
  - Scenario smoke run with toggle disabled (regression baseline).
  - Scenario run with toggle enabled and artificially high SV to confirm race/infirmary deferral.
  - Goal race scenario with few turns remaining to ensure hard deadline triggers race.
- **UX/Visual:**
  - Web UI preset editor displays new fields with default values; form validation prevents invalid mood strings/SV numbers.

## Verification Checklist
- [ ] Lint and type checks pass locally
- [ ] Lobby flows respect new toggle while keeping auto-rest/summer guards
- [ ] Training decisions honor weak-turn SV and junior mood overrides
- [ ] Web UI presets load/save new configuration options
- [ ] Documentation/diagrams updated without Mermaid errors

## Rollback / Mitigation
- Disable new toggle fields in presets (leave defaults) to revert to previous behavior without code changes.
- If necessary, revert commits touching Settings and lobby/training logic; restore prior diagrams/notes from version control.

## Open Questions (if any)
- Should goal race hard deadline be global or per-scenario? (Default proposal: global constant with preset override.)
- Preferred data model for marking planned races as tentative? (Extend `plan_races` entries or maintain separate toggle list.)
- Do we need distinct SV thresholds for infirmary vs. race pre-check, or reuse the same value initially?
