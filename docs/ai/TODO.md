# vNext TODO (Engineering Plan)

This document tracks actionable requirements for the next release. Items are grouped by module with acceptance criteria and code references to this repo.

## AgentNav + Team Trials

- **[Loop back-and-retry on missing expected button]**
  - Where: `core/actions/team_trials.py::TeamTrialsFlow.process_banners_screen()`, helpers in `core/utils/nav.py`.
  - Behavior:
    - During multi-click sequences, if after two advances/clicks the expected next-state button isn’t seen, press BACK and restart this Team Trials attempt.
    - Expected cues: after pre-start greens, expect `button_green` "RACE!" or an advance chain; during advances expect one of `button_advance`, `button_pink` ("RACE AGAIN"), or `button_white` "BACK" within a small timeout.
    - Add helper `nav.advance_sequence_with_backoff(...)` wrapping `advance_sequence_with_mid_taps()` with periodic checks and a back-and-retry path.
  - Acceptance:
    - When flow derails, we back out and retry instead of stalling. Max 2 retries per banner.

- **[Composite classification during multi-clicks]**
  - Where: `core/agent_nav.py::AgentNav.classify_nav_screen()`.
  - Rule: if we see `button_pink` + `button_advance` + `button_white` (text="BACK") over last two polls, classify `RaceSequenceScreen`.
  - Thresholds: default 0.50 each; store in an internal `_thr` map.
  - Acceptance:
    - New screen name "RaceSequenceScreen" returned when present; Team Trials loop uses this to avoid over-clicking and detect stuck states.

## Training Policy

- **[Top-3 priority gate for low-priority stats]**
  - Where: `core/actions/training_policy.py::decide_action_training()`.
  - Config: `general.advanced.lowPriorityStatMargin` (default 0.5).
  - Behavior:
    - If best SV tile is for a 4th/5th priority stat, only choose it when it exceeds the best top-3 SV by ≥ margin; otherwise prefer best among top-3.
  - Acceptance:
    - With small SV gap (<0.5), the decision stays within top-3 priorities unless top-3 has no allowed/risk-ok options.

## Races Dataset and Selection

- **[Dataset validation & dirt/deer, barrier field fixes]**
  - Data: `datasets/in_game/races.json`.
  - New script: `dev_utils/validate_races.py` to report (not auto-fix):
    - `surface` ∈ {Turf, Dirt, Varies} (detect typos like "Deer").
    - `distance_m` present/consistent with `distance_text`; flag accidental "barriers".
  - Acceptance:
    - Running the validator prints a concise report with JSON pointers for manual corrections.

- **[Duplicate race disambiguation with template match tie-breaker]**
  - Where: `core/actions/race.py::_pick_race_square()`.
  - Assets: `assets/races/templates/` + `index.json` map `raceName -> templatePath`.
  - Behavior:
    - When OCR/title scores are within ~0.03 among candidates, run OpenCV `matchTemplate` or pHash on a banner/title crop vs template and add a small bonus (+0.10) to best match.
  - Acceptance:
    - Improves selection for Japanese Derby vs Oaks/Hawks when both show; gracefully falls back if no template.


## YOLO Retraining (Navigation)

- **[Improve rainbow detection]**
  - Model: `models/uma_nav.pt` updated after adding more labeled rainbow samples and hard negatives.
  - Wire via `Settings.YOLO_WEIGHTS_NAV`.
  - Acceptance: better recall on WIT rainbow; fewer false positives.

## Strategy Plugin (User-Pluggable)

- **[Configurable strategy selector]**
  - Where: `core/actions/race.py::set_strategy()` and `core/agent.py` (preset extraction).
  - Config: `general.advanced.strategyPlugin` = "module.path:callable".
  - Behavior: import callable and get `"end"|"late"|"pace"|"front"` before clicking; fallback to preset if absent/errors.
  - Provide `plugins/strategy_example.py` as reference.

## Requirements File

- **[Refresh requirements.txt]**
  - Ensure: `opencv-python`, `imagehash`, `paddleocr`, `paddlepaddle` (CPU default), `rapidfuzz`, `Pillow`, `numpy`.
  - Note GPU caveats in README (Paddle/Torch env separation).

## Events: Auguri Cap Chain Step

- **[Default chain_step_hint to 1 when None]**
  - Where: `core/actions/events.py::process_event_screen()` when building `Query`.
  - Behavior: if `_count_chain_steps()` is None but an `event_card` is present, set `chain_step_hint=1`.
  - Acceptance: events with same title but different chain steps match correct `#s1` vs `#s2`.

## Config Keys (Samples + Settings)

- Add to `prefs/config.sample.json` and map in `core/settings.py::apply_config()`:
  - `general.advanced.skillCheckInterval` (int, default 3)
  - `general.advanced.skillPtsDelta` (int, default 60)
  - `general.advanced.lowPriorityStatMargin` (float, default 0.5)
  - `general.advanced.raceTemplateTiebreak` (bool, default true)
  - `general.advanced.strategyPlugin` (string, default empty)

## Tests

- **[Skills OCR]** `tests/test_text_normalization.py` for noisy "Groundwork", "Left‑Handed" cases.
- **[Training gate]** Add unit to prefer top-3 when 4th/5th advantage < margin.
- **[Events chain]** Simulate `chain_step_hint=None`, ensure default=1 improves retrieval.
- **[Race tie-breaker]** Optional harness under `dev_utils/` to score two candidates with/without templates.

## Implementation Order (suggested)

1. AgentNav/Team Trials loop safety + composite classification.
2. Skills interval optimization + config.
3. OCR domain fixes (skills).
4. Training policy gate.
5. Events chain bug.
6. Web UI distance.
7. Races DB validator + template tie-breaker.
8. Strategy plugin (+ sample).
9. YOLO retrain + model swap.
10. requirements.txt refresh.
