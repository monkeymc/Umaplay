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
AI-driven automation for Umamusume: Pretty Derby. A Python runtime controls a game window (Steam/Scrcpy/Bluestacks) using PyAutoGUI, with perception via YOLO (Ultralytics) and OCR (PaddleOCR). A FastAPI server hosts a local Web UI (Vite/React) to edit presets and runtime settings stored in `prefs/config.json`. Optionally, heavy perception offloads to a separate FastAPI inference microservice.
This document explains the **AI side** of the project: perception models, extractors, analyzers, decision policy, and how the agent stitches everything together to act inside *Uma Musume: Pretty Derby* (Steam PC and Android via scrcpy).

> If you’re just trying to run the bot end-to-end, see `README.md` / `README.gpu.md`.
> If you’re collecting data or training models, see `README.train.md`.

---

## What this agent actually does

At a high level, the agent runs a loop:

1. **Capture & Detect** the game UI with YOLO (stable anchors, not templates).
2. **Extract** structured state via OCR and small CV analyzers (bars/badges).
3. **Score** training options with a transparent **Support Value (SV)** policy (risk-aware).
4. **Decide** among: train/rest/recreation/race/skills/events.
5. **Act** with a controller (precise local↔screen coordinate transforms).
6. **Repeat**, saving debug overlays when useful.

It supports both **Steam on Windows** and **Android mirrored with scrcpy**.

---

## Repository map (AI-relevant)

```
core/
  actions/
    claw.py                 # predictive controller for claw mini-game
    events.py               # click top-most event choice (OCR/YOLO gated)
    lobby.py                # lobby logic: rest/recreate/race/skills/training
    race.py                 # end-to-end race flow & skipping
    skills.py               # OCR-aware auto buying with active-button check
    training_check.py       # training scan + SV scoring helpers
    training_policy.py      # date/mood/energy-aware decision policy
  controllers/
    android.py              # scrcpy (client-area) capture & input
    base.py                 # IController interface & shared helpers
    steam.py                # Steam controller (client-area, left-half capture)
  perception/
    analyzers/
      badge.py              # race badge classification (EX/G1/G2/…)
      energy_bar.py         # pill interior segmentation → % fill
      friendship_bar.py     # color (blue/green/orange/yellow) + fill
      hint.py               # pink hint badge detector
      mood.py               # color-first mood classifier with OCR fallback
      support_type.py       # SPD/STA/PWR/GUTS/WIT/Friend glyph classifier
    extractors/
      state.py              # mood/turns/date/energy/stats/goal/points/infirmary
      training_metrics.py   # robust Failure% ROI per raised tile
    detection.py            # YOLO model cache + prediction + flattening
    digits.py               # fast numeric OCR (digits)
    is_button_active.py     # small classifier for “active” button state
    ocr.py                  # PaddleOCR wrapper (mobile/server backends)
  utils/
    analyzers.py, geometry.py, img.py,
    text.py, waiter.py, yolo_objects.py, pointer.py, debug.py, logger.py
  agent.py                  # orchestrates Lobby/Training/Race/Skills flows
  settings.py               # knobs (OCR models, YOLO, debug, policies)
  types.py                  # DetectionDict, XYXY, constants/classes
server/
  main.py, utils.py         # minimal FastAPI + uvicorn runner
main.py                     # hotkey toggle + server bootstrap
```

---

## End-to-end loop (current `main.py`)

* **Hotkey toggle**: press your configured key (default `HOTKEY` in `Settings`, plus a hardcoded fallback `F4`) to **start/stop** the agent thread.

  * Uses `keyboard` hooks with a polling fallback (admin rights may be required on Windows).
* **Server**: runs uvicorn (`server/main.py`) so you can integrate or monitor.
* **Controllers**:

  * `SteamController("Umamusume")` (change the window title if needed).
  * `ScrcpyController(window_title="...")` for Android.
* **OCR**: choose **fast** or **server** PP-OCRv5 models via `Settings.USE_FAST_OCR`.

```python
# Simplified
ctrl = SteamController("Umamusume")           # or ScrcpyController("23117RA68G")
ocr  = OCREngine(text_detection_model_name="PP-OCRv5_mobile_det", ...)

state = BotState()
threading.Thread(target=hotkey_loop, args=(state, ctrl, ocr), daemon=True).start()
boot_server()  # uvicorn FastAPI app
```

---

## Perception: how we “see” the screen

### Object detection (YOLO, `core/perception/detection.py`)

* Cached **Ultralytics YOLO** model; lazy load from `Settings.YOLO_WEIGHTS` (CUDA if available).
* Returns normalized `DetectionDict` records `{name, conf, xyxy, idx}` in **last-screenshot local coords**.
* Typical classes used (non-exhaustive):
  `training_button`, `support_card`, `support_card_rainbow`, `support_bar`, `support_type`, `ui_stats`, `ui_turns`, `ui_mood`, `ui_skills_pts`, `ui_goal`, `ui_energy`, `lobby_training`, `lobby_races`, `lobby_rest`, `lobby_rest_summer`, `lobby_skills`, `lobby_infirmary`, `button_white`, `button_green`, `button_skip`, `race_square`, `race_star`, `race_badge`, `race_after_next`, `skills_square`, `skills_buy`, `event_choice`.

> Steam controller usually captures the **left half** of the client area (fast, where most UI lives). Scrcpy controller captures the **full client area**.

### OCR & digits (`perception/ocr.py`, `perception/digits.py`)

* **PP-OCRv5** (mobile/server variants) for free text like **goal** and **date**.
* Lightweight **digit recognizer** for **turns** and **skill points**.
* Robust stat parsing tolerates OCR quirks (e.g., trailing letters, O↔0, I↔1) with clamping and salvage rules.

### Analyzers (classical CV)

* **Energy bar**: segments the pill **interior** into colored gradient vs gray to compute `energy_pct` (avoids rings/caps).
* **Friendship bar**: estimates color (`blue/green/orange/yellow/max`) and fill with column-wise votes.
* **Hint badge**: pink badge detector in card’s top-right.
* **Support type**: glyph/edge in top-left quadrant + hue fallback → `spd|sta|pwr|guts|wit|friend`.
* **Mood**: color-first label (`AWFUL`→`GREAT`) with OCR fallback.

### State extractors (`perception/extractors/state.py`)

* **Mood** → `("GOOD", 4)` style.
* **Turns** → integer turns left (`digits()`).
* **Career date** → OCR string, later parsed into `DateInfo`.
* **Energy** → analyzer percent.
* **Stats** → five segments cropped from `ui_stats`, parsed to ints with noise guards.
* **Skill Points / Goal** → digits/text OCR.
* **Infirmary** → active/off via small classifier or brightness fallback.

---

## Training screen intelligence

### 1) Scan tiles once (no churning)

`core/actions/training_check.py::scan_training_screen(...)`:

* **Detect** `training_button` ×5. If one is already **raised**, harvest it **without clicking**.
* For each remaining tile (left→right):

  * Click center (with jitter), short randomized pause.
  * **Re-capture**; **refresh** anchors and geometry.
  * Collect all **support cards** shown on the overlay (including parts like `support_bar`/`support_type`).
  * Run analyzers: `support_type`, `friendship_bar`, `has_hint`, `has_rainbow`.
  * **Failure %** via `extract_failure_pct_for_tile(...)` using the stats strip ↔ button overlay ROI.
* Output list (by `tile_idx`) with:

  ```json
  {
    "tile_idx": 0..4,
    "tile_xyxy": [x1,y1,x2,y2],             // local coords of training button
    "tile_center_x": ...,
    "supports": [ { name, support_type, friendship_bar, has_hint, has_rainbow, ... } ],
    "has_any_rainbow": true/false,
    "failure_pct": 0..100,                  // -1 → unreadable; energy-aware fallback sets to MAX+1
    "skipped_click": true/false
  }
  ```

### 2) Score with Support Value (SV)

`training_check.py::compute_support_values(training_state)` implements your latest rules:

* **Blue/Green** card: `+1` each (tile-capped hint **+0.5** once).
* **Orange/Max**: baseline `+0`, but hint gives **+0.5** (tile-capped).
* **Rainbow** card: `+1` each (if ≥2 rainbows on the tile → **+0.5** combo).
* **Reporter (Etsuko)**: `+0.1`.
* **Director**: color-based bonus
  `blue:+0.50, green:+0.25, orange:+0.15, yellow/max:+0`.
* **Risk gate** (Failure%):

  * Base cap **20%**.
  * If `SV ≥ 3.5`, relax cap ×**1.5** (→ 30%).
  * Produce `risk_limit_pct`, `allowed_by_risk`, and `greedy_hit` (if `SV ≥ 3.0` and risk OK).
* Returns per-tile dicts with **notes** explaining contributions (great for logs and tuning).

### 3) Decide what to do on Training

`training_policy.py::decide_action_training(...)` takes:

* `sv_rows` from the step above,
* **mood**, **turns\_left**, **career\_date** (`DateInfo`),
* **energy\_pct**, **stats**, **prioritize\_g1** flag,
* optional `priority_stats` (default order: `SPD, STA, WIT, PWR, GUTS`).

It returns `(TrainAction, tile_idx|None, "why")` with transparent reasoning. The policy includes:

* **Top picks** if SV ≥ 2.5 or ≥ 2.0 and **risk OK**.
* **Distribution nudge**: if a **top-3 priority** stat is undertrained ≥7% vs reference distribution and its best SV is close to the global best, prefer it.
* **WIT soft-skip** near **summer** or with rainbow/WIT opportunities.
* **Director windows** (Senior year, color-aware) if risk-allowed.
* **Energy** gates (rest at ≤35%, URA rest at ≤50%).
* **Racing**:

  * If `prioritize_g1` and not Junior year (and not explicitly skipped).
  * Else when **not summer**, **energy ≥ 68%**, and not pre-debut.
* **Late game (URA)**: prefer hints; otherwise WIT/REST; else best allowed.
* **Fallbacks**: WIT → REST → best allowed → NOOP.

Use `training_policy.check_training(player, skip_race=...)` to run the whole training decision step: it scans, scores, logs the SV table+notes, and returns a `TrainingDecision` (including `why`).

---

## Lobby, Races, Skills, Events

### Lobby (`core/actions/lobby.py`)

* Maintains a light **LobbyState**: `goal`, `energy`, `skill_pts`, `infirmary_on`, `turn`, `date_info`, `is_summer`, `mood`, `stats`.
* Optimizations to **refresh stats** every N cycles, with jump debouncing/persistence.
* **Race early** if critical goals (fans/G1) and energy is fine.
* **Infirmary** when ON (outside summer).
* **Rest/Recreation** decisions based on energy, upcoming summer, and mood.
* Navigates into **Training** when nothing critical is pending.
* Predicts **turns** cheaply between OCR updates; robust **date parsing** (monotonic, merge partial info, jump sanity).

### Race (`core/actions/race.py`)

* Picks a **race square** (≥2 stars) and **badge** (EX>G1>G2>G3>OP), with `prioritize_g1` toggle.
* Uses an **ActiveButtonClassifier** to see if “VIEW RESULTS” is clickable; otherwise clicks green **RACE**, confirms, and taps **SKIP** sequences.
* Handles post-race screens (`NEXT`, `CLOSE`, special `race_after_next`).
* Robust scroll and tie-breakers (topmost, rank).

### Skills (`core/actions/skills.py`)

* Scans `skills_square` + `skills_buy`, checks **active** buy buttons with the classifier, OCR-matches target names (fuzzy).
* If targets clicked: **Confirm → Learn → Close → Back** sequence, OCR-gated at each step.
* Early-stop when two consecutive views look **nearly identical** (signature buckets).

### Events (`core/actions/events.py`)

* Clicks the **top** event choice (with confidence filter) when multiple choices exist.

### Claw mini-game (`core/actions/claw.py`)

* Predictive **hold→release** controller using observed velocity and loop latency; handles thin targets and flicker. Saves overlays to `debug/claw_test/`.

---

## Controllers: precise, origin-aware input

Both controllers keep **last screenshot origin** so every `xyxy` in detections can be transformed into **absolute screen coordinates** for clicks/scrolls:

* `center_from_xyxy(xyxy)` → screen `(x,y)`.
* `click_xyxy_center(xyxy, clicks=N, jitter=auto)`.
* `scroll(...)` with naturalistic drags (scrcpy) or wheel (Steam).
* Organic pointer motion + subtle jitter to reduce misclicks.

---

## Config & knobs (selected)

Adjust in `core/settings.py` (or via `config.json` if you load it there):

* **Detectors**: `YOLO_WEIGHTS`, `YOLO_IMGSZ`, `YOLO_CONF`, `YOLO_IOU`, `USE_GPU`.
* **OCR**: `USE_FAST_OCR` to switch PP-OCRv5 mobile/server models.
* **Debug/data**: `DEBUG`, `DEBUG_DIR`, `STORE_FOR_TRAINING`, `STORE_FOR_TRAINING_THRESHOLD`.
* **Policy**: `CHECK_STATS_INTERVAL`, `MINIMUM_SKILL_PTS`, `PRIORITIZE_G1`, `PAUSE_AFTER_CLICK_SEC`, `MAX_FAILURE`.
* **Server**: `HOST`, `PORT`.
* **Hotkey**: `HOTKEY` (plus fallback `F4`).

---

## Data collection & training

* Use `collect_training_data.py` and `prepare_uma_yolo_dataset.py` to capture and curate YOLO training data from live runs (the Android controller can save **low-confidence** detections with overlays for labeling).
* Notebooks:

  * `dev_ocr.ipynb` – iterate OCR/segments/regex salvage.
  * `dev_play.ipynb` – drive flows from a notebook (introspect decisions).
  * `dev_train.ipynb` – model training experiments.

---

## Typical logs you’ll see

* **SV table** with per-tile notes (e.g., “rainbow:+1”, “Hint on blue/green:+0.50”, “Director(blue):+0.50”).
* **Policy reasons** (string `why`): the decision trace is emitted to help tuning.
* **Stats updates** with jump persistence: “accepted confirmed big jump … (Δ=…)”.

---

## Extending the agent

* **New detector**: add a YOLO class; anchor ROIs using those boxes. Avoid raw template matching.
* **New analyzer**: drop a module under `perception/analyzers/` and wire it in `extractors`.
* **New flow**: follow the pattern: perceive → decide → act, and **re-capture after each click**.
* **Swap policy**: keep `scan_training_screen()` output; plug your scoring/learning model into `training_check` / `training_policy`.

---

## Quick start (AI-focused)

1. **Install** requirements (`requirements.txt`) and GPU runtimes (see `README.gpu.md`).
2. **Configure** `Settings` (weights paths, OCR mode, debug dir, hotkey).
3. **Open** the game (Steam window “Umamusume” or scrcpy device window title).
4. **Run**:

   ```bash
   python main.py
   ```
5. Press **HOTKEY** (and/or **F4**) to toggle the agent. Watch the terminal logs.

> For Steam capture reliability on Windows, run your shell **as Administrator** (keyboard hooks + client-area capture).

---

## Troubleshooting

* **No window focus**: update your Steam/scrcpy **window title** in `main.py`.
* **Detections missing**: lower `YOLO_CONF` a bit; ensure the correct `YOLO_WEIGHTS`.
* **OCR weird digits**: try the **server** PP-OCR models (`USE_FAST_OCR=False`).
* **Clicks off-by-some**: controllers rely on **last screenshot** origin—avoid external windows covering the game; don’t resize during a run.
* **Hotkey not firing**: Windows may require admin for `keyboard`; polling fallback still tries every \~80ms.

---

## Appendix A — Key data structures

### `DetectionDict`

```python
{
  "name": "training_button",
  "conf": 0.91,
  "xyxy": (x1, y1, x2, y2),
  "idx": 0
}
```

### Training scan row

```python
{
  "tile_idx": 0,
  "tile_xyxy": [...],
  "tile_center_x": 123.4,
  "supports": [
    {
      "name": "support_card",
      "support_type": "SPD",
      "support_type_score": 0.92,
      "friendship_bar": { "color":"green", "progress_pct":53, "is_max":false },
      "has_hint": true,
      "has_rainbow": false,
      "xyxy": [...]
    },
    ...
  ],
  "has_any_rainbow": true,
  "failure_pct": 12,
  "skipped_click": false
}
```

### SV row (from `compute_support_values`)

```python
{
  "tile_idx": 0,
  "failure_pct": 12,
  "risk_limit_pct": 20,
  "allowed_by_risk": true,
  "sv_total": 3.50,
  "sv_by_type": { "cards":2.00, "hint_bluegreen":0.50, "rainbow_combo":0.50, ... },
  "greedy_hit": true,
  "notes": ["green:+1.00", "rainbow:+1.00", "Hint on blue/green (tile-capped): +0.50", ...]
}
```

---

## Appendix B — YOLO class glossary (partial)

* **Training**: `training_button`, `support_card`, `support_card_rainbow`, `support_bar`, `support_type`
* **Global UI**: `ui_stats`, `ui_turns`, `ui_mood`, `ui_skills_pts`, `ui_goal`, `ui_energy`
* **Lobby**: `lobby_training`, `lobby_races`, `lobby_rest`, `lobby_rest_summer`, `lobby_skills`, `lobby_infirmary`
* **Buttons**: `button_green`, `button_white`, `button_skip`
* **Race**: `race_square`, `race_star`, `race_badge`, `race_after_next`
* **Skills**: `skills_square`, `skills_buy`
* **Events**: `event_choice`



## DIRS
<dir>
├── assets/
├── build/
├── core/
│ ├── actions/ (flows: lobby, race, skills, training, events, claw)
│ ├── controllers/ (window control: Steam, Scrcpy, Bluestacks, static)
│ ├── perception/ (yolo, ocr, analyzers, extractors)
│ ├── utils/ (logging, geometry, waiter, event catalog)
│ ├── agent.py
│ ├── settings.py
│ └── version.py
├── datasets/
│ ├── in_game/ (events.json, event_catalog.json, races.json, skills.json)
│ └── uma/ (training data/images/labels)
├── docs/
│ ├── README.gpu.md
│ ├── README.virtual_machine.md
│ └── ai/
├── models/ (YOLO weights, classifiers)
├── prefs/ (config.json, config.sample.json, preset.sample.json)
├── server/
│ ├── main.py (FastAPI app + static serving)
│ ├── main_inference.py (optional inference API)
│ ├── updater.py (GitHub release check)
│ └── utils.py (config IO, dataset loader)
├── web/
│ ├── src/ (React app, Zustand stores, Zod schemas)
│ ├── dist/ (built UI served by FastAPI)
│ └── vite/ts configs
├── tests/ (pytest with image fixtures)
├── main.py (entrypoint: bot + web server)
├── requirements.txt
└── README.md
</dir>

## Module & Directory Map (2–3 levels)
- Runtime
  - `main.py` — launches FastAPI (`server/main.py`) and hotkey loop; orchestrates `core.agent.Player`.
  - `core/agent.py` — agent loop; composes flows in `core/actions/*` with YOLO/OCR and controller.
  - `core/controllers/*` — window/device abstraction (`IController`, Steam/Scrcpy/Bluestacks).
  - `core/perception/*` — detection (`yolo/*`), OCR (`ocr/*`), analyzers and extractors.
  - `core/utils/*` — logging, waiting/polling, geometry, events catalog builder.
- Web/Server
  - `server/main.py` — FastAPI app: config CRUD, datasets API, admin update, static UI.
  - `web/src` — React + MUI + Zustand + Zod; config editor and event setup UI.
  - `server/main_inference.py` — optional FastAPI microservice for OCR/YOLO offload.
- Data & Config
  - `prefs/config.json` — user config persisted by Web UI.
  - `datasets/in_game/*.json` — game metadata (skills, races, events, catalog).
  - `models/` — weights and classifiers (`uma.pt`, `active_button_clf.joblib`).

## Runtime Topology (diagram-as-text)
- Web UI (Vite/React in `web/dist`) → FastAPI (`server/main.py`) → reads/writes `prefs/config.json`.
- Bot runtime (`main.py`) → constructs `IController` → game window capture + input via PyAutoGUI.
- Bot runtime → YOLO detector + OCR engine (local) → perception (classes, text) → flows → actions/clicks.
- Optional: Bot runtime → Remote OCR/YOLO (`server/main_inference.py`) over HTTP.
- Data dependencies: `datasets/in_game/*.json` (skills, races, events) and `models/*` (YOLO/CLF).
- Observability: logs via `core/utils/logger.py` to console and `debug/`.

## Services / Apps (repeat per unit)
### Bot + Web Server (monolith)
- Purpose:
  - Serve Web UI, persist configuration, and run the gameplay automation agent.
- Entry points (files + line anchors):
  - `main.py:278–309` — `__main__` boot sequence (ensure config, apply settings, spawn hotkey, start server).
  - `main.py:88–91` — `boot_server()` runs `uvicorn` with `server.main:app`.
  - `main.py:212–271` — `hotkey_loop()` registers/polls hotkeys to toggle the bot.
  - `main.py:37–54` — `make_controller_from_settings()` selects Steam/Scrcpy/Bluestacks controller.
  - `main.py:57–82` — `make_ocr_yolo_from_settings()` selects local vs remote OCR/YOLO engines.
- Public interfaces:
  - HTTP (FastAPI in-process):
    - `server/main.py:24–31` GET/POST `/config` — load/save `prefs/config.json`.
    - `server/main.py:62–74` GET `/api/skills` — skills dataset.
    - `server/main.py:76–87` GET `/api/races` — races dataset.
    - `server/main.py:90–101` GET `/api/events` — events dataset.
    - `server/main.py:106–132` GET/POST `/api/presets/{preset_id}/event_setup` — focused event prefs.
    - `server/main.py:144–178` POST `/admin/update` — safe git fetch + ff-only pull (localhost only).
    - `server/main.py:183–213` POST `/admin/force_update` — hard reset + clean + pull (localhost only).
    - `server/main.py:219–225` GET `/admin/version`, `/admin/check_update` — app version and GH latest.
    - `server/main.py:134–141, 228–241` `GET /` and fallback static file serving (`web/dist`).
  - Hotkey: `F2` by default to start/stop bot (`main.py:212–241`).
  - Windows input: PyAutoGUI mouse/scroll via `core/controllers/*`.
- Key internal dependencies:
  - `core/agent.py:30–112` — `Player` constructor wiring flows and engines.
  - `core/agent.py:136–360` — `Player.run()` main loop, screen classification, flow dispatch.
  - `core/controllers/base.py:15–58` — `IController` interface; screenshot/input utilities (`click_xyxy_center` etc.).
  - `core/perception/yolo/interface.py:8–25,37–49` — detector protocol and capture API.
  - `core/perception/ocr/interface.py:5–25` — OCR protocol.
  - `server/utils.py:10–19,54–76` — config load/save and ensure/seed.
  - `core/settings.py:106–155,156–173` — applying config and extracting preset runtime knobs.
- External dependencies:
  - Ultralytics (`ultralytics`), Torch (`torch`), OpenCV (`opencv-python`), PaddleOCR (`paddleocr`, `paddlepaddle`, `paddlex`).
  - FastAPI/Uvicorn for HTTP server; `keyboard` for hotkeys; `pyautogui` for input; `ImageHash`, `RapidFuzz`.
- Data models & storage:
  - Config: `prefs/config.json` (Web UI writes via `/config`). Seed: `prefs/config.sample.json`.
  - Datasets: `datasets/in_game/{skills.json,races.json,events.json,event_catalog.json}` loaded via `server/utils.py:32–52`.
  - Models: YOLO weights (`models/uma.pt`), button-activity classifier (`models/active_button_clf.joblib`).
  - Logs: `debug/debug.log` and timestamped logs via `core/utils/logger.py:40–96`.
- Configuration & feature flags:
  - Mapped from `config.json` to runtime in `core/settings.py:115–155` (mode, window title, fast mode, thresholds, external processor URL, hotkey, auto-rest, etc.).
  - Preset runtime extraction (`plan_races`, `skillsToBuy`, `selectStyle`) in `core/settings.py:156–173`.
- Observability:
  - Console + file logging with level control via `Settings.DEBUG` (`core/utils/logger.py:40–96`).
  - Minimal in-app warnings/info in flows; errors captured and logged in agent (`main.py:158–180`).
- Tests:
  - `tests/` pytest suite; image-based e2e-like extractors (e.g., `tests/test_turns.py:56–82,94–107`).

### Inference Microservice (optional)
- Purpose:
  - Offload OCR and YOLO from client machines to a stronger host.
- Entry points (files + line anchors):
  - `server/main_inference.py:21–28` — FastAPI app + health.
  - `server/main_inference.py:31–43,77–110` — OCR request model and `/ocr` endpoint.
  - `server/main_inference.py:111–119,120–137` — YOLO engine and `/yolo` endpoint.
- Public interfaces:
  - HTTP JSON API at `/health`, `/ocr`, `/yolo`.
- Key internal dependencies:
  - `core/perception/ocr/ocr_local.py` and `core/perception/yolo/yolo_local.py` for engines.
- External dependencies:
  - Torch, Ultralytics, PaddleOCR, OpenCV.
- Data models & storage:
  - Loads models on process start; stateless per request.
- Configuration & feature flags:
  - Consumed by bot when `Settings.USE_EXTERNAL_PROCESSOR=True` (`main.py:66–72`).
- Observability:
  - FastAPI exception messages; checksum metadata for debugging responses.
- Tests:
  - No direct tests; integration exercised via bot when enabled.

### Web UI
- Purpose:
  - Edit general settings and presets, manage event preferences, trigger updates, and save config to backend.
- Entry points (files + line anchors):
  - `web/src/main.tsx` — React bootstrap; routes/layout.
  - `web/src/services/api.ts:10–44,46–72,74–118` — backend client for config, datasets, and admin endpoints.
- Public interfaces:
  - Consumes FastAPI routes under `/config`, `/api/*`, `/admin/*`.
- Key internal dependencies:
  - State: `web/src/store/configStore.ts:40–80,98–160` (Zustand store with schema-normalized config IO).
  - Schemas: `web/src/models/config.schema.ts:15–37,40–88,97–122` (Zod schemas and defaults).
- External dependencies:
  - React, MUI, Zustand, Zod, TanStack Query, Axios; built with Vite + TypeScript.
- Data models & storage:
  - LocalStorage backup (`LS_KEY`) and POST to backend `/config`.
- Configuration & feature flags:
  - UI toggles map to `general.advanced` (debugMode, useExternalProcessor, hotkey, autoRestMinimum, etc.).
- Observability:
  - Minimal; browser console logs on local load; backend responses shown as toasts where applicable.
- Tests:
  - No frontend tests in repo.

## Data & Persistence
- No DB. Files only:
  - Config: `prefs/config.json` seeded from `prefs/config.sample.json` (`server/utils.py:54–76`).
  - Datasets: `datasets/in_game/*.json` loaded with mtime cache (`server/utils.py:32–52`).
  - Models: `models/uma.pt`, `models/active_button_clf.joblib` referenced by `core/settings.py:58–64`.
  - Debug logs: `debug/` via `core/utils/logger.py:40–96`.

## External Integrations
- GitHub Releases: `server/updater.py:7–12,24–45` (check latest, compare versions; UI buttons call `/admin/*`).
- Optional device mirrors: Scrcpy/Bluestacks windows are controlled locally via controllers (no SDK).

## Cross-Cutting Concerns
- Authentication/authorization flows:
  - None. Admin update routes restricted to localhost checks (`server/main.py:145–150,186–188`).
- Error handling strategy:
  - Agent guards long loops with patience/debounce; try/except around main run to recover transient errors (`main.py:158–176`).
- Logging/metrics/tracing stack:
  - Structured logger with file and console handlers, levels via settings (`core/utils/logger.py`).
- Internationalization/theming:
  - Frontend uses MUI theming (light/dark in Zustand store); no i18n layer.
- Security boundaries, sensitive data handling:
  - No secrets/PII persisted; config file contains gameplay preferences only.
  - Update routes enforce clean git state and local-only access; force-update performs `git reset --hard`.

## Frontend Architecture (if applicable)
- App shell/routing: Single-page app served from `web/dist`; fallback handler returns `index.html` (`server/main.py:228–241`).
- State management: Zustand store for config (`web/src/store/configStore.ts`).
- Design system: MUI components; simple custom components in `web/src/components/*`.
- Tokens/themes: light/dark theme flag in store; no separate design tokens.
- Styling: CSS + MUI sx props; Vite builds to `web/dist` consumed by FastAPI static mount.

## Environments & Deployment
- Environments: Local execution (Windows focus). No CI configuration in repo.
- Run modes:
  - Monolith: `python main.py` → starts FastAPI on `127.0.0.1:8000` and hotkey listener.
  - Inference Host: `uvicorn server.main_inference:app --host 0.0.0.0 --port 8001` (README.md).
  - Client-only mode uses `requirements_client_only.txt` and `Settings.USE_EXTERNAL_PROCESSOR=True`.
- Artifacts: Frontend built with `web/package.json` scripts; output in `web/dist`.
- Secrets management: none.

## Performance & Capacity Notes
- YOLO parameters (`imgsz`, `conf`, `iou`) tunable via `Settings` and Waiter config; GPU usage enabled by default (`core/settings.py:73–79`).
- External inference reduces client CPU/GPU load at the cost of network latency.
- Dataset JSON loads cached by mtime (`server/utils.py:45–52`).
- Agent loop throttled by `delay` (default ~0.4s) and event debouncing/hotkey debounce.

## Known Hotspots & Risks
- Heavy frontend assets in `web/dist` and images in `datasets/uma/` (not used at runtime) — avoid shipping in minimal client installs.
- Window focus/handle detection can fail if titles mismatch; ensure `Settings.resolve_window_title()` mapping is correct (`core/settings.py:106–114`).
- OCR variability may misread small fonts; `USE_FAST_OCR` vs server models trade accuracy vs speed.
- Admin update endpoints execute git commands; require clean working tree and may fail on non-`main` branches.

## Glossary & Conventions
- SPD/STA/PWR/GUTS/WIT — stat keys in presets and detection overlays.
- `xyxy` — [x1,y1,x2,y2] rectangle; `xywh` — [x,y,width,height].
- `Waiter` — polling helper coordinating detection + clicks.
- `EventSetup` — focused event preferences per preset; persisted inside `prefs/config.json`.
- Screen classes — logical screens classified from YOLO detections (Lobby, Training, Event, etc.).

## Related Documents
- `README.md` — usage, installation, Web UI, Android setup.
- `docs/README.gpu.md` — GPU setup and notes.
- `docs/ai/SOPs/sop-config-back-front.md` — Standard Operating Procedure for managing configuration changes across frontend and backend (setting presets, general configs, wired with settings.py).
- `docs/README.virtual_machine.md` — VM usage guidance.
- `internal.md` — internal notes (if present).

## Open Questions
- Any additional auth or rate limiting on the FastAPI app? None found; consider adding if exposing beyond localhost. See `server/main.py`.
- Detailed training pipeline for YOLO weights is not described here; refer to `datasets/uma/` and potential external scripts.

## Source References
- `main.py:37–82,88–91,97–200,201–209,212–271,278–309` — controller/engine factories, server boot, bot state, hotkeys, main.
- `server/main.py:14–22,24–56,62–141,144–241` — FastAPI app, static mounts, datasets API, admin, routing/fallback.
- `server/main_inference.py:21–28,31–43,77–137` — inference microservice endpoints and models.
- `server/utils.py:10–19,32–52,54–76,78–90` — config IO, dataset loader, repo root helper.
- `core/agent.py:30–112,136–360` — agent composition and run loop.
- `core/controllers/base.py:15–58,60–122,123–171` — controller interface and input helpers.
- `core/perception/yolo/interface.py:8–25,37–49`; `core/perception/ocr/interface.py:5–25` — perception contracts.
- `core/settings.py:46–66,68–79,84–101,106–155,156–173` — paths, detection defaults, flags, config apply/extract.
- `web/src/services/api.ts:10–44,46–72,74–118`; `web/src/store/configStore.ts:40–80,98–160`; `web/src/models/config.schema.ts:15–37,40–88,97–122` — frontend API, state, schemas.
- `tests/test_turns.py:56–82,94–107` — example test pipeline and assertions.


# Web UI Overview

The Web UI is a React/TypeScript application that provides a configuration interface for the Uma Musume AI agent. It allows users to manage general settings and presets, with automatic local storage persistence and backend synchronization.

## Key Features

- **Modern Tech Stack**: Built with React 18, TypeScript, Vite, Material-UI, Zustand, and Zod
- **Responsive Design**: Adapts to different screen sizes with collapsible panels
- **Type Safety**: Full TypeScript support with Zod schema validation
- **State Management**: Centralized state with Zustand
- **Theming**: Light/dark mode support

## Project Structure

```
web/
├─ public/         # Static assets (images, icons)
├─ src/
│  ├─ components/  # Reusable UI components
│  ├─ models/      # Data models and schemas
│  ├─ pages/       # Main views
│  ├─ services/    # API clients and services
│  ├─ store/       # State management
│  └─ utils/       # Utility functions
```

## Configuration Flow

1. **Local State**: Changes are immediately reflected in the UI and auto-saved to Local Storage
2. **Persistence**: Click "Save config" to persist changes to the backend (`/config` endpoint)
3. **Backend Integration**: Python backend reads `config.json` on startup

## Development

### Setup

```bash
cd web
npm install
npm run dev  # Start dev server at http://localhost:5173
```

### Key Files

- `src/models/config.schema.ts` - Configuration types and validation
- `src/store/configStore.ts` - Central state management
- `src/components/` - Reusable UI components
- `src/pages/Home.tsx` - Main application layout

## Common Tasks

### Adding New Settings

1. Update schema in `config.schema.ts`
2. Add UI controls in the appropriate form component
3. Update backend mapping in `core/settings.py` if needed

### Styling

- Use Material-UI components and the `sx` prop for styling
- Follow the responsive patterns in existing components
- Keep styles co-located with components

For detailed implementation guides and advanced topics, see the full [Web UI Documentation](https://github.com/Magody/Umaplay/tree/main/web).
