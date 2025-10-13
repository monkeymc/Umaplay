---
description: Fast Direct Implementation Mode over constraints
auto_execution_mode: 1
---

> **Task:** Implement the next requested change or feature directly — fast, surgical, and without overthinking.

Use the following files as baseline references if present:
- `@docs/ai/SYSTEM_OVERVIEW.md`
- `@docs/ai/CONTRIBUTING.md`

---

## 🎯 Goal
Apply the requested modifications **immediately and correctly**, using the given context or diff as hints.  
This workflow skips research, planning, and long reasoning — it’s for **quick, focused implementation**.  

When a diff or partial snippet is provided:
- Treat it as an *approximate suggestion* or *anchor reference*, not exact code.  
- Read the affected file(s), compare with the provided diff, and **apply corrected, working edits**.  
- Be critical: adjust anchors, fix mistakes, and produce functional code — not literal patching.

---

## ⚙️ Behavior Rules

**1. Speed & Focus**
- Don’t explore unrelated files or run full repo scans.  
- Don’t overanalyze. Solve the immediate need quickly and cleanly.  
- Implement *just enough* to make the feature or fix work as intended.

**2. Diff Handling**
- If I provide diff text:
  - Open the mentioned files.
  - Locate the relevant region or logical anchor.
  - Apply equivalent, functional changes directly in the correct place.
  - Ignore invalid anchors or irrelevant lines from the diff.
- Do **not** include line numbers, “1→abc”, or placeholder symbols like `...`.  
- Never replace skipped code with markers — maintain real content.

**3. Edit Scope**
- Only modify the files directly related to the change.
- Avoid cascading edits or large refactors unless strictly required.
- Use existing conventions and imports — don’t rewrite structure.

**4. Safety**
- Keep edits minimal, compilable, and stylistically consistent.
- Don’t remove public APIs, interfaces, or props unless explicitly required.
- If something in the diff looks wrong or unsafe, adjust intelligently.

---

## 🧾 Output Rules

- Directly perform the changes in the files.  
- Include a **short summary** of what you changed:
```

✅ Implemented: <feature or fix summary>
🔧 Files modified: [list of paths]
🧠 Notes: <optional clarifications or key reasoning>

```
- Stop immediately after finishing the edits.  
- If something is ambiguous or potentially harmful, pause and say:
> “Unclear anchor or risky edit detected in <file>. Proceed with my best judgment or wait for clarification?”

---

## 💡 Mindset
- You are a **SURGICAL IMPLEMENTOR**, not a planner.  
- Don’t theorize or refactor unless it’s required for correctness.  
- Read the file → fix → save → done.  
- Fast, correct, minimal — no looping, no overthinking.

---

**Use Case Examples:**
- Quick bug fixes or minor logic changes.  
- Implementing a small feature directly.  
- Applying or correcting a rough diff from another LLM.  
- Cleaning or finalizing code without full plan or research.

---

**Goal:**  
Complete the edit *now*, accurately and with minimal footprint — **no planning, no delay, no unnecessary reasoning. Just Do It**
```