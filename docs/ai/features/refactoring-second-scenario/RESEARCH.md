---
date: 2025-11-06T11:15:00-05:00
topic: Refactoring for second scenario (Aoharu)
status: research_complete
---

# RESEARCH — Refactoring for second scenario (Aoharu)

## Research Question
Prepare the codebase to support multiple career scenarios (URA + Aoharu) without breaking existing URA behavior, with a clear UX to pick a scenario (e.g., F2 popup) and clean separations so scenario-specific policies plug into the capture → perceive → decide → act loop.

## Summary (≤ 10 bullets)
- Hotkey F2 toggles the main bot in `main.py`; a Tkinter chooser now intercepts the start flow and respects persisted `scenarioConfirmed` state before calling `BotState.start()`.
- Runtime constructs Player with a single Waiter tagged `Settings.AGENT_NAME_URA`; introduce per-scenario agent tags and YOLO weights selection.
- URA-specific logic exists inside `training_policy.py` (e.g., “URA Finale branch”); create a scenario policy interface and move URA policy under `/core/scenarios/ura/` with an Aoharu stub.
- Web UI config already carries a `preset.event_setup.scenario` object; `general.activeScenario` and `scenarioConfirmed` now exist for runtime clarity with migrations guarding legacy configs.
- Persist per-scenario skill memory to avoid cross-scenario contamination; runtime now suffixes `RUNTIME_SKILL_MEMORY_PATH` and stores scenario metadata.
- Keep RaceFlow/Events largely scenario-agnostic; later, add an Aoharu “team race” scheduler hook keyed by date without consuming a turn.
- Model selection: keep `YOLO_WEIGHTS_URA`, add `YOLO_WEIGHTS_AOHARU`; switching logic is in place via `Settings.normalize_scenario` though non-URA weights remain placeholders until trained.
- UX: F2 opens a lightweight popup or selection overlay to choose scenario (URA/Aoharu) then starts; default to last used scenario from config.
- Testing: add regression tests to ensure URA baseline remains identical post-refactor (policy decisions, race flow entry, skill-buy gates); still pending per PLAN step 7.
- Minimal surface changes: `main.py`, `core/settings.py`, `core/agent.py` (Waiter/agent tag), new `core/scenarios/*`, and Web UI schema/store for `activeScenario`.

## Detailed Findings (by area)
### Area: Runtime toggles & entry
- **Why relevant:** F2 hotkey now requests scenario selection and initializes per-scenario engines before Player runs, skipping the prompt when `scenarioConfirmed` is true.
- **Files & anchors (path:line_start–line_end):**
  - `main.py:195–328` — `BotState.start()` builds controller, OCR/YOLO, extracts preset, and instantiates `Player`.
  - `main.py:443–642` — `hotkey_loop()` binds F2 (and configured `Settings.HOTKEY`), calls `bot_state.toggle()`.
- **Cross-links:** `server/utils.load_config()`, `Settings.apply_config()`, `Settings.extract_runtime_preset()`.

### Area: Player and Waiter construction
- **Why relevant:** Single Waiter/agent tag is hardcoded to URA; needs scenario-aware tag for debug artifacts and analyzers.
- **Files & anchors:**
  - `core/agent.py:38–76` — `Player.__init__` signature and params.
  - `core/agent.py:49–57` — `PollConfig(... tag=Settings.AGENT_NAME_URA, agent=Settings.AGENT_NAME_URA)`.
- **Cross-links:** `core/utils/waiter.py` (synchronization), `Settings.AGENT_NAME_URA`.

### Area: Training policy/check (URA-specific)
- **Why relevant:** Core of scenario differentiation; URA Finale branch and heuristics live here.
- **Files & anchors:**
  - `core/actions/training_policy.py:556–616` — “URA Finale branch”.
  - `core/actions/training_check.py:115–692` — training screen scan and SV computation scaffolding.
- **Cross-links:** `core/utils/date_uma.py` (date helpers), `core/utils/support_matching.py`, `Settings` policy knobs.

### Area: Race & Events (likely shared)
- **Why relevant:** Mostly scenario-agnostic; later Aoharu team races need date-based inserts, not full rewrites.
- **Files & anchors:**
  - `core/actions/race.py:599–715` — race lobby flow and confirmations via Waiter.
  - `core/actions/events.py:176–567` — `EventFlow` selection with energy-overflow guardrails.
  - `core/actions/lobby.py:130–283` — turn processing and routing to training/race/rest.
- **Cross-links:** `core/utils/race_index.RaceIndex`, `server/utils.load_dataset_json()`.

### Area: Settings & model selection
- **Why relevant:** Central place to add scenario switch, agent names, and weights mapping.
- **Files & anchors:**
  - `core/settings.py:92–101` — YOLO weights (`YOLO_WEIGHTS_URA`, `YOLO_WEIGHTS_NAV`).
  - `core/settings.py:125–129` — `AGENT_NAME_URA`, `AGENT_NAME_NAV`.
  - `core/settings.py:178–320` — `apply_config()` (maps UI config → runtime), including hotkey, advanced knobs.
  - `core/settings.py:382–455` — `extract_runtime_preset()` (skills/races deck, priorities).
- **Cross-links:** `main.py` model factory (`make_ocr_yolo_from_settings`), `server/utils`.

### Area: Web UI config & UX
- **Why relevant:** Scenario selection and per-scenario preset handling now exist; remaining work is validating broader UX once additional scenarios ship.
- **Files & anchors:**
  - `web/src/models/config.schema.ts:16–44` — general/advanced schema (place to add `activeScenario`).
  - `web/src/models/config.schema.ts:86–96, 112–136` — `preset.event_setup.scenario` structure already present (name, rewardPriority, avoidEnergyOverflow).
  - `web/src/store/configStore.ts:45–95, 162–268` — config load/save/migration; active preset handling.
  - `web/src/pages/Home.tsx:56–107, 110–179` — tabs (Scenario setup, Shop, Team Trials) and preset shell.
- **Cross-links:** `server/main.py` config API, `server/utils.save_config`.

### Area: Datasets & analyzers (future Aoharu-specific)
- **Why relevant:** Aoharu needs detectors for white flames/Spirit Explosion and a team race calendar.
- **Files & anchors:**
  - `core/perception/analyzers/*` (hint, matching) — extension points for new icons/banners.
  - `server/utils.py:31–56` — dataset loader helpers for `datasets/in_game`.
- **Cross-links:** Add `datasets/in_game/aoharu_team_races.json` and YOLO classes for special icons (future step).

### Area: Persistence (skill memory)
- **Why relevant:** Prevent cross-scenario double-buys/memory bleed.
- **Files & anchors:**
  - `core/utils/skill_memory.py` (referenced in `Player` and `SkillsFlow`).
  - `core/agent.py:160–209` — Skill memory metadata refresh keyed to preset/date; extend with scenario key.
- **Cross-links:** `Settings.RUNTIME_SKILL_MEMORY_PATH`.

## 360° Around Target(s)
- **Target file(s):**
  - `main.py` — add scenario prompt on F2; pass scenario to Settings/engines before `BotState.start()`.
  - `core/settings.py` — add `ACTIVE_SCENARIO`, `AGENT_NAME_AOHARU`, `YOLO_WEIGHTS_AOHARU`, scenario-aware `get_active_preset_snapshot()` and memory path suffixing.
  - `core/agent.py` — parameterize Waiter tag/agent by scenario.
  - `core/scenarios/` — new folder. `ura/` moves current `training_policy.py` + `training_check.py`; `aoharu/` stubs with same interface.
  - `core/scenarios/registry.py` — simple resolver `get_policy(scenario)` returning `(scan_training_screen, decide_action_training)` callables.
  - `web/src/models/config.schema.ts` — add `general.activeScenario: z.enum(['ura','aoharu'])` with default; keep per-preset `event_setup.scenario` (different concept).
  - `web/src/store/configStore.ts` — load/save `activeScenario`; migrate from legacy if absent.
  - `core/utils/skill_memory.py` — include scenario in run metadata and file path.
- **Dependency graph (depth 2):**
  - `main.py` → `core/settings.py`, `server/utils.py`, `core/agent.py`.
  - `core/agent.py` → `core/actions/*`, `core/utils/waiter.py`, `core/utils/skill_memory.py`.
  - `core/scenarios/*` → `core/actions/training_check.py`-like scan + policy; `core/utils/date_uma.py`.
  - `web/src/models/config.schema.ts` → `web/src/store/configStore.ts` → FastAPI `/config` API.

- Scenario source of truth — resolved: `general.activeScenario` + `scenarioConfirmed` drive runtime; preset event scenarios remain for event preferences.
- F2 popup implementation — use a minimal Tkinter dialog vs. an overlay + arrow keys? Tkinter is simplest to ship; overlay-only requires keyboard handling.
- Default behavior — when no popup (e.g., remote/headless), should we auto-use the last saved `general.activeScenario`? Suggested: yes.
- Skill memory — implemented via per-scenario file metadata and path suffix.
- YOLO labels — do we ship a single universal model or per-scenario weights? Suggested: keep `uma_ura.pt` and add `uma_aoharu.pt` initially.
- Team race scheduler — lives in Lobby vs. Race flow? Suggested: Lobby schedules special team races by date (every six months) and signals RaceFlow; does not consume a turn.
- Web UI tabs — presets remain universal; scenario toggle + confirmation guardrails are active. Consider preset filtering when a third scenario arrives.

## Suggested Next Step
- Draft `PLAN.md` with per-file changes, exact function signatures for `core/scenarios/registry.py`, hotkey popup behavior, Settings additions, and a targeted test plan:
  - Unit tests: ensure URA policy decisions for known inputs remain identical pre/post refactor; Waiter tag = `ura`; F2 without popup uses last-saved scenario.
  - Smoke: start/stop loop, race lobby entry, skills purchasing gate under URA.
  - Web UI: save/load round-trip including `general.activeScenario`.

---
Important!: Generate RESEARCH.md file at the end in the right place. Don't forget the place or slug, we may have a lot of folder features so don't get confused
