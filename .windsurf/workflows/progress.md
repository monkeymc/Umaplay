---
description: Save Progress to continue later
auto_execution_mode: 1
---

> **Task:** Write or update `docs/ai/feature/progress.md` to capture the current project state.

Use this file to record what was achieved, what remains, and any open issues — so future workflows can resume seamlessly.

---

## 🧱 Output Format (Markdown)

Always overwrite or update `docs/ai/feature/progress.md` with this structure:

```md
---
status: in_progress
updated: <ISO_TIMESTAMP_WITH_TZ>
---

# PROGRESS — <feature or topic name>

## Context & Goal
<2–3 lines describing what this feature does and what it aims to achieve>

## Key Decisions
- <short statement of a design or implementation choice>
- <tradeoff, simplification, or dependency>

## Files & Anchors in Play
- `path/to/file_a.py` — lines 80–145 (handles validation)
- `path/to/component.tsx` — lines 30–90 (render logic)
- `path/to/utils.js` — lines 10–55 (helper methods)

## Work Completed in This Iteration
- <concise bullet: what was implemented, fixed, or verified>
- <summarize tests or validations performed>
(5–10 bullets max)

## Current Issue or Observation
- <describe any failing case, uncertainty, or blocker>
- Hypothesis: <what might be causing it or what to check next>

## Next Step
- <single, concrete action for `/continue` or `/implement` to perform next>
````

---

## ⚙️ Behavior Rules

**1. Preserve Prior Progress**

* If `docs/ai/feature/progress.md` already exists:

  * Keep all previous completed or noted items.
  * Append new entries or mark old ones as ✅ if resolved.
  * Never delete meaningful context or overwrite history.

**2. Compact & Reusable**

* Keep each section short and readable.
* Exclude logs, console output, or long JSON data.
* Use simple Markdown lists and clear phrasing.

**3. Clarity & Traceability**

* Always specify the **current iteration or step** being saved.
* If there are no current issues, explicitly write `None`.
* When all work is complete, update the YAML front matter to:
  `status: complete`.

---

## 🧩 Example Output

```md
---
status: in_progress
updated: 2025-10-10T22:20:00-05:00
---

# PROGRESS — Quote Detail Refactor

## Context & Goal
Improve quote detail rendering and pricing synchronization between frontend and backend.

## Key Decisions
- Validation occurs in backend; frontend only handles UI errors.
- Deferred currency conversion until final submission.

## Files & Anchors in Play
- `frontend/src/components/QuoteDetail.tsx` — lines 40–125
- `backend/quote/views.py` — lines 150–220

## Work Completed in This Iteration
- Implemented price propagation from backend response.
- Fixed missing currency field in schema.
