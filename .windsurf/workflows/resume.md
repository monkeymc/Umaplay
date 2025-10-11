---
description: Restore the conversation in fresh chat
auto_execution_mode: 1
---

> **Task:** Restore the previous workflow context from documentation and prepare to continue implementation.

---

## 🎯 Purpose
Rebuild understanding of what has been done and what remains, so the next call to `/continue` can resume from the correct step.

---

## 🧠 Steps

1. Read the following files if they exist:
   - `docs/ai/feature/progress.md` — summarize current progress or partial completions.  
   - `docs/ai/feature/PLAN.md` — identify the defined steps, file list, and pending items.  
   - `docs/ai/feature/RESEARCH.md` — optional background or rationale.  

2. Summarize the recovered context:
   - What feature or task this workflow sequence addresses.  
   - Which steps have already been completed.  
   - Which step should come next according to PLAN.md.

3. Output a concise status summary:

