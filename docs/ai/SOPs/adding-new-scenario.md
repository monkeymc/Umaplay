---
title: SOP – Add a New Scenario
date: 2025-11-07T19:00:00-05:00
version: 1.0.0
owner: Umaplay maintainers
applies_to: [core-scenarios, config-pipeline, web-ui]
last_validated: 2025-11-07
related_prs: []
related_docs: [docs/ai/SYSTEM_OVERVIEW.md, docs/ai/SOPs/sop-config-back-front.md]
risk_level: medium
---

# Purpose
Document the repeatable steps for introducing a brand-new training scenario (e.g., "Grand Masters") to the Umaplay stack so the runtime, web UI, and configuration schema stay consistent. Use this SOP whenever gameplay adds a scenario that requires distinct policies, presets, or assets.

# Scope & Preconditions
- **Environments**: Local dev workstation with Python 3.10+ and Node 18+, bot repo cloned.
- **Access**: Ability to modify `core/`, `web/`, `prefs/`, and documentation directories.
- **Prerequisites**:
  - Scenario policies (scan/decide flows) either implemented or defined as stubs.
  - Scenario-specific YOLO weights or shared defaults identified.
  - Icons or imagery prepared for the web UI (`web/public/scenarios/`).
- **Impacted systems**: Python runtime (`core/`), config server (`server/`), web UI (`web/`), configuration samples (`prefs/`).
- **Estimated time**: 60–120 minutes depending on policy complexity.

# Inputs & Parameters
- **Scenario key**: machine-friendly slug (`"unity_cup"`, `"grand_masters"`).
- **Display label**: UI-facing name.
- **Policy functions**: `scan`, `decide` callables or imports.
- **Assets**: Scenario icon (PNG) sized ~32×32 for UI, optional preset defaults.
- **Config defaults**: Baseline preset list, advanced tuning, scenarioConfirmed default (usually `false`).

# Step-by-Step Procedure
1. **Add scenario module & registry hook**
   - **Files/paths**: `core/scenarios/<scenario>.py`, `core/scenarios/__init__.py`, `core/scenarios/registry.py`
   - **Commands:**
     ```bash
     # create module (example)
     copy core\scenarios\unity_cup.py core\scenarios\grand_masters.py
     ```
   - **Notes:**
     - Import `ScenarioPolicyRegistry` and register `SCAN_FN` and `DECIDE_FN`.
     - Reuse an existing policy temporarily if bespoke logic is pending.
     - Update `__all__` or module imports in `core/scenarios/__init__.py` to trigger registration on import.

2. **Extend runtime settings & defaults**
   - **Files/paths**: `core/settings.py`, `core/utils/skill_memory.py` (if scenario-specific paths differ)
   - **Commands:**
     ```bash
     rg "unity_cup" core/settings.py
     ```
   - **Notes:**
     - Update scenario normalization switch to include new key/aliases.
     - Ensure `resolve_skill_memory_path` and related helpers return per-scenario storage.
     - Mirror defaults (agent name, YOLO weights) or provide scenario-specific overrides.

3. **Wire config migration & schema**
   - **Files/paths**: `web/src/models/config.schema.ts`, `web/src/models/types.ts`, `web/src/store/configStore.ts`, `prefs/config.sample.json`, `server/utils.py`
   - **Commands:**
     ```bash
     npm run lint -- --fix
     ```
   - **Notes:**
     - Add scenario branch defaults inside the Zod schema (`scenarios.<key>`).
     - Update TypeScript discriminated unions (`ScenarioKey`, `GeneralConfig.activeScenario`).
     - Ensure `ensureScenarioMap()` + migrations seed presets array and `activePresetId`.
     - Update `server/utils.load_config()` to set sane defaults (active scenario + `scenarioConfirmed`).
     - Provide a sample preset entry in `prefs/config.sample.json` if relevant.

4. **Expose scenario in Web UI**
   - **Files/paths**: `web/src/components/general/GeneralForm.tsx`, optional scenario-specific components, `web/public/scenarios/`
   - **Notes:**
     - Add the toggle button with icon/label and ensure `setScenario()` handles the new key.
     - Keep accessibility text accurate; update highlighter logic if the scenario has constraints.
     - If presets require unique layout, add scenario-specific instructions/tooltips.

5. **Verify persistence & hotkey behavior**
   - **Files/paths**: `main.py`, `core/ui/scenario_prompt.py`, `core/utils/preset_overlay.py`
   - **Notes:**
     - Confirm `_select_scenario_before_start()` bypasses the prompt when `scenarioConfirmed` is true and the new scenario is active.
     - Update overlay text/images if scenario naming requires special formatting.

6. **Document & test**
   - **Files/paths**: `docs/ai/SYSTEM_OVERVIEW.md`, `README.md`, relevant SOP indexes.
   - **Commands:**
     ```bash
     npm run build
     pytest tests/core/test_settings.py -k scenario
     ```
   - **Notes:**
     - Add the scenario to architecture docs and changelog entries.
     - Update SOP references so future work starts here.
     - Capture screenshots for UI documentation if the layout changes.

# Verification & Acceptance Criteria
- Active scenario can be selected in Web UI; toggle shows highlight + confirmation note.
- Config saved to `prefs/config.json` contains new scenario branch with presets and `scenarioConfirmed` flag.
- Running `python main.py` skips TechEye prompt when the scenario was selected in UI.
- Scenario registry resolves policy without falling back to default.
- Tests covering `Settings.apply_config()` pass and include the new scenario key.

# Observability & Monitoring
- **Logs**: `[HOTKEY] Scenario selected` entries in console, migration logs in browser devtools from `configStore.loadLocal()`.
- **Files**: `prefs/runtime_skill_memory.json` should switch to a scenario-specific path (verify metadata).
- **UI**: Overlay toast (emerald background) shows scenario name when hotkey starts the bot.

# Failure Modes & Recovery
- **Symptom**: Scenario prompt still appears despite selection.
  - Verify `scenarioConfirmed` stored as `true` in config and `server/utils.load_config()` retains it.
- **Symptom**: Web UI loses legacy presets.
  - Inspect migration logs; ensure `migrateConfig()` maps legacy `presets[]` into `scenarios.<key>.presets` before validation.
- **Recovery**:
  1. Restore prior config from `prefs/config.json` backup or git history.
  2. Re-run migration after fixes with DevTools console `useConfigStore.getState().loadLocal()`.

# Post-Change Tasks
- Commit updated presets and documentation.
- Announce scenario availability in changelog / release notes.
- Schedule follow-up to train dedicated YOLO or policy models if needed.

# Open Questions
- What heuristics decide when a scenario deserves bespoke YOLO weights versus reusing URA defaults?
- Should scenario presets share race plans by default, or require new datasets per scenario?

# Change Log
- 2025-11-07 – v1.0.0 – Initial SOP covering configuration, runtime, and documentation touchpoints for new scenarios.
