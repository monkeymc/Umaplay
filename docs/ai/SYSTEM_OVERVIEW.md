---
date: 2025-10-12T21:17:00-05:00
repository: Umaplay
default_branch: main
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
- `docs/ai/SOPs/sop-config-back-front.md` (Reference of web folder and web UI)
- `docs/ai/SOPs/waiter-usage-and-integration.md` (Important)
- `docs/ai/SOPs/towards-custom-training-policy-graph.md` (Notes on evolving training-policy automation graph)
- `docs/ai/SOPs/adding-new-scenario.md` (How to onboard a new training scenario end-to-end)

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
- **Entrypoint (`main.py`)** loads configuration (`server/utils.py`), applies runtime settings, builds controllers/OCR/YOLO engines, and starts the bot loop plus the FastAPI server when enabled. The hotkey bootstrap respects the persisted `scenarioConfirmed` flag so TechEye prompting is skipped when the user selected a scenario from the Web UI.
- **Agent loop (`core/agent.py`)** coordinates perception→decision→action for training careers, integrating race scheduling, skill buys, events, and the claw mini-game. Deferred post-hint skill rechecks now persist intent (`_pending_hint_recheck`) until the loop returns to a stable screen (Lobby/Raceday) before reopening the Skills view and retrying purchases with guardrails against forced navigation. Event handling (
  `core/actions/events.EventFlow`) fuses YOLO+OCR hints with template matching scores that blend multi-scale TM, perceptual hash, and HSV hair histograms (with gray-world balancing/masks) so lookalike trainees (e.g., seasonal alts) stay separable. When presets specify a trainee in
  `config.json`, the retriever promotes that card even if it scores slightly lower and, if that name is missing, falls back to the "trainee/general/None/None" catalog entry to avoid dead ends when seasonal data is absent. The same flow remembers two-phase prompts (e.g., Acupuncturist) and auto-confirms the follow-up dialog when only the accept/reconsider buttons are present.
- **Scenario routing**: `core/scenarios/registry.py` maps scenario keys (URA, Unity Cup/Aoharu aliases) to policy callables so `AgentScenario` instantiations fetch the correct training strategy without duplicating logic. This registry is populated during agent bootstrap.
- **AgentNav (`core/agent_nav.py`)** provides hotkey-triggered navigation flows for Team Trials and Daily Races, reusing shared perception but with dedicated YOLO weights (`Settings.YOLO_WEIGHTS_NAV`).
- **Action flows (`core/actions/`)** modularize behaviors: lobby management, training policy scoring, races, skills, events, Team Trials (`team_trials.py`), and Daily Races (`daily_race.py`). Skill purchasing respects per-preset `skillPtsCheck` thresholds, while event handling consults per-entity energy overflow toggles plus ranked reward priorities (skill pts → stats → hints by default) before rotating choices. `core/utils/event_processor.UserPrefs` now persists reward priority maps per support/scenario/trainee, and `EventFlow` falls back to the global order only when entity-specific lists are absent. When an event would overcap energy, `EventFlow.process_event_screen()` scores each option (via `max_positive_energy()` and `extract_reward_categories()`), builds the rotation order around the player-preferred pick, and only reorders if the chosen option violates the energy cap. Safe alternatives are then filtered by reward priority, preferring matches that satisfy the entity-specific ranking before defaulting to the first non-overflowing candidate, with adjustments surfaced through debug telemetry.
- **Controllers (`core/controllers/`)** abstract capture/input for Steam, Scrcpy, optional BlueStacks, and ADB-backed Android sessions. In addition to `SteamController`, `ScrcpyController`, and `BlueStacksController`, the new `core/controllers/adb.py` issues `adb` taps/swipes/screenshots so BlueStacks (or any reachable Android device) can run without hijacking the local mouse. `core/controllers/base.py` defines the contract every controller implements.
- **Utilities (`core/utils/`)** cover logging (`logger.py`), waiters (`waiter.py`), abort handling, navigation helpers, skill memory persistence (`skill_memory.py`), preset toast rendering (`preset_overlay.py`), event catalogs, and race indexing for scheduling. `SkillMemoryManager` maintains grade-specific skill purchases (e.g., distinguishing `○` vs. `◎` variants), shares a single instance with `SkillsFlow`, and auto-resets on career completion so each run starts from a clean slate. `event_processor.py` normalizes per-entity reward priorities coming from config, builds lookup tables consumed downstream, and fuses template matching + pHash + histogram scores when comparing trainee portraits; when `Settings.USE_EXTERNAL_PROCESSOR` is enabled the portrait matching offloads to the remote `/template-match` service so thin clients avoid OpenCV costs while retaining the same fused score.
- **Settings (`core/settings.py`)** maps persisted configuration and environment flags into runtime constants, including remote inference toggles, YOLO thresholds, nav weights, controller mode selection, and the active preset’s `skillPtsCheck` (fallback to legacy general config) before handing it to `Player`. The general config now exposes `mode`, `useAdb`, and `adbDevice` (backed by env vars `MODE`, `USE_ADB`, `ADB_DEVICE`) so BlueStacks sessions can be switched to ADB control when desired. `RUNTIME_SKILL_MEMORY_PATH` defaults to `prefs/runtime_skill_memory.json` but can be overridden via env.

### Control Flow Overview
1. Load the latest config using `Settings.apply_config()` and configure logging.
2. Instantiate controller, OCR, and YOLO engines (local or remote) based on selected mode.
3. Spin up agent threads (`BotState`, `NavState`) and monitor hotkeys/hard-stop signals.
4. In each iteration: capture frame, classify screen, delegate to the matching flow, and confirm state transitions via `Waiter`.
5. Persist debug artifacts, race plans, and skill purchase state for reuse.

This design allows the core loop to evolve independently of perception implementations or UI flows.

## Perception & Automation Stack
- **Perception**: `core/perception/yolo/` wraps local (`yolo_local.py`) and remote (`yolo_remote.py`) detectors; `core/perception/ocr/` exposes PaddleOCR engines (`ocr_local.py`, `ocr_remote.py`).
- **Classifiers**: `core/perception/classifiers/` hosts lightweight HTTP clients (e.g., `spirit_remote.py`) that mirror local inference APIs when offloading to the remote server.
- **Analyzers**: `core/perception/analyzers/` classifies screens, detects UI states, and supports navigation heuristics.
- **Hint detection**: `core/perception/analyzers/hint.py` fuses HSV ROI checks with anchor-aware hint assignment so YOLO detections favor the card's top-right quadrant and penalize support_bar overlaps, preventing jump misassociation.
- **Template matching**: `core/perception/analyzers/matching/` prepares histogram/hash caches, performs gray-world balancing, and extracts HSV hair-region fingerprints before combining them with multi-scale TM + perceptual hash scores. OpenCV usage is feature-gated so thin clients can route calls to the remote `/template-match` endpoint (`server/main_inference.py`) when local `cv2` is unavailable.
- **Extractors**: `core/perception/extractors/` pulls structured stats, goals, and energy values used by flows.
- **Button activation**: `core/perception/is_button_active.py` provides classifier logic for interactable buttons.
- **Waiter synchronization**: `core/utils/waiter.py` coordinates detection loops and click retries across flows.
- **Automation flows**: `core/actions/` modules cover training (`training_policy.py`, `training_check.py`), lobby orchestration (`lobby.py`), race execution (`race.py`, `daily_race.py`), Team Trials automation (`team_trials.py`), claw game (`claw.py`), event handling (`events.py`), and skill purchasing (`skills.py`).
- **Agent-scoped debug captures**: Low-confidence YOLO/OCR snapshots are saved under `debug/<agent>/<tag>/raw`. When introducing a new agent, supply its identifier through `PollConfig.agent`/`Waiter` and ensure remote YOLO requests include the same `agent` so ` LocalYOLOEngine`/`RemoteYOLOEngine` place samples in the correct folder.
- When classifier active/inactive button checks are required use `ActiveButtonClassifier.load(Settings.IS_BUTTON_ACTIVE_CLF_PATH)`. Check if button is active or not, in the project we are using this classifier a lot

### Hint Priority System (2025 Q4)
- **Purpose**: Let presets define per-card hint multipliers or blacklist hints, reducing noise from low-value cards.
- **UI**: `web/src/components/events/EventSetupSection.tsx` surfaces a `Custom hint` badge and opens `SupportPriorityDialog.tsx` where users toggle *Hint enabled/disabled*, adjust blue/green vs. orange/max multipliers, or ignore hints entirely.
- **Config plumbing**: The preset schema extends `SelectedSupport.priority`; `Settings.apply_config()` stores `SUPPORT_CARD_PRIORITIES` plus derived flags (`SUPPORT_PRIORITIES_HAVE_CUSTOMIZATION`, `SUPPORT_CUSTOM_PRIORITY_KEYS`).
- **Classification**: `core/actions/training_check.py` initializes a cached `SupportCardMatcher` (`core/utils/support_matching.py`, `core/perception/analyzers/matching/support_card_matcher.py`) only when customized hints exist, then assigns deck templates per tile via a single-pass matcher to avoid duplicate matches.
- **Scoring**: `compute_support_values()` applies the highest hint bonus per tile, honoring card-specific multipliers, blacklist, and the global `HINT_IS_IMPORTANT` toggle; `training_policy.py` consumes `sv_by_type` to decide whether hint tiles beat risk caps. Supports configured with `recheckAfterHint` only retain that flag until all required skills have been bought—once satisfied, the agent clears the flag and the Skills recheck target set (`Settings.RECHECK_AFTER_HINT_SKILLS`) the next time memory refreshes.

## Services / Apps
### Python Runtime
- **Purpose**: Main automation loop for training runs.
- **Entrypoints**: `main.py`, `core/agent.py`.
- **Public interfaces**: Hotkeys (F2 toggle), console logging.
- **Key internal dependencies**: `core/actions/`, `core/perception/`, `core/utils/waiter.py`.
- **Data/config locations**: `prefs/config.json`, `datasets/in_game/`.
- **Observability**: `core/utils/logger.py`, debug artifacts under `debug/`.
- **Testing**: `tests/` (e.g., `tests/test_turns.py`).
- **Scenario implementations**: `core/actions/ura/` encapsulates URA campaign flows (lobby, training check, policy), while `core/actions/unity_cup/` contains Unity Cup-specific agent logic (seasonal lobby flow, training adaptations, showdown handling). The shared agent scaffolding delegates to these modules based on `Settings.ACTIVE_SCENARIO` via the registry noted above.

### FastAPI Configuration Server
- **Purpose**: Serve web UI assets, manage configs, expose dataset APIs, and orchestrate updates.
- **Entrypoints**: `server/main.py`.
- **Public interfaces**: `/config`, `/api/skills`, `/api/races`, `/api/events`, `/admin/*` endpoints.
- **Key internal dependencies**: `server/utils.py`, `server/updater.py`, `core/version.py`.
- **External dependencies**: FastAPI, Uvicorn.
- **Data/config locations**: `prefs/`, `web/dist/` for static assets.
- **Observability**: Console logs, HTTP responses with error detail. When handling template matching requests, the service caches prepared templates under `web/public/` (e.g., trainee portraits) so remote hint/event lookups stay fast for thin clients.

### Remote Inference Service
- **Purpose**: Offload OCR, YOLO detection, and OpenCV-heavy template matching to a stronger host.
- **Entrypoints**: `server/main_inference.py`.
- **Public interfaces**: `/ocr`, `/yolo`, `/template-match`, `/classify/spirit`, `/health`.
- **Key internal dependencies**: `core/perception/ocr/ocr_local.py`, `core/perception/yolo/yolo_local.py`, template matcher helpers in `core/perception/analyzers/matching/`, Torch.
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
- **Hotkeys & toggles**: `BotState` binds F2 for start/stop (and shows the active preset overlay via `core/utils/preset_overlay.py` when enabled); `AgentNav` exposes one-shot flows for Team Trials (F7), Daily Races (F8), and Roulette (F9). The overlay now ships with a high-contrast border/emerald background so the toast remains visible even on busy desktops. Roulette relies on `core/actions/roulette.py` to spin Prize Derby wheels, respects `NavState.stop()` for early exit, and reuses nav YOLO weights in `core/agent_nav.py`.
- **Logging & observability**: `core/utils/logger.py` sets structured logs; `debug/` collects screenshots and overlays; cleanup logic in `main.py.cleanup_debug_training_if_needed()` prunes large training captures.
- **Performance levers**: `core/settings.py` exposes YOLO image size, confidence, OCR mode (fast/server), remote processor URLs, and preset overlay toggles/duration (`SHOW_PRESET_OVERLAY`, `PRESET_OVERLAY_DURATION`). Nav-specific weights configured via `Settings.YOLO_WEIGHTS_NAV`.
- **Reliability guards**: `core/utils/abort.py` enforces safe shutdown; `core/utils/waiter.py` throttles retries; `core/actions/race.ConsecutiveRaceRefused` handles stale states.

## Data & Persistence
- **Datasets (`datasets/in_game/`)** provide JSON for skills, races, and events consumed by backend APIs and lobby planning; trainee entries now retain seasonal suffixes (e.g., `(Summer)`) while normalizing legacy `(Original)` noise, and each row carries a stable `id` (`{name}_{attribute}_{rarity}`) for downstream joins.
- **Event Scraper System**:
  - Main scraper: `datasets/scrape_events.py` handles Gametora data parsing (HTML/JSON modes)
  - Shared events: `datasets/in_game/shared_events.json` stores common trainee events
  - Features: Output normalization, stat-based overrides (Dance Lesson, New Year's Resolutions), single-outcome event filtering
  - Web UI: Toggle in `web/src/components/events/EventSetupSection.tsx` controls display
- **YOLO datasets** (`datasets/uma/`, `datasets/uma_nav/`, `datasets/coco8/`) support ongoing model training.
- **Models (`models/`)** store YOLO weights (`uma.pt`) and classifiers referenced by `core/settings.py` and remote inference.
- **Prefs (`prefs/`)** persist runtime configuration (`config.json`) plus samples for onboarding; runtime skill memory defaults to `prefs/runtime_skill_memory.json`.
- **Skill memory (`core/utils/skill_memory.py`)** provides `SkillMemoryManager` to track skill sightings/purchases across runs, enforcing staleness rules before persisting the JSON payload. Runtime saves immediately reload to keep in-memory state aligned with disk, and the manager resets on end-of-career so subsequent runs do not inherit prior skill buys.
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
- **State management**: Zustand store in `web/src/store/configStore.ts` manages config, exposes actions (`setGeneral`, `patchPreset`, `importJson`). Per-preset `skillPtsCheck` thresholds are mirrored into legacy general config on save/load for backwards compatibility. The general scenario toggle now raises `scenarioConfirmed` so hotkey runs skip redundant prompts, and the store blocks overwriting previously saved presets when a transient empty payload is produced. `useEventsSetupStore` tracks per-support/scenario/trainee energy overflow switches and reward priority stacks, syncing them with per-entity config payloads while maintaining a global fallback order.
- **Scenario-aware UI**: The Bot Strategy/Policy section follows a registry pattern in `web/src/components/presets/strategy/`, mapping scenario keys to dedicated components (`UraStrategy.tsx`, `UnityCupStrategy.tsx`). Adding new scenarios requires creating a component implementing `StrategyComponentProps` and registering it in the loader—no conditional logic in parent components.
- **Schema validation**: `web/src/models/config.schema.ts` ensures inbound configs are normalized and defaulted; migrations keep legacy fields compatible.
- **Components**: Modular folders (`web/src/components/general/`, `web/src/components/presets/`, `web/src/components/events/`) encapsulate forms, race planners, and event editors. Strategy components under `presets/strategy/` use a registry pattern for scenario-specific customization without parent sprawl.
- **Skills picker**: `web/src/components/presets/SkillsPicker.tsx` now provides a dialog with search, rarity/category filters, pagination, and inline toggles for adding/removing skills, surfacing rarity-aware styling (e.g., gradient badges for unique skills) synced with preset `skillsToBuy` arrays.
- **Daily Races tab**: `web/src/pages/Home.tsx` keeps both tabs mounted for instant switching; `web/src/components/nav/DailyRacePrefs.tsx` writes to `useNavPrefsStore`, which persists `/nav` preferences (alarm clock, star pieces, parfait) via FastAPI without re-fetching when users toggle between tabs.
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
