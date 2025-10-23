---
status: plan_ready
---

# PLAN

## Objectives
- Provide a general-config toggle plus SV threshold that triggers a training sneak peek before lobby actions such as races, infirmary visits, or rest when high-value tiles exist.
- Allow individual scheduled races to opt into the sneak peek so low-priority events can be skipped automatically when good training appears.
- Ensure backend decisions respect the new toggles without regressing existing race planning, and surface the controls in the Web UI with backward-compatible config storage.

## Steps (general; not per-file)
### Step 1 — Extend configuration schema and persistence
**Goal:** Introduce new config fields with safe defaults and migrations.
**Actions (high level):**
- Add general-level fields for `checkTrainingFirst` and `trainingSvThreshold` in TS types, Zod schema, Zustand store migrations, and sample config JSON.
- Update preset schema to store per-race metadata (name, allowSneakPeek) while migrating existing string-only `plannedRaces` entries.
- Ensure export/import mirrors the new structure without breaking older configs.
**Affected files (expected):**
- `web/src/models/types.ts`
- `web/src/models/config.schema.ts`
- `web/src/store/configStore.ts`
- `prefs/config.sample.json`
**Quick validation:**
- Import/export a legacy config and confirm new fields populate defaults without errors in console logs.

### Step 2 — Surface controls in Web UI
**Goal:** Expose the toggles and threshold inputs to users.
**Actions (high level):**
- Add general settings controls (switch + numeric input) in `GeneralForm.tsx` with appropriate validation and tooltips.
- Enhance `RaceScheduler` to display per-race sneak-peek toggle, ensuring UI handles new race metadata.
- Adjust any preset panels or helper components that assume `plannedRaces` is a string map.
**Affected files (expected):**
- `web/src/components/general/GeneralForm.tsx`
- `web/src/components/presets/RaceScheduler.tsx`
- `web/src/components/presets/PresetPanel.tsx`
**Quick validation:**
- Run the dev UI, toggle options, and verify Zustand state updates via React DevTools.

### Step 3 — Propagate settings to backend runtime
**Goal:** Make backend aware of the new configuration data.
**Actions (high level):**
- Extend `Settings` defaults, `apply_config()`, and `extract_runtime_preset()` to capture general toggle/threshold and race-level sneak peek flags.
- Update any helpers consuming `plan_races` to handle richer objects.
- Ensure runtime settings include sensible fallbacks when toggles disabled.
**Affected files (expected):**
- `core/settings.py`
- `core/actions/lobby.py`
- `core/actions/race.py`
**Quick validation:**
- Load config through backend (e.g., run `python main.py`) and confirm logs print the new settings without tracebacks.

### Step 4 — Integrate sneak peek logic into lobby/training flow
**Goal:** Modify decision flow to respect thresholds and per-race flags.
**Actions (high level):**
- Add sneak-peek calls in `LobbyFlow.process_turn()` before racing/infirmary/rest when toggles apply, invoking a lightweight training scan.
- Reuse `compute_support_values()` to compare SV against threshold and decide whether to navigate to training or continue planned action.
- Guard against repeated scans within the same turn and ensure state cleanup when action changes.
**Affected files (expected):**
- `core/actions/lobby.py`
- `core/actions/training_policy.py`
- `core/actions/training_check.py`
- `core/agent.py`
**Quick validation:**
- Run a simulated turn with debug logging enabled and confirm the flow opts into training when SV exceeds threshold.

### Step 5 — Finalization and verification
**Goal:** Stabilize, verify, and close out.
**Actions (high level):**
- Run TypeScript lint/build and Python formatting/tests as applicable.
- Exercise UI toggles plus backend flows in an end-to-end dry run.
- Update any relevant documentation or release notes if required.
**Quick validation:**
- All lint/test suites pass and manual run showcases skip behavior toggling correctly.

## Test Plan
- **Unit:** Add tests for config store migrations and `Settings.extract_runtime_preset()` to ensure new fields propagate correctly.
- **Integration/E2E:** Perform manual bot runs with and without the sneak peek enabled, observing race skipping based on configured thresholds; verify per-race toggle overrides behavior.
- **UX/Visual:** Validate UI renders new controls properly in light/dark themes and that toggles persist after reload.

## Verification Checklist
- [ ] Lint and type checks pass locally
- [ ] Critical lobby/race flows behave as expected with toggles ON/OFF
- [ ] No PII in logs; metrics/traces updated (if applicable)
- [ ] Feature flag toggles behave (if applicable)

## Rollback / Mitigation
- Disable the new general toggle to restore original behavior; if necessary, revert to previous config schema and rollback associated code changes via git revert.

## Open Questions (if any)
- Should the SV threshold remain global or allow per-preset overrides for future flexibility?
- When sneak peek is enabled, do we re-check training before every lobby action (race, infirmary, rest) or only for races by default?
- What is the expected behavior if scanning fails (e.g., YOLO returns no tiles) — retry, log, or proceed with original action?
