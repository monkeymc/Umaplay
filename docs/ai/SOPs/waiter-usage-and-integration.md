---
title: SOP – Waiter Usage and Integration
date: 2025-10-12T13:09:00-05:00
version: 1.0.0
owner: Not applicable
applies_to: [core/utils/waiter.py, core/agent.py, core/actions/]
last_validated: 2025-10-12
related_prs: []
related_docs: [docs/ai/SYSTEM_OVERVIEW.md]
risk_level: medium
---

# Purpose
Document how the unified `Waiter` in `core/utils/waiter.py` orchestrates detection-driven clicks and polling across gameplay flows. Use this SOP when adding automation that depends on YOLO detections, OCR disambiguation, or timed retries.

# Scope & Preconditions
- **Environments:** Local Windows runtime with Umamusume client (Steam or Android mirror) and repository checkout.
- **Access:** Ability to modify `core/` Python modules and run `python main.py`.
- **Dependencies:** YOLO detector weights configured in `Settings`, OCR backend available (Tesseract or Paddle), active `IController` implementation.
- **Estimated time:** 30–45 minutes to integrate or audit a new waiter usage.

# Inputs & Parameters
- **PollConfig** (`core/utils/waiter.py:23`)
  - `imgsz`, `conf`, `iou`: YOLO inference parameters (defaults mirror `Settings.YOLO_*`).
  - `poll_interval_s`, `timeout_s`: Poll cadence and overall wait budget.
  - `tag`: Log tag forwarded to detector.
- **Waiter.click_when()`** (`core/utils/waiter.py:67`)
  - Required `classes` tuple; optional `texts`, `prefer_bottom`, `timeout_s`, `clicks`, `allow_greedy_click`.
  - `forbid_texts` + `forbid_threshold` prevent misclicks via OCR.
- **Waiter.seen()`** (`core/utils/waiter.py:168`)
  - Single snapshot probe with optional `texts` OCR.
- **Waiter.try_click_once()`** (`core/utils/waiter.py:218`)
  - Non-polling variant for opportunistic clicks.
- **Utility wrappers** in `core/utils/nav.py`: `click_button_loop()`, `advance_sequence_with_mid_taps()`, `handle_shop_exchange_on_clock_row()` use shared waiter semantics.

# Step-by-Step Procedure
1. Instantiate shared waiter for a flow or agent.
   - **Files/paths:** `core/agent.py`, `core/agent_nav.py` constructor blocks.
   - **Commands:**
     ```bash
     # Example: start runtime after modifying waiter config
     python main.py
     ```
   - **Notes:** Reuse one `Waiter` per controller/OCR pair; propagate it into action flows to avoid duplicate YOLO sessions.

2. Configure flow-specific PollConfig overrides when behavior requires different thresholds.
   - **Files/paths:** `core/agent.py:47-55`, `core/agent_nav.py:39-47`, `core/actions/race.py` helpers.
   - **Commands:**
     ```python
     flow_waiter = Waiter(ctrl, ocr, yolo, PollConfig(timeout_s=6.0, poll_interval_s=0.4, tag="race_flow"))
     ```
   - **Notes:** Align `imgsz`, `conf`, `iou` with `Settings`; tighten `timeout_s` for fast loops to prevent blocking.

3. Use `click_when()` for deterministic navigation steps.
   - **Files/paths:** `core/actions/race.py:80-134`, `core/actions/lobby.py:1039-1254`, `core/actions/daily_race.py:43-258`, `core/actions/team_trials.py:64-349`, `core/actions/skills.py:133-437`.
   - **Commands:**
     ```python
     self.waiter.click_when(
         classes=("button_green",),
         texts=("RACE", "RACE!"),
         forbid_texts=("CANCEL",),
         prefer_bottom=True,
         timeout_s=2.0,
         tag="daily_race_next"
     )
     ```
   - **Notes:** Prefer `prefer_bottom=True` when multiple candidates align vertically (e.g., team trials banners). Use `forbid_texts` to block false positives.

4. Gate state transitions with `seen()` before expensive OCR or multi-click sequences.
   - **Files/paths:** `core/actions/race.py:95-133`, `core/agent_nav.py:93-157`.
   - **Commands:**
     ```python
     if self.waiter.seen(classes=("race_square",), tag="race_nav_probe"):
         return True
     ```
   - **Notes:** `seen()` performs a single detection call; use it to exit polling loops early or sanity-check popups.

5. Integrate waiter-aware utilities for repetitive sequences.
   - **Files/paths:** `core/utils/nav.py:60-285`.
   - **Commands:**
     ```python
     nav.click_button_loop(
         self.waiter,
         classes=("button_green",),
         tag_prefix="team_trials_prestart",
         max_clicks=2,
         forbid_texts=("CANCEL",),
     )
     ```
   - **Notes:** Utilities already respect waiter configuration; ensure shared waiter instance is passed through.

# Verification & Acceptance Criteria
- Run `python main.py` and confirm runtime logs show `[waiter]` tags without repeated timeouts during lobby, race, skills, and event flows.
- Validate `Waiter.seen()` probes by examining debug logs when entering races (`race_nav_seen_*`).
- Confirm new waiter call sites respect `forbid_texts` for high-risk buttons (OK/CANCEL pairs) by checking log statements.

# Observability
- Monitor console or file logs emitted via `logger_uma` with tag `[waiter]` (timeouts, OCR rejections, forbidden matches).
- Review YOLO capture artifacts under `debug/` if attacks are enabled to ensure bounding boxes align.
- For persistent issues, enable additional logging in `core/utils/waiter.py` around `_pick_by_text()` to inspect OCR outputs.

# Failure Modes & Recovery
- **Symptom:** Waiter times out (`[waiter] timeout` log). → **Cause:** Detection class missing or blocked by forbid rule. → **Resolution:** Adjust `classes`, relax `forbid_texts`, or increase `timeout_s`.
- **Symptom:** Wrong button clicked. → **Cause:** OCR threshold too low or `allow_greedy_click` True on ambiguous detections. → **Resolution:** Set `allow_greedy_click=False`, provide `texts` constraints, or raise `threshold`.
- **Symptom:** Loop stalls on popup with overlapping options. → **Cause:** `prefer_bottom` not set when vertical choices overlap. → **Resolution:** Enable `prefer_bottom=True` or add `texts` disambiguation.

# Security & Compliance
- Waiter manipulates on-screen UI only; no secrets or PII processed.
- Ensure OCR engines respect local privacy requirements; no external network calls are made by default.

# Maintenance & Change Management
- When updating YOLO class names or models, revise waiter call sites to reference new `classes` strings.
- Review `core/utils/waiter.py` whenever OCR provider changes (e.g., new `OCRInterface` contract).
- Escalation: route issues through project maintainers listed in repository README; update this SOP after major flow refactors.

# References
- `core/utils/waiter.py`
- `core/agent.py`
- `core/agent_nav.py`
- `core/actions/race.py`
- `core/actions/lobby.py`
- `core/actions/daily_race.py`
- `core/actions/team_trials.py`
- `core/actions/skills.py`
- `core/utils/nav.py`
- `docs/ai/SYSTEM_OVERVIEW.md`

# Open Questions
- None.

# Change Log
- 2025-10-12 – v1.0.0 – Initial SOP for Waiter Usage and Integration; validated on local Windows runtime.
