---
description: Prompt to do Planning over a specific problem we need to resolve
auto_execution_mode: 3
---

> **Task:** Generate a structured, step-by-step implementation PLAN.

Use:
- `docs/ai/feature/RESEARCH.md` as the research baseline (if present).
- If any contradiction exists between RESEARCH and the codebase, **actual source code takes priority**.

Your output is a **PLAN only** (no code). Steps are **general**, not per-file: a single step may modify multiple files, or just one. Do **not** include line numbers or exact anchors.

---

## OUTPUT (write to `docs/ai/feature/PLAN.md`)
```md
---
status: plan_ready
---

# PLAN

## Objectives
- <what will exist and how we’ll know it works>
- <key measurable outcomes or acceptance goals>

## Steps (general; not per-file)
### Step 1 — <title>
**Goal:** <what this step achieves>  
**Actions (high level):**
- <describe the change in terms of behavior/logic, not code>
- <mention modules/areas (e.g., “API layer”, “UI form”, “DB migration”)>
**Affected files (expected):**
- `path/to/file_a.ext`
- `path/to/file_b.ext`
**Quick validation:**
- <how to check success fast: test, CLI, UI action, log line>

### Step 2 — <title>
**Goal:** ...
**Actions (high level):**
- ...
**Affected files (expected):**
- ...
**Quick validation:**
- ...

### Step N — Finalization
**Goal:** Stabilize, verify, and close out.
**Actions (high level):**
- Lint/type-check/tests
- Cleanups (dead code, unused imports), docs touch-ups
**Quick validation:**
- All checks green; feature observable as intended

## Test Plan
- **Unit:** <cases>
- **Integration/E2E:** <flows>
- **UX/Visual (if applicable):** <checks or Storybook refs>

## Verification Checklist
- [ ] Lint and type checks pass locally
- [ ] Critical endpoint(s)/flows behave as expected
- [ ] No PII in logs; metrics/traces updated (if applicable)
- [ ] Feature flag toggles behave (if applicable)

## Rollback / Mitigation
- <how to revert safely: disable flag, revert commit, rollback DB change>

## Open Questions (if any)
- <clear questions or unknowns; where to confirm in the repo or runtime>
```

---

## CONSTRAINTS

* Do **not** generate code or diffs.
* Do **not** organize by file; **organize by steps**. Each step can touch multiple files.
* Do **not** include line numbers, ranges, or brittle anchors.
* If info is missing, list **precise questions**; do not guess.

---

## EXECUTION PROTOCOL (for later)

* The next workflow will implement **Step 1 only**. You must **not** merge steps or perform Step 2 work during Step 1.
* After returning the PLAN, **ask explicitly**:
  “Start with Step 1, or adjust the plan first?”
* Stop. Do **not** auto-continue into implementation.

