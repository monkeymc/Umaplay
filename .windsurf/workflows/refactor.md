---
description: Plan Generation for Targeted Refactor
auto_execution_mode: 1
---

> **Task:** Design a detailed, incremental plan to refactor one or more files in this repository.

---

## 🎯 Goal
Create a safe, structured plan for refactoring — improving maintainability, readability, or design — while preserving existing behavior.

This workflow produces **only the plan**.  
After reviewing it, I will reply **“continue”** to begin execution step by step.

---

## ⚙️ Operating Rules

- **No code yet:** Only describe the refactor plan, not the implementation.  
- **Incremental execution:** Each step should be small, verifiable, and reversible.  
- **Accuracy:** Use real file paths; do not guess structure or invent modules.
- **Behavioral safety:** The refactor must not change external behavior unless explicitly requested.  
- **Readability & structure:** Favor simplification, modularization, or consistency improvements.  
- **Verification checkpoints:** Every step must have a quick test or validation hint.

---

## 🧠 Plan Construction Guidelines

When building the plan:

1. **Understand the context:**  
   - What the file(s) currently do.  
   - Why a refactor is needed (complexity, duplication, naming, modularity, style).  
   - Any relevant dependencies, components, or configs.

2. **Identify affected areas:**  
   - List the target files and any supporting files (helpers, configs, tests).  
   - Use Python-style lists for clarity, for example:
     ```python
     TARGET_FILES = ["src/core/actions/lobby.py"]
     EXTRA_REFERENCE_FILES = ["src/core/utils/session_manager.py", "tests/test_lobby_flow.py"]
     ```

3. **Define clear goals:**  
   - What you want to improve (structure, abstraction, readability, performance, testability).  
   - What must remain unchanged (behavior, API surface, output, etc.).

4. **Break the plan into minimal steps:**  
   - Typically 3–6 steps depending on scope (not more than needed).  
   - Each step should include:
     - **Goal:** The intent of the change.  
     - **Actions:** What to modify or move.  
     - **Validation:** How to confirm it works (lint, test, or output check).  

5. **Design for review:**  
   - After each step, ask explicitly:
     > “Step X complete. Continue with the next step, or make adjustments before proceeding?”  
   - Stop immediately if feedback is needed or errors appear.

---

## 🧾 Expected PLAN Output Format

The output of this prompt must be the **refactor plan only**, structured like this:

```md
# PLAN — Refactor Strategy

## Target Files
TARGET_FILES = ["path/to/main/file.ext", "path/to/other/file.ext"]
EXTRA_REFERENCE_FILES = ["path/to/supporting/file.ext"]

## Overview
<Brief description of why this refactor is needed and what it aims to improve.>

## Step 1 — <Title>
**Goal:** <What this step accomplishes>  
**Actions:**  
- <specific edits or reorganizations to perform>  
- <modules/functions/classes to review>  
**Validation:** <How to test or confirm success quickly>

## Step 2 — <Title>
**Goal:** ...  
**Actions:** ...  
**Validation:** ...

## Step N — Final Cleanup & Verification
**Goal:** Validate that everything still works as expected after refactor.  
**Actions:**  
- Run lint/tests/CI commands  
- Remove unused imports or deprecated code  
**Validation:**  
- All tests pass; no regressions detected.
```

---

## 🧱 Guardrails

* Never remove functionality unless explicitly mentioned.
* Avoid renaming public APIs, exported components, or environment variables without explicit confirmation.
* Maintain consistent logging, error handling, and style conventions.
* If something is ambiguous (e.g., purpose of a class or function), flag it in the plan under “Clarifications Needed.”

---

## 🧾 Output Requirements

* Output only the **PLAN** — no diffs or code blocks yet.
* Ensure every step can be executed independently and validated quickly.
* Keep total steps ≤ 6; only expand if absolutely necessary.

---
