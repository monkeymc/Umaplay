# vNext TODO (Engineering Plan)

This document tracks actionable requirements for the next release. Items are grouped by module with acceptance criteria and code references to this repo.

## AgentNav + Team Trials

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

## Policy Plugin (User-Pluggable)



## Events: Auguri Cap Chain Step

- **[Default chain_step_hint to 1 when None]**
  - Where: `core/actions/events.py::process_event_screen()` when building `Query`.
  - Behavior: if `_count_chain_steps()` is None but an `event_card` is present, set `chain_step_hint=1`.
  - Acceptance: events with same title but different chain steps match correct `#s1` vs `#s2`.

