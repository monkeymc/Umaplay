---
topic: planned_race_suppression
status: plan_ready
---

# PLAN — planned_race_suppression

## Objectives
- Ensure scheduled races defined in `plannedRaces` reliably trigger when their date key matches the current in-game calendar, without spurious "first junior day" suppression.
- Provide observability so logs reveal why a planned race was accepted or skipped, enabling regression detection during future runs.

## Changes by File (no diffs yet)
- `core/actions/lobby.py`
  - **Step 1 Goal:** Expand logging around the planned-race decision path (`process_turn()`, `_plan_race_today()`) to record `date_info`, `_skip_race_once`, `_date_artificial`, and chosen actions.  
    **Quick validation:** Run a short lobby loop with a scheduled race and confirm new `[planned_race]` log entries include the flag snapshot.
  - **Step 2 Goal:** Tighten the first-junior guard so it only suppresses when the date reading is confirmed (non-artificial, stable) and clear `_skip_race_once` after evaluation to prevent stale suppression.  
    **Quick validation:** Schedule Satsuki Sho; verify the flow enters `RaceFlow` instead of logging the suppression message, while a true first-junior day still skips.
  - **Edit:** `process_turn()` guard block (lines ~162–193) — gate suppression on confirmed `DateInfo`, reset `_skip_race_once` immediately after handling, and emit structured logs for each branch.
  - **Edit:** `_plan_race_today()` (lines ~831–855) — persist the resolved planned race key/name and surface guard context for logging.
  - **Add:** Helper (e.g., `_log_planned_race_decision`) to centralize the new logging payload and reuse it across guard outcomes.
- `core/agent.py`
  - **Step 1 Goal:** Mirror the lobby logging by noting when `_skip_race_once` is toggled during planned-race attempts (`Player._desired_race_today()`, planned `TO_RACE` handling).  
    **Quick validation:** Trigger a planned race refusal (e.g., force `ConsecutiveRaceRefused`) and confirm the agent log records skip toggles with date keys.
  - **Step 2 Goal:** After a failed planned race, attempt a lightweight reset so the next lobby tick reconsiders the plan when conditions allow, rather than leaving `_skip_race_once` armed indefinitely.  
    **Quick validation:** Simulate a failed planned race and ensure the next lobby cycle either retries or logs the reason the reset didn’t occur.
  - **Edit:** `Player` planned-race branch (lines ~348–405) — include richer logging and ensure `_skip_race_once` is cleared when it is safe to retry.
- `core/utils/date_uma.py`
  - **Step 2 Goal:** Provide a helper (e.g., `date_is_confident()`) that tells whether the parsed date has reliable month/half fields, so the lobby guard can rely on it.  
    **Quick validation:** Unit-test the helper with known OCR strings (complete vs partial) to confirm it only marks full Junior July Early as confident.
  - **Add:** New function exporting the confidence heuristic used by `LobbyFlow`.
- `tests/` (new or existing module)
  - **Step 2 Goal:** Add regression coverage for the guard logic by simulating date/flag combinations to ensure planned races proceed when expected.  
    **Quick validation:** Run targeted test (e.g., `pytest tests/test_lobby_plan.py`) and confirm it fails with old guard and passes with the new logic.

## Snippet Anchors to Touch
- `core/actions/lobby.py` — `LobbyFlow.process_turn()` (lines ~162–228)
- `core/actions/lobby.py` — `LobbyFlow._plan_race_today()` (lines ~831–855)
- `core/agent.py` — `Player.run()` planned-race branch (lines ~348–405)
- `core/utils/date_uma.py` — add new helper near `parse_career_date()` (lines ~175–297)

## Test Plan
- **Unit:** Add tests covering the new date-confidence helper and guard logic permutations (confirmed first-junior day, artificial dates, stale skip flag).
- **Integration:** Run a scripted training session with a scheduled Satsuki Sho to verify the lobby transitions into `RaceFlow` and logs the structured decision payload.
- **UX / Visual (if applicable):** Review web UI `plannedRaces` workflow briefly to ensure no schema changes are required; confirm saved configs still align with the expected key format.

## Verification Checklist
- [ ] Lint and type checks pass locally
- [ ] Endpoint `/config` returns `200` with expected payload
- [ ] Logs contain no PII; metrics updated
- [ ] Feature flag toggled correctly (if applicable)

## Rollback / Mitigation
- Revert the guard logic changes in `core/actions/lobby.py` and the companion helper if regressions appear, then redeploy. Disable automated planned races temporarily by clearing `plannedRaces` in `config.json` while investigating.

## Open Questions (if needed)
- Should the skip reset attempt happen immediately, or should we require an explicit confirmation (e.g., `RaceFlow` callback) before retrying? Human: up to you
- Do we need telemetry on OCR confidence or confidence thresholds to justify the new helper heuristics, or is the existing `_date_artificial` flag sufficient? Human: Not sure, up to you
