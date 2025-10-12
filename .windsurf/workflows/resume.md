---
description: Restore the conversation in fresh chat
auto_execution_mode: 1
---

> **Task:** Restore the previous workflow context from documentation and immediately resume the next pending implementation step.

---

## 🎯 Purpose
Rebuild full context from the feature’s documentation and progress logs, identify the next actionable step, and continue implementation automatically — without waiting for user confirmation.

---

## 🧠 Steps

1. Read and interpret the following files if they exist:
   - `docs/ai/feature/progress.md` — summarize completed work and pending subtasks.  
   - `docs/ai/feature/PLAN.md` — extract step list, goals, and files under “Changes by File”.  
   - `docs/ai/feature/RESEARCH.md` — optional background or rationale for design decisions.  

2. Determine:
   - What feature or task this workflow sequence belongs to.  
   - Which steps are already done (based on `progress.md`).  
   - Which step should come next (the next incomplete step in `PLAN.md`).  
   - Which files are involved and what needs to be edited or created.  

3. Summarize context internally (no long prose output).  
   Then **immediately start implementation** of the next pending step following all implementation rules from the `/implement` workflow:
   - Modify only relevant files.  
   - No exploration outside the plan.  
   - Keep edits minimal, correct, and aligned with `PLAN.md`.  
   - Stop after finishing the current step.

4. After finishing the step, output:
```

✅ Resumed and completed Step <N>: <short summary of what was done>
🔧 Files modified: [list of paths]
🧠 Next step pending: <step or section name from PLAN.md>

```
Then ask:
> “Continue with Step <N+1> from PLAN.md, or pause here?”

---

## ⚙️ Behavioral Rules

- Do not output the full summaries of the docs; read and act.  
- Start editing directly after determining the next step.  
- If any referenced file is missing, create it following project conventions.  
- If context is inconsistent (e.g., progress ahead of plan), correct alignment logically and note it briefly before resuming.  
- Never regenerate the full PLAN; only execute the next defined step.  
- Stop after completing one logical step — no auto-chaining multiple steps.

---

**Goal:**  
Automatically restore workflow state, identify the next step, and continue implementation seamlessly — without rehashing context or waiting for confirmation.
