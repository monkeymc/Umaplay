---
date: 2025-10-22T19:04:00-05:00
topic: sneak-peak-training
status: research_complete
---

# RESEARCH — sneak-peak-training

## Research Question
Introduce configurable "check training first" heuristics that can bypass scheduled races or other lobby actions when a training tile exceeds a user-defined SV threshold.

## Summary (≤ 10 bullets)
- **Lobby flow**: `core/actions/lobby.py` currently performs race/infirmary/rest actions before visiting training when guards pass; no hook exists for an SV-based pre-check.
- **Training evaluation**: `core/actions/training_policy.py` and `core/actions/training_check.py` already compute SVs and could expose thresholds for early exits when invoked from lobby.
- **Config plumbing**: `core/settings.py` maps both general and preset settings but lacks fields for a pre-training peek toggle or SV threshold.
- **Frontend general config**: `web/src/components/general/GeneralForm.tsx` has no control for a pre-training check toggle or numeric SV threshold.
- **Schema/types**: `web/src/models/types.ts` and `web/src/models/config.schema.ts` do not define new fields required for the feature.
- **Race scheduler data**: `plannedRaces` in presets is a `Record<string, string>`; adding per-race flags requires schema evolution for backward compatibility.
- **Runtime preset extraction**: `Settings.extract_runtime_preset()` must surface both the general toggle/threshold and per-race overrides for consumption inside lobby/training flows.
- **Agent integration**: `core/agent.py` handles transitions between lobby and training; coordination is needed so lobby-driven peeks and training decisions do not conflict.

## Detailed Findings (by area)
### Area: Backend / Lobby decision flow
- **Why relevant:** Determines whether to enter races, infirmary, rest, or training; needs injection point for optional sneak peek.
- **Files & anchors (path:line_start–line_end):**
  - `core/actions/lobby.py:130–282` — `LobbyFlow.process_turn()` orchestrates race planning, infirmary, rest, and training navigation.
  - `core/actions/lobby.py:884–1050` — Planned race logging/guards and helpers that would need to respect new per-race skip flags.
  - `core/actions/lobby.py:1100–1140` — Navigation helpers (`_go_infirmary`, `_go_training_screen_from_lobby`) used when deciding next action.
- **Cross-links:** `core/agent.Agent._handle_training()` relies on lobby state after returning from training; any sneak peek must leave state consistent.

### Area: Backend / Training policy & scanning
- **Why relevant:** Already calculates SV (`sv_total`) for each tile; threshold comparison can reuse this data to decide whether to abort lobby actions.
- **Files & anchors:**
  - `core/actions/training_check.py:26–626` — `scan_training_screen()` and `compute_support_values()` generate SV metrics.
  - `core/actions/training_policy.py:189–906` — `decide_action_training()` uses SV to choose actions; can be extended with new threshold parameters.
  - `core/actions/training_policy.py:955–1036` — `check_training()` pulls runtime settings via `Settings.extract_runtime_preset()`.
- **Cross-links:** `core/agent.Agent._handle_training()` (`core/agent.py:573–688`) consumes decisions produced here.

### Area: Backend / Settings & config ingestion
- **Why relevant:** Central place to apply general/preset config; must persist toggle, threshold, and per-race metadata.
- **Files & anchors:**
  - `core/settings.py:44–298` — `Settings` class fields and `apply_config()` mapping for general/preset values.
  - `core/settings.py:247–298` — `Settings.extract_runtime_preset()` returns runtime-ready preset data (currently strings for `plan_races`).
  - `main.py:120–220` — (indirect) ensures `Settings.apply_config()` is invoked when config loads.
- **Cross-links:** Consumers include `LobbyFlow`, `RaceFlow`, and training modules; new settings must be accessible in all.

### Area: Frontend / General configuration UI
- **Why relevant:** Needs toggles/inputs for enabling sneak peek and configuring SV threshold.
- **Files & anchors:**
  - `web/src/models/types.ts:9–43` — `GeneralConfig` interface lacks fields for the new toggle and threshold.
  - `web/src/models/config.schema.ts:15–44` — `generalSchema` requires new keys and defaults.
  - `web/src/components/general/GeneralForm.tsx:48–235` — UI form where the toggle and numeric control should appear.
  - `web/src/store/configStore.ts:45–187` — Zustand actions handle general state; migration/default logic required for new fields.
- **Cross-links:** `prefs/config.sample.json` must mirror schema changes for onboarding defaults.

### Area: Frontend / Preset race scheduler
- **Why relevant:** Per-race overrides (skip if high SV) must live alongside existing race plan data.
- **Files & anchors:**
  - `web/src/models/types.ts:31–43` — `Preset` definition of `plannedRaces` as `Record<string, string>`; needs richer structure.
  - `web/src/models/config.schema.ts:47–133` — `presetSchema` must accept new race metadata while migrating existing string values.
  - `web/src/components/presets/RaceScheduler.tsx:16–77` — Race picker UI; must expose per-race toggle and handle new data shape.
  - `web/src/store/configStore.ts:53–183` — Preset mutators (`patchPreset`) and migrations for importing/exporting race schedules.
- **Cross-links:** Backend `Settings.extract_runtime_preset()` must parse updated race schedule entries.

### Area: Persistence & samples
- **Why relevant:** Example configs and stored JSON require updates to avoid breaking legacy imports.
- **Files & anchors:**
  - `prefs/config.sample.json:1–446` — Sample config currently lacks new fields and may require migration script.
  - `web/src/store/configStore.ts:164–182` — Import/export normalization logic will need to backfill new fields for old files.
- **Cross-links:** CLI or user-managed configs rely on consistent schema definitions; ensure migrations handle pure string race entries.

## 360° Around Target(s)
- **Target file(s):** `core/actions/lobby.py`, `core/actions/training_policy.py`, `core/actions/training_check.py`, `core/settings.py`, `web/src/models/config.schema.ts`, `web/src/store/configStore.ts`, `web/src/components/general/GeneralForm.tsx`, `web/src/components/presets/RaceScheduler.tsx`.
- **Dependency graph (depth 2):**
  - `core/agent.py` — orchestrates transitions between lobby and training decisions.
  - `core/actions/race.py` — invoked when lobby decides to race; must respect per-race skip flags.
  - `web/src/components/presets/PresetPanel.tsx` — wraps `RaceScheduler` and preset strategy toggles.
  - `server/main.py` / `server/utils.py` — load/save config JSON, ensuring schema compatibility.

## Open Questions / Ambiguities
- **Race metadata shape** — Should `plannedRaces` evolve into `Record<string, { name: string; allowSneakPeek?: boolean }>` or a parallel map to preserve backward compatibility? Need decision to minimize migration risk.
- **Threshold scope** — Does the SV threshold apply globally (general config) with optional preset overrides, or should presets be able to specify their own values? Clarify to avoid conflicting settings.
- **Action precedence** — When both infirmary and race are pending, should the sneak peek run before each action (potentially multiple training scans per turn) or only for races? Define order to prevent unnecessary scans.

## Suggested Next Step
- Draft `PLAN.md` describing schema changes, migration strategy, backend logic entry points, and testing (unit + manual) to validate lobby behavior with and without the new toggles.
