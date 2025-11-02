# Event Dataset Workflow (Supports & Trainees)

This guide documents the reproducible flow for adding fresh events to the catalog. Follow the numbered steps in order—each depends on the previous one.

---

## 0. Prerequisites

- Chrome (or similar) with DevTools
- Local clone of this repo with Python + Node dependencies installed
- `datasets/events_full_html.txt` available for temporary HTML dumps
- (Optional) Scratch editor for validating JSON output

---

## 1. Collect HTML from GameTora

1. Open <https://gametora.com/umamusume/training-event-helper>.
2. Use the filters to select **all new supports** and **trainee variants** you want to add (you can multi-select).
3. Once the page renders the event cards, open **Developer Tools → Elements**.
4. Right-click the root container (search for `eventhelper` in the DOM), choose **Copy → Copy outerHTML**.
5. Paste the copied HTML into `datasets/events_full_html.txt`, overwriting previous contents.

> 💡 Tip: keep the page open until you confirm the scrape succeeded—recopying is faster than reselecting everything.

---

## 2. Run the scraper

From the repo root:

```bash
cd datasets
cls && python scrape_events.py --html-file events_full_html.txt --support-defaults "Nice Nature-SSR-WIT" --out supports_events.json --debug
```

- Replace `--support-defaults` with a comma-separated list that covers any new supports you expect in the scrape. The format is `"Name-Rarity-Attribute"`.
- `--debug` is optional but recommended while verifying new entities. Remove it once you are confident in the pipeline.

The script emits `supports_events.json`, containing every parsed support/trainee block, their options, and computed default preferences.

---

## 3. Validate and merge results

1. Open `supports_events.json` in your editor.
2. Spot-check each new entry:
   - Seasonal trainee names should retain suffixes like `(Summer)`.
   - `(Original)` variants are automatically normalized (suffix removed).
   - Range outcomes (e.g., energy `-5/-20`) should appear as separate outcomes in an option.
   - Ensure `default_preference` matches expectations.
3. Copy the **new** support/trainee objects into `datasets/in_game/events.json`. Keep the array sorted/grouped as desired.
4. Run `python -m json.tool datasets/in_game/events.json` (or your formatter of choice) to ensure valid JSON before committing.

---

## 4. Rebuild the catalog

From the project root:

```bash
python build_catalog.py
```

This regenerates the compressed catalog consumed by the runtime and web UI.

---

## 5. Rebuild the web assets

```bash
cd web
npm run build
```

The updated build will include the refreshed catalog for distribution.

---

## 6. Optional clean-up & QA

- If the new trainees have unique portraits, download them from their GameTora detail pages and place the images under `web/public/events/trainee/` using the naming pattern `<Name>_profile.png` (e.g., `Special Week (Summer)_profile.png`).
- Launch the bot or web UI locally to confirm the catalog surfaces the new events correctly.

---

## Reference / Troubleshooting

- Input HTML lives in `datasets/events_full_html.txt`; overwrite it each run.
- Parsed output is temporary in `datasets/supports_events.json`.
- Canonical dataset is `datasets/in_game/events.json`.
- If the scraper fails to parse an entity, rerun with `--debug` and inspect the console output for the relevant block.
- For additional automation helpers (e.g., GPT tools) see the historical notes in previous README revisions.
