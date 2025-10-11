# vNext TODO (Engineering Plan)

This document tracks actionable requirements for the next release. Items are grouped by module with acceptance criteria and code references to this repo.




## Races Dataset and Selection

- Make sure we have the same local storage for localhost and 127.0.0.1 in web ui when pressing 'save config set that duplication if needed, and by default if nothing loaded in a url try to look in the data of localhost, so we have the same'

- Train with Tazuna icon in training it is not detecting saved some samples in android folder. Is detected as director even if no support_director is there, weird error. No, it is detectes as director:
[{'tile_idx': 4, 'tile_xyxy': (...), 'tile_center_x': 359.2553405761719, 'supports': [...], 'has_any_rainbow': False, 'failure_pct': 0, 'skipped_click': True}, {'tile_idx': 0, 'tile_xyxy': (...), 'tile_center_x': 61.63492298126221, 'supports': [...], 'has_any_rainbow': True, 'failure_pct': 0, 'skipped_click': False}]

- Option in UI to 'force' the recreations with tazuna / give more priority


- Train to be able to detect suppont_tazuna for recreations, also the 'chain' stuff there. also 'Recreation row' class

- **Custom policy for training**
  - Important yolo train with: D:\GitHub\UmAutoplay\temp\android\s
it is not recognicing some support cards

- **[Tazuna training]** if support_tazuna is there, add +0.15 (orange, yellow, max). Or pal in general in support type
  
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
