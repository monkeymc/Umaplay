---
date: 2025-10-12T21:17:00-05:00
status: complete
repository: Umaplay
default_branch: main
current_branch: feature/0.2.0
git_commit: 2ffbf59
tags: [architecture, overview]
context_budget_pct_target: 40
---

# System Overview
`Umaplay` is an AI-driven automation stack for *Umamusume: Pretty Derby*. The system combines a perception→decision→action loop, task-focused automation flows, and optional services to expose configuration, remote perception, and monitoring. This document captures durable architecture so contributors can orient quickly even as implementation details iterate.

> If you’re just trying to run the bot end-to-end, see `README.md` / `README.gpu.md`.
> If you’re collecting data or training models, see `README.train.md`.

## Document Scope & Maintenance
- **Audience**: contributors updating automation logic, perception, or services.
- **Coverage**: focuses on durable architecture, directory boundaries, and extension points. Parameter-level details stay in code comments, SOPs, or READMEs.
- **Maintenance tips**: when adding modules, update the relevant section summary, directory map, and cross-cutting notes. Prefer stable descriptions over implementation trivia.

## Architecture Snapshot
1. **Capture** the active game window via a controller abstraction (Steam, Scrcpy, BlueStacks fallback).
2. **Perceive** the frame with YOLO detectors (`core/perception/yolo/`) and OCR pipelines (`core/perception/ocr/`).
3. **Assemble state** using analyzers (`core/perception/analyzers/`) and extractors to derive stats, events, and UI context.
4. **Decide** the next action inside `core/agent.py` or `core/agent_nav.py`, coordinating specialized flows per screen.
5. **Act** through controller clicks and gestures, using `core/utils/waiter.py` to synchronize on UI feedback.
6. **Expose services** for configuration, updates, and optional remote inference through FastAPI apps under `server/`.

The runtime supports Steam on Windows and Android mirrored via scrcpy, with experimental BlueStacks support.

## Directory Map
```
.
├── core/
│   ├── actions/
│   ├── controllers/
│   ├── perception/
│   ├── utils/
│   └── settings.py
├── server/
│   ├── main.py
│   ├── main_inference.py
│   └── utils.py
├── web/
│   ├── src/
│   ├── dist/
│   └── package.json
├── datasets/
│   ├── in_game/
│   └── uma_nav/
├── models/
├── prefs/
├── docs/ai/SOPs/
└── tests/
```

---

## SOPs
- `docs/ai/SOPs/sop-config-back-front.md`
- `docs/ai/SOPs/waiter-usage-and-integration.md` (Important)

## Runtime Topology (diagram as text)
```
[Controllers (Steam/Scrcpy/BlueStacks)]
          |
          v
 [Perception Engines]
 (YOLO detectors, OCR) --optional--> [Remote Inference API]
          |
          v
    [Agent Loop]
 (core/agent.py, flows)
          |
          v
[FastAPI Config Server] <---> [React Web UI]
          |
          v
       [Prefs/Config]
```

## Runtime Core Loop
- **Entrypoint (`main.py`)** loads configuration (`server/utils.py`), applies runtime settings, builds controllers/OCR/YOLO engines, and starts the bot loop plus the FastAPI server when enabled.
- **Agent loop (`core/agent.py`)** coordinates perception→decision→action for training careers, integrating race scheduling, skill buys, events, and the claw mini-game.
- **AgentNav (`core/agent_nav.py`)** provides hotkey-triggered navigation flows for Team Trials and Daily Races, reusing shared perception but with dedicated YOLO weights (`Settings.YOLO_WEIGHTS_NAV`).
- **Action flows (`core/actions/`)** modularize behaviors: lobby management, training policy scoring, races, skills, events, Team Trials (`team_trials.py`), and Daily Races (`daily_race.py`).
- **Controllers (`core/controllers/`)** abstract capture/input for Steam, Scrcpy, and optional BlueStacks; `core/controllers/base.py` defines the contract.
- **Utilities (`core/utils/`)** cover logging (`logger.py`), waiters (`waiter.py`), abort handling, navigation helpers, event catalogs, and race indexing for scheduling.
- **Settings (`core/settings.py`)** maps persisted configuration and environment flags into runtime constants, including remote inference toggles, YOLO thresholds, and nav weights.

### Control Flow Overview
1. Load the latest config using `Settings.apply_config()` and configure logging.
2. Instantiate controller, OCR, and YOLO engines (local or remote) based on selected mode.
3. Spin up agent threads (`BotState`, `NavState`) and monitor hotkeys/hard-stop signals.
4. In each iteration: capture frame, classify screen, delegate to the matching flow, and confirm state transitions via `Waiter`.
5. Persist debug artifacts, race plans, and skill purchase state for reuse.

This design allows the core loop to evolve independently of perception implementations or UI flows.

## Perception & Automation Stack
- **Vision**: `core/perception/yolo/` wraps local (`yolo_local.py`) and remote (`yolo_remote.py`) detectors; `core/perception/ocr/` exposes PaddleOCR engines (`ocr_local.py`, `ocr_remote.py`).
- **Analyzers**: `core/perception/analyzers/` classifies screens, detects UI states, and supports navigation heuristics.
- **Extractors**: `core/perception/extractors/` pulls structured stats, goals, and energy values used by flows.
- **Button activation**: `core/perception/is_button_active.py` provides classifier logic for interactable buttons.
- **Waiter synchronization**: `core/utils/waiter.py` coordinates detection loops and click retries across flows.
- **Automation flows**: `core/actions/` modules cover training (`training_policy.py`, `training_check.py`), lobby orchestration (`lobby.py`), race execution (`race.py`, `daily_race.py`), Team Trials automation (`team_trials.py`), claw game (`claw.py`), event handling (`events.py`), and skill purchasing (`skills.py`).

## Services / Apps
### Python Runtime
- **Purpose**: Main automation loop for training runs.
- **Entrypoints**: `main.py`, `core/agent.py`.
- **Public interfaces**: Hotkeys (F2 toggle), console logging.
- **Key internal dependencies**: `core/actions/`, `core/perception/`, `core/utils/waiter.py`.
- **Data/config locations**: `prefs/config.json`, `datasets/in_game/`.
- **Observability**: `core/utils/logger.py`, debug artifacts under `debug/`.
- **Testing**: `tests/` (e.g., `tests/test_turns.py`).

### FastAPI Configuration Server
- **Purpose**: Serve web UI assets, manage configs, expose dataset APIs, and orchestrate updates.
- **Entrypoints**: `server/main.py`.
- **Public interfaces**: `/config`, `/api/skills`, `/api/races`, `/api/events`, `/admin/*` endpoints.
- **Key internal dependencies**: `server/utils.py`, `server/updater.py`, `core/version.py`.
- **External dependencies**: FastAPI, Uvicorn.
- **Data/config locations**: `prefs/`, `web/dist/` for static assets.
- **Observability**: Console logs, HTTP responses with error detail.

### Remote Inference Service
- **Purpose**: Offload OCR and YOLO detection to a stronger host.
- **Entrypoints**: `server/main_inference.py`.
- **Public interfaces**: `/ocr`, `/yolo`, `/health`.
- **Key internal dependencies**: `core/perception/ocr/ocr_local.py`, `core/perception/yolo/yolo_local.py`, Torch.
- **Data/config locations**: `models/`, `datasets/uma_nav/` weights referenced by `Settings.YOLO_WEIGHTS_NAV`.
- **Observability**: Response metadata includes checksums, model identifiers.

### AgentNav One-Shot Flows
- **Purpose**: Automate Team Trials and Daily Races outside the main career loop.
- **Entrypoints**: `core/agent_nav.py` (triggered via hotkeys F7/F8).
- **Public interfaces**: Hotkey toggles.
- **Key internal dependencies**: `core/actions/team_trials.py`, `core/actions/daily_race.py`, `core/utils/nav.py`.
- **Data/config locations**: Nav-specific YOLO weights (`Settings.YOLO_WEIGHTS_NAV`).
- **Observability**: Logs under `[AgentNav]` namespace.

### React Web UI
- **Purpose**: Configure runtime presets, manage events, trigger updates.
- **Entrypoints**: `web/src/main.tsx`, `web/src/App.tsx`.
- **Public interfaces**: Served at `/` via FastAPI.
- **Key internal dependencies**: `web/src/store/configStore.ts`, `web/src/models/config.schema.ts`, `web/src/services/api.ts`.
- **External dependencies**: React, Vite, MUI, Zustand, React Query.
- **Data/config locations**: Persists to `prefs/config.json` via API.
- **Observability**: Browser console logs, React Query devtools (dev builds).

## Operational Notes
- **Execution modes**: `python main.py` starts the bot and the config server; `run_inference_server.bat` launches remote perception; `uvicorn server.main_inference:app --host 0.0.0.0 --port 8001` runs standalone inference.
- **Hotkeys & toggles**: `BotState` binds F2 for start/stop; `AgentNav` exposes one-shot flows for Team Trials (F7) and Daily Races (F8) with recovery handling in `core/actions/team_trials.py` and `core/actions/daily_race.py`.
- **Logging & observability**: `core/utils/logger.py` sets structured logs; `debug/` collects screenshots and overlays; cleanup logic in `main.py.cleanup_debug_training_if_needed()` prunes large training captures.
- **Performance levers**: `core/settings.py` exposes YOLO image size, confidence, OCR mode (fast/server), and remote processor URLs. Nav-specific weights configured via `Settings.YOLO_WEIGHTS_NAV`.
- **Reliability guards**: `core/utils/abort.py` enforces safe shutdown; `core/utils/waiter.py` throttles retries; `core/actions/race.ConsecutiveRaceRefused` handles stale states.

## Data & Persistence
- **Datasets (`datasets/in_game/`)** provide JSON for skills, races, and events consumed by backend APIs and lobby planning.
- **YOLO datasets (`datasets/uma/`, `datasets/uma_nav/`, `datasets/coco8/`)** support ongoing model training.
- **Models (`models/`)** store YOLO weights (`uma.pt`) and classifiers referenced by `core/settings.py` and remote inference.
- **Prefs (`prefs/`)** persist runtime configuration (`config.json`) plus samples for onboarding.
- **Debug artifacts (`debug/`)** capture screenshots and overlays for tuning; cleanup automation runs when exceeding thresholds.
- **Training scripts**: `collect_training_data.py`, `collect_data_training.py`, and `prepare_uma_yolo_dataset.py` manage dataset curation.

## External Integrations
- **PaddleOCR** and **PaddlePaddle** power local OCR engines; optional remote service still relies on these models installed on the host.
- **Ultralytics YOLO** powers object detection for both local and remote pipelines.
- **FastAPI + Uvicorn** serve configuration and inference APIs.
- **Torch** backs inference acceleration on GPU hosts.

## Cross-Cutting Concerns
- **Configuration**: Centralized in `core/settings.py`, persisted in `prefs/config.json`, synchronized through `web/src/store/configStore.ts` and Zod schemas.
- **Authentication**: Services expect local access; admin endpoints restrict to loopback.
- **Logging**: Configured by `setup_uma_logging()`, enriched by flow-specific debug lines; remote inference endpoints log checksums for traceability.
- **Metrics/Telemetry**: No dedicated metrics stack; rely on logs and debug artifacts.
- **Feature flags**: Settings such as `USE_EXTERNAL_PROCESSOR`, `DEBUG`, and nav weights act as toggles.
- **Testing**: `tests/` contains focused regression tests (e.g., `tests/test_turns.py`) validating decision logic.

## Frontend Architecture
- **Routing**: Single-page app anchored at `/` with internal layout and tabs for General vs Preset settings (`web/src/pages/Home.tsx`).
- **State management**: Zustand store in `web/src/store/configStore.ts` manages config, exposes actions (`setGeneral`, `patchPreset`, `importJson`).
- **Schema validation**: `web/src/models/config.schema.ts` ensures inbound configs are normalized and defaulted; migrations keep legacy fields compatible.
- **Components**: Modular folders (`web/src/components/general/`, `web/src/components/presets/`, `web/src/components/events/`) encapsulate forms, race planners, and event editors.
- **Styling**: MUI theme toggles via `uiTheme` state; `web/src/App.tsx` consumes design tokens.
- **Build**: Vite config in `web/vite.config.ts`; production output in `web/dist/` served by FastAPI.

## Environments & Deployment
- **Local development**: Install Python deps via `requirements.txt`, Node deps via `web/package.json`. Run `python main.py` to launch runtime and UI.
- **Client-only mode**: Machines with limited resources install `requirements_client_only.txt`, enable `USE_EXTERNAL_PROCESSOR`, and point to a remote inference host.
- **GPU setup**: Follow `docs/README.gpu.md` for CUDA-enabled Paddle/Torch installs.
- **Virtual machines**: `docs/README.virtual_machine.md` guides resource tuning for VM deployments.
- **Update flow**: Web UI exposes pull/force update buttons hitting `/admin/update` and `/admin/force_update` with safeguards.

## Performance & Reliability
- **Hot paths**: YOLO detection and OCR loops dominate runtime; leverage remote inference to offload heavy computation.
- **Caching**: YOLO engines reuse loaded weights; config store hydrates defaults from schema to avoid undefined fields.
- **Recovery**: `AgentNav` includes stale-state detection for shops/results; `core/actions/race` handles consecutive race refusals; unknown screens trigger safe clicks with patience backoff.
- **Cleanup**: Training debug folders automatically compressed/relocated when exceeding 250 MB.

## Risks & Hotspots
- **UI drift**: Game UI updates require new YOLO labels and adjusted analyzers (`core/perception/analyzers/`).
- **OCR accuracy**: Paddle OCR may misread small fonts; consider enhancing dataset or leveraging remote service.
- **Race scheduling**: Depends on JSON datasets; outdated entries can skip events or misclassify races.
- **Config migrations**: Ensure `configStore.ts` migrations stay in sync with `core/settings.py` defaults.
- **Remote inference**: Network latency or dropped connections can stall detection loops; monitor logs for retries.

## Related Docs
- `README.md`, `README.gpu.md`, `README.train.md`, `docs/README.virtual_machine.md`
- `web/README.md` for frontend-focused details
- `internal.md` for transient notes (sanitize before sharing)

## Open Questions
- Pending nav expansions beyond Team Trials and Daily Races.
- Potential metrics/telemetry integration for long-running sessions.
- Packaging strategy for stable Windows executables.

## Source References
- `main.py`, `core/agent.py`, `core/agent_nav.py`
- `core/actions/`, `core/perception/`, `core/controllers/`, `core/utils/`
- `core/settings.py`, `core/version.py`
- `server/main.py`, `server/main_inference.py`, `server/utils.py`, `server/updater.py`
- `web/src/`, `web/vite.config.ts`, `web/package.json`
- `datasets/`, `models/`, `prefs/`
- `docs/ai/SOPs/`
- `tests/`
