---
date: 2025-10-10T16:31:46-05:00
topic: planned_race_suppression
status: research_complete
---

# RESEARCH — planned_race_suppression

## Research Question
Why are scheduled races from the config often ignored and replaced by normal lobby behavior?

## Summary (≤ 10 bullets)
- **Root Guard** `core/actions/lobby.py:162-193` suppresses planned races whenever either `is_first_junior_date` or `_skip_race_once` is true, logging the observed message.
- **Date OCR Fragility** `core/actions/lobby.py:537-829` plus `core/utils/date_uma.py:175-297` can misclassify the current date; stale or auto-advanced `DateInfo` may keep `year_code==1, month==7, half==1` even after Junior July, triggering the guard.
- **Skip Flag Persistence** `core/actions/lobby.py:857-865` sets `_skip_race_once` after any race attempt; it only clears mid-loop (line 192) if execution reaches that point, so early returns or exceptions leave it armed for the next cycle.
- **Agent-Level Interaction** `core/agent.py:348-405` may set `_skip_race_once` when `RaceFlow` fails or refuses, pairing with the guard to suppress later planned races in the same half/month.
- **Config Path** `core/settings.py:223-259` pulls `plannedRaces` from the active preset; schema uses `Y{year}-{MM}-{half}`, matching the guard’s key (`date_key_from_dateinfo`).
- **Dataset Consistency** `datasets/in_game/races.json` (via `core/utils/race_index.py:95-185`) validates that schedule entries exist; mismatches convert to fallback OCR attempts, potentially causing repeated fail/skip cycles.
- **UI Scheduler** `web/src/components/presets/RaceScheduler.tsx:47-205` produces keys using `toDateKey`; user input errors (e.g., duplicates) propagate directly to runtime without extra guards.
- **Observed Symptom** Log message `[lobby] Planned race suppressed by first-junior-day/skip flag.` confirms guard path; no other module emits that string.

## Detailed Findings (by area)
### Area: Lobby flow / planned race guard
- **Why relevant:** Core logic deciding whether to launch a scheduled race; houses the suppression message.
- **Files & anchors (path:line_start–line_end):**
  - `core/actions/lobby.py:162–193` — main guard for planned races.
  - `core/actions/lobby.py:831–865` — `_plan_race_today()` picks scheduled race based on `DateInfo`.
  - `core/actions/lobby.py:900–929` — additional G1/goal checks reuse `_skip_race_once` guard.
- **Cross-links:** `LobbyFlow.mark_raced_today()` (`core/actions/lobby.py:857–864`) sets `_skip_race_once` after race completion; `Player._desired_race_today()` (`core/agent.py:124–137`) mirrors the date key lookup.

### Area: Date detection & auto-advance
- **Why relevant:** Mis-detected dates can masquerade as the first junior half, incorrectly tripping the guard.
- **Files & anchors (path:line_start–line_end):**
  - `core/actions/lobby.py:537–829` — `_process_date_info()` handles OCR, warm-up, and auto-advance heuristics.
  - `core/utils/date_uma.py:175–297` — `parse_career_date()` parses strings like “Classic Year Early Apr”.
  - `core/utils/race_index.py:65–81` — `date_key_from_dateinfo()` drops keys lacking month/half, so partial OCR results erase planned lookups.
- **Cross-links:** `collect(...)` (`core/utils/yolo_objects.py`, imported at top) supplies OCR inputs; `extract_career_date()` (`core/perception/extractors/state.py`) feeds raw text.

### Area: Skip flag propagation via Agent & RaceFlow
- **Why relevant:** `_skip_race_once` is toggled at agent level after failed race attempts, potentially suppressing future planned races.
- **Files & anchors (path:line_start–line_end):**
  - `core/agent.py:348–405` — handles `TO_RACE` outcome for planned races; sets `_skip_race_once` when `RaceFlow` declines or errors.
  - `core/agent.py:412–432` — similar guard for “critical goal” races.
  - `core/actions/lobby.py:857–865` — lobby-level setter triggered post-race.
- **Cross-links:** `RaceFlow.run()` (not yet reviewed) may throw `ConsecutiveRaceRefused`, leading to the skip path; `core/actions/race.py` defines that exception.

### Area: Config schema & UI scheduler
- **Why relevant:** Ensures `plannedRaces` is loaded correctly; malformed keys or duplicates could cause fallback loops that arm the skip flag.
- **Files & anchors (path:line_start–line_end):**
  - `core/settings.py:223–259` — extracts `plannedRaces` from active preset.
  - `web/src/components/presets/RaceScheduler.tsx:47–205` — UI to add/remove planned races, providing copy of keys/race names.
  - `web/src/utils/race.ts:1–11` — key generator (`Y{year}-{MM}-{half}`) used by UI.
- **Cross-links:** `server/main.py:25–34` exposes `/config` API; `server/utils.py` handles persistence (not inspected in detail); `prefs/config.sample.json:21–446` demonstrates planned race configuration.

## 360° Around Target(s)
- **Target file(s):** `core/actions/lobby.py`, `core/agent.py`, `core/settings.py`, `core/utils/date_uma.py`, `core/utils/race_index.py`, `web/src/components/presets/RaceScheduler.tsx`
- **Dependency graph (depth 2):**
  - `core/actions/lobby.py`
    - depends on `core/utils/date_uma.py`, `core/utils/race_index.py`, `core/utils/logger.py`, `core/perception/extractors/state.py`.
    - upstream triggers include `core/agent.py` (calls `LobbyFlow.process_turn()` and `LobbyFlow.mark_raced_today()`).
  - `core/agent.py`
    - depends on `core/actions/race.py`, `core/actions/lobby.py`, `core/actions/training_policy.py`, `core/settings.py`.
    - invoked by `main.py` via `Player` instantiation.
  - `core/settings.py`
    - depends on persisted config via `server/utils.load_config()` and front-end updates.
  - `web/src/components/presets/RaceScheduler.tsx`
    - depends on `/api/races` (`server/main.py:80–92`), `useConfigStore` (`web/src/store/configStore.ts`, not inspected), and `web/src/utils/race.ts`.

## Open Questions / Ambiguities
- **Date OCR accuracy:** Is `extract_career_date()` frequently returning partial strings (e.g., missing month) that cause auto-advance to mislabel the calendar as `Y1-07-1`? — matters because planned races rely on precise keys; need telemetry or logs of `self.state.career_date_raw` around failures.
- **Skip flag lifetime:** Under what sequences does `_skip_race_once` remain true when `_plan_race_today()` runs? — investigating whether earlier returns or exceptions leave the flag set; could instrument the flow to confirm.
- **RaceFlow failure reasons:** Are scheduled races failing due to dataset mismatches (e.g., race order) leading to repeated `ConsecutiveRaceRefused` exceptions? — understanding failure modes would guide whether to add retry/backoff before setting the skip flag.

## Suggested Next Step
- Draft `PLAN.md` with instrumentation tasks: add detailed logging around `DateInfo`, `_skip_race_once`, and `RaceFlow` outcomes; consider capturing telemetry to pinpoint whether calendar misreads or skip propagation drive the suppression.
