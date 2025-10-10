---
description: Continue with next steps of the implementation
auto_execution_mode: 1
---

> **Task:** Continue with the next step defined in `docs/ai/feature/PLAN.md`, using the existing context and previous history if available.

---

## 🎯 Purpose
Proceed to the **next implementation step** from the PLAN, following the same rules and scope defined in that document.

---

## ⚙️ Behavior

1. Read `docs/ai/feature/PLAN.md` and locate the step that comes **immediately after the last completed one**.  
   - If the plan has no explicit numbering, treat each bullet or file section under “Changes by File” as sequential steps.  
2. Confirm which step is next before applying any change.  
3. Output a brief summary:  
   - `Goal: <what this step will implement or verify>`  
4. Generate the corresponding diff patch following strict editing rules:  
   - Raw diff format, **no backticks**, **no markdown fences**, **≥3 real context lines**, and **only modify files listed in PLAN.md**.  
5. After the patch, stop and ask:

   > “Step <N> complete. Continue with the next step from PLAN.md, or adjust before proceeding?”

---

## 🧱 Rules
- Only modify the files explicitly mentioned in PLAN.md.  
- If a required change affects a non-listed file, **stop** and produce a short *Plan Update Proposal* explaining why.  
- Do not open or analyze the entire repository.  
- If a conflict arises between PLAN.md and the source code, **source wins** — make minimal corrections.  
- If all steps are already complete, state clearly:  
  > “All steps in PLAN.md are complete. Do you want to review or finalize?”

---

**Goal:** Execute the next planned step with precision, using prior context when available, and pause for explicit confirmation before continuing further.
