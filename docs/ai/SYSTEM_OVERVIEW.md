---

date: 2025-10-06T19:59:41-05:00
status: complete
repository: Umaplay
default_branch: main
current_branch: feature/0-1-3
git_commit: 858d873
tags: [architecture, overview]
context_budget_pct_target: 40
---

# System Overview
This repository provides an AI-driven automation stack for *Umamusume: Pretty Derby*. The runtime coordinates perception, decision logic, and input control; optional FastAPI services and a React UI expose configuration and monitoring. This document is maintained as a high-level system map so it remains useful even as implementation details evolve.

> If you’re just trying to run the bot end-to-end, see `README.md` / `README.gpu.md`.
> If you’re collecting data or training models, see `README.train.md`.

## Document Scope & Maintenance
- **Audience**: contributors who need to understand subsystems quickly without chasing implementation details.
- **Coverage**: focuses on durable architecture, directory boundaries, and extension points. Parameter-level details live in code comments or SOPs.
- **Maintenance tips**: when adding new modules, update the relevant section summary and the directory index. Keep examples generic so the document survives refactors.

## Architecture Snapshot
At a high level, the agent runs a repeatable perception→decision→action loop:

1. **Capture & detect** the game UI using YOLO anchors.
2. **Extract** structured state via OCR and lightweight analyzers.
3. **Score** candidate actions with the Support Value policy and contextual heuristics.
4. **Decide** among training, rest, recreation, racing, skills, or event handling.
5. **Act** through a controller that maps local detections to absolute screen coordinates.
6. **Repeat**, persisting debug artifacts when useful.

It supports both Steam on Windows and Android mirrored with scrcpy.

## Section Guide
- **Runtime Core Loop** — how `main.py` and `core/agent.py` coordinate actions.
- **Perception Stack** — detectors, OCR, and analyzers that build state.
- **Training Strategy** — decision helpers used on the training screen.
- **Automation Flows** — lobby, race, skills, events, and mini-games.
- **Controller Interfaces** — Steam and Android input adapters.
- **Configuration Surface** — settings, knobs, and runtime flags.
- **Data Collection & Model Training** — supporting scripts and datasets.
- **Frontend & Services** — FastAPI server, optional inference API, and React UI.
- **Appendices** — glossary, directory map, and source references.


## Runtime Core Loop
- **Entrypoint (`main.py`)** builds the runtime environment: load configuration, resolve the active controller, spin up the agent thread, and start the FastAPI server when enabled.
- **Agent orchestrator (`core/agent.py`)** owns the perception→decision→action loop. It routes every frame through screen classification, chooses the appropriate flow, and coordinates retries or recovery logic.
- **Action flows (`core/actions/`)** encapsulate lobby, training, race, skills, events, and mini-game behaviors. Each flow follows the same pattern: perceived the current screen, decide next steps, perform inputs, then re-capture to confirm state.
- **Controllers (`core/controllers/`)** abstract screenshot capture and input delivery for Steam, scrcpy, and other window providers. They normalize coordinate systems so decision code can stay device-agnostic.
- **Utilities & settings (`core/utils/`, `core/settings.py`)** provide cross-cutting helpers (geometry, waiting, logging) and map persisted configuration into runtime flags.
- **Key files**: `main.py`, `core/agent.py`, `core/actions/lobby.py`, `core/actions/training_check.py`, `core/actions/training_policy.py`, `core/actions/race.py`, `core/actions/skills.py`, `core/actions/events.py`, `core/actions/claw.py`, `core/controllers/steam.py`, `core/controllers/android.py`, `core/utils/logger.py`, `core/utils/waiter.py`, `core/settings.py`.

### Control Flow Overview
1. Load settings and instantiate the selected `IController`.
2. Spin up the agent loop (threaded hotkey toggle by default).
3. For each cycle, capture the screen, build structured state, pick a flow, and execute its scripted steps.
4. Persist debug artifacts and metrics when enabled, then sleep briefly before the next capture.

This design keeps the main loop stable even as individual flows or perception modules evolve.

---
## Data & Model Assets
- **Datasets (`datasets/`)**: Stores curated game metadata (skills, races, events) and YOLO training assets. Loader utilities live in `server/utils.py`.
- **Models (`models/`)**: Bundles YOLO weights and classifiers resolved by `core/settings.py`.
- **Prefs (`prefs/`)**: Holds persisted configuration, with samples (`prefs/config.sample.json`, `prefs/preset.sample.json`) used by the web UI.
- **Debug (`debug/`)**: Receives screenshots, overlays, and logs during runtime.
- **Key files**: `datasets/in_game/skills.json`, `datasets/in_game/races.json`, `datasets/in_game/events.json`, `datasets/uma/`, `models/uma.pt`, `models/active_button_clf.joblib`, `collect_training_data.py`, `prepare_uma_yolo_dataset.py`.

Supporting scripts extend data in-place so runtime code can rely on stable directory contracts.

---

## Services & Frontend
- **FastAPI backend (`server/`)**: Handles configuration CRUD, dataset APIs, admin update endpoints, and static file serving. See `server/main.py`, helpers in `server/utils.py`, and updater logic in `server/updater.py`.
- **Inference microservice (`server/main_inference.py`)**: Optional FastAPI app for `/ocr` and `/yolo` offload.
- **React web UI (`web/`)**: Vite-built SPA using Zustand and Zod. Entry in `web/src/main.tsx`; API client in `web/src/services/api.ts`; state store in `web/src/store/configStore.ts`; schemas in `web/src/models/config.schema.ts`.
- **Launch scripts**: `run_uma.bat`, `run_inference_server.bat` wrap common start commands.

Backend and frontend share typed contracts through the settings schema, keeping configuration consistent.

---

## Operational Notes
- **Execution modes**: Common runs include `python main.py`, `uvicorn server.main_inference:app`, and client-only mode toggled via `Settings.USE_EXTERNAL_PROCESSOR` in `core/settings.py`.
- **Logging & observability**: `core/utils/logger.py` configures console/file output; tests like `tests/test_turns.py` provide sanity checks; runtime artifacts accumulate under `debug/`.
- **Performance levers**: Adjust YOLO image size, confidence thresholds, and polling delays in `core/settings.py`. Offloading perception via `run_inference_server.bat` shifts resource usage to remote hosts.
- **Known sensitivities**: Window-title mapping in `core/settings.py.resolve_window_title()`, OCR variance handled by `core/perception/ocr.py`, and frontend bundle size under `web/dist/`.

---

## Maintenance Tips
- **Summaries first**: When adding subsystems, note purpose, key files, and extension hooks here; link to SOPs or docstrings for detail.
- **Keep paths fresh**: Update directory/file bullet lists if assets move or new entrypoints appear.
- **Cross-link wisely**: Reference SOPs (`docs/ai/SOPs/`) or README sections instead of duplicating procedures.

---

## Related References
- `docs/README.md`, `docs/README.gpu.md`, and `docs/README.virtual_machine.md` cover installation, GPU setup, and VM usage specifics.
- `docs/ai/SOPs/` holds task-specific procedures (e.g., syncing frontend and backend configuration changes).
- `internal.md` may contain transient internal notes; keep sensitive content out of this overview.



# Web UI Overview

The `web/` directory contains a React/Vite single-page app that edits runtime configuration. It mirrors the backend schema, keeps optimistic state, and persists to `prefs/config.json` via FastAPI routes.

- **Entry point**: `web/src/main.tsx`
- **API client**: `web/src/services/api.ts`
- **State store**: `web/src/store/configStore.ts`
- **Schemas**: `web/src/models/config.schema.ts`
- **Primary layout**: `web/src/pages/Home.tsx`
- **Forms & flows**: General settings live in `web/src/components/general/GeneralForm.tsx`; presets tooling (tabs, skill picker, race scheduler) sits under `web/src/components/presets/`; shared chrome like `SaveLoadBar` and `FieldRow` lives in `web/src/components/common/`.

## Configuration wiring
- **Local state**: `configStore.ts` hydrates defaults from `config.schema.ts`, syncs changes to Local Storage, and exposes helpers like `setGeneral()` and `patchPreset()`.
- **Backend sync**: `SaveLoadBar.tsx` posts the active config via `api.ts` → FastAPI’s `/config` route (`server/main.py`), which writes `prefs/config.json` for the Python runtime.
- **Runtime consumption**: `core/settings.py` loads the saved configuration when `main.py` boots or the agent starts, keeping frontend edits aligned with controller, perception, and policy knobs.
- **Datasets**: React Query hooks in `api.ts` pull `skills.json` / `races.json` from `/api/skills` and `/api/races`, using the same files referenced by backend flows.
