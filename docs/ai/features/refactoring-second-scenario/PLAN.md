---
status: plan_ready
---

# PLAN

## Objectives
- Add multi-scenario support (URA + Unity Cup) with minimal risk and zero regressions for URA.
- Introduce a clear runtime selector for scenario (UX on F2) and persist the choice.
- Decouple URA training policy into a scenario module; provide a Unity Cup stub to plug later.
- Keep shared flows (Lobby, Races, Events, Skills) intact; ensure skill memory and debug artifacts separate per scenario.

## Steps (general; not per-file)
### Step 0 — Establish URA regression harness
**Goal:** Capture current URA behavior in tests before any refactor moves code.
**Actions (high level):**
- Add focused unit/functional tests that snapshot URA training policy outcomes for representative inputs (summer vs. non-summer, low/high energy, mood variants).
- Cover lobby-to-training routing and skill purchase guards using canned perception outputs.
- Create reusable fixtures/mocks so later refactors reuse identical inputs.
**Affected files (expected):**
- `tests/core/actions/test_training_policy.py`
- `tests/core/actions/test_lobby_flow.py`
- Supporting fixtures under `tests/fixtures/`
**Quick validation:**
- `pytest tests/core/actions` passes and fails if training policy decisions change unexpectedly.

### Step 1 — Introduce scenario state (config + Settings)
**Goal:** Establish the concept of an active scenario without changing behavior (default URA).
**Actions (high level):**
- Extend configuration schema with `general.activeScenario: 'ura' | 'unity_cup'` (default `ura`, accept legacy aliases).
- Persist/load via store and server config endpoints; migrate old configs by defaulting to `ura`.
- Map `general.activeScenario` into `Settings` (e.g., `Settings.ACTIVE_SCENARIO`).
- Add regression tests covering schema round-trip and `Settings.apply_config` to guard defaults.
**Affected files (expected):**
- `web/src/models/config.schema.ts`, `web/src/models/types.ts`, `web/src/store/configStore.ts`, `server/utils.py`, `core/settings.py`.
- Tests: `tests/web/test_config_schema.py`, `tests/core/test_settings.py` (new or updated).
**Quick validation:**
- Export/import config shows `activeScenario`.
- On runtime start, logs show `ACTIVE_SCENARIO=ura`.
- `pytest tests/web/test_config_schema.py tests/core/test_settings.py` passes.

### Step 2 — F2 hotkey scenario chooser (UX)
**Goal:** Let users pick a scenario at start/stop time without Web UI friction.
**Actions (high level):**
- On F2, show a small modal/popup to select `URA` or `Unity Cup` (default to last saved `activeScenario`).
- If confirmed, set `Settings.ACTIVE_SCENARIO` and persist back to config; if canceled, do not start.
- Display a short overlay/toast with the chosen scenario.
**Affected files (expected):**
- `main.py` (hotkey loop + start toggle), optional small UI helper under `core/utils/`.
- **Quick validation:**
  - Press F2 → chooser appears → selecting Unity Cup shows overlay and starts.
  - Re-press F2 stops; on next start chooser defaults to last pick.

### Step 3 — Scenario-aware runtime plumbing
**Goal:** Parameterize agent tag and model selection by scenario (URA preserved by default).
**Actions (high level):**
- Add canonical scenario resolution so legacy values like `aoharu` map to `unity_cup`.
- Pass the scenario-derived agent/tag into `Player`’s `PollConfig` and Waiter; separate debug directories.
- Keep training policy behavior URA-only for now; this step must not change decisions.
**Affected files (expected):**
- `core/settings.py`, `main.py` model/engine creation, `core/agent.py` (Waiter tag init).
**Quick validation:**
  - Logs show `agent=unity_cup` when Unity Cup is selected; runs proceed normally under URA behavior.

### Step 4 — Extract training policy into scenario modules (no behavior change)
**Goal:** Create a clean seam for policies; move URA code as-is and provide a Unity Cup stub.
**Actions (high level):**
- Create `core/scenarios/` with `ura/` and `unity_cup/` packages.
- Move current `decide_action_training` (and helpers if needed) under `ura/`.
- Add a `registry` that returns `(scan_training_screen, decide_action_training)` by scenario; initial Unity Cup stub reuses URA to avoid behavior drift.
- Update the runtime to call through the registry based on `Settings.ACTIVE_SCENARIO`.
**Affected files (expected):**
- `core/scenarios/**`, `core/actions/training_policy.py` (delegation), `core/actions/training_check.py` (shared), `core/agent.py`/`lobby.py` (invoke via resolver).
**Quick validation:**
  - URA decisions match pre-refactor logs on sample captures.
  - Selecting Unity Cup still runs (functionally identical to URA for now).

### Step 5 — Separate skill memory per scenario
**Goal:** Avoid cross-scenario contamination in skills_seen/bought.
**Actions (high level):**
- Include scenario in run metadata and derive a scenario-specific memory file (e.g., `runtime_skill_memory.ura.json` / `...unity_cup.json`).
- Reset memory when scenario changes mid-session.
**Affected files (expected):**
- `core/utils/skill_memory.py`, `core/agent.py`, `core/settings.py`.
- **Quick validation:**
- After switching from URA to Unity Cup, a different runtime_skill_memory file is used.

### Step 6 — Web UI polish for scenario clarity
**Goal:** Make the scenario toggle discoverable and avoid confusion with event scenario preferences.
**Actions (high level):**
- Add a simple “Active Scenario” control in the Scenario tab; clarify copy that event `preset.event_setup.scenario` is for event prefs.
- Ensure save/load/export maintain both fields without collision.
**Affected files (expected):**
- `web/src/pages/Home.tsx`, `web/src/components/general/*`, `web/src/store/configStore.ts`.
**Quick validation:**
- Toggle visible and persisted; exporting config shows both `general.activeScenario` and preset event prefs intact.

### Step 7 — Regression tests and guardrails
**Goal:** Prove URA parity and basic scenario selection correctness.
**Actions (high level):**
- Add unit tests for URA training decisions on fixed SV inputs; confirm unchanged.
- Add tests for Waiter tag selection and skill memory path derivation by scenario.
- Add a smoke test: start, enter Lobby, stop; ensure no exceptions under both scenarios.
**Affected files (expected):**
- `tests/**`.
**Quick validation:**
- Tests pass locally/CI; URA logs match baselines.

### Step 8 — Finalization
**Goal:** Stabilize, verify, and close out.
**Actions (high level):**
- Lint/type-check; small cleanups; ensure defaults safe when Aoharu weights are missing.
- Update minimal docs notes in System Overview (optional) referencing scenario support.
**Affected files (expected):**
- Lint/test configs, optional docs touch-up.
**Quick validation:**
- All checks green; F2 chooser + scenario separation working.

## Test Plan
- **Unit:**
  - URA `decide_action_training` parity tests with canned `sv_rows` and date/mood/energy inputs.
  - Resolver returns URA functions when `activeScenario=ura`, Unity Cup stub (or URA proxy) when `unity_cup`.
  - Skill memory manager writes/reads separate files per scenario.
- **Integration/E2E:**
  - F2 chooser flow: cancel (no start), select scenario (starts), persists choice.
  - Unity Cup selection uses `agent=unity_cup` tag; debug artifacts are separated; no crashes during Lobby → Training loop.
  - Config export/import preserves `general.activeScenario` and preset event prefs.
- **UX/Visual:**
  - Scenario toggle in Web UI visible, defaulting to URA; helper text distinguishes it from event prefs.
  - Preset overlay shows active preset; short toast displays chosen scenario on start.

## Verification Checklist
- [ ] Lint and type checks pass locally
- [ ] URA flows behave as before (logs/decisions parity on samples)
- [ ] F2 chooser works and persists selection
- [ ] Debug artifacts and skill memory separate per scenario
- [ ] No crashes with missing Aoharu weights (fallback applies)

## Rollback / Mitigation
- Set `general.activeScenario` to `ura` in config to force URA behavior.
- Disable chooser temporarily by reverting the F2 popup call (guard behind a flag) and default to URA.
- If regressions persist, revert the scenario registry delegation while keeping the config field (non-breaking).

## Open Questions
- Should runtime selection rely solely on `general.activeScenario`, keeping `preset.event_setup.scenario` strictly for event preference logic? (Recommended.)
- Preferred F2 chooser implementation: small desktop modal (e.g., Tkinter) vs. in-game overlay + keyboard navigation?
- Do we want a single universal YOLO for both scenarios or per-scenario weights? Initial plan assumes per-scenario, with URA fallback.
