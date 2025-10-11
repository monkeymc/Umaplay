# vNext TODO (Engineering Plan)

- Make sure we have the same local storage for localhost and 127.0.0.1 in web ui when pressing 'save config set that duplication if needed, and by default if nothing loaded in a url try to look in the data of localhost, so we have the same'

RACES:
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

Minimal train
- Minimal tazuna recreation handling (no support_tazuna logic yet)
