---
description: Adaptive System Overview Updater
auto_execution_mode: 3
---

> **Task:** Review and update `docs/ai/SYSTEM_OVERVIEW.md` so it accurately reflects the current repository architecture after recent work.

---

## 🎯 Goal
Keep the architecture overview continuously accurate and readable — updating only what’s necessary.

- If recent changes were minor (trivial refactors, variable renames, doc fixes):  
  → perform **light maintenance** (minor wording or path adjustments).  
- If the system structure changed significantly (new modules, deleted services, reorganized directories):  
  → perform a **partial regeneration** of affected sections, ensuring coherence and accuracy.  
- The output must always be **real**, **verifiable**, and **free of speculation**.

---

## ⚙️ Operating Rules

- **Truth-first:** Re-read and verify real files before making updates.  
- **No line numbers or anchors** — use only file paths, directories, and module names.  
- **Preserve what’s still valid**; don’t rewrite stable sections.  
- **Summarize large diffs** instead of pasting code.  
- **Keep format identical** to the structure defined in `/system-overview-plan`.  
- **If nothing changed**, explicitly confirm:  
  > “No updates required; SYSTEM_OVERVIEW.md remains valid.”  

---

## 🔍 Update Detection Method

1. **Scan recent signals**:
   - Git commits, diffs, or PRs since last SYSTEM_OVERVIEW update.
   - Added, deleted, or renamed files/folders.
   - Changes to build/deploy scripts, Dockerfiles, or CI workflows.
   - Modifications in configs or infra directories.
   - New apps, services, or components detected under `/src`, `/apps`, or `/packages`.

2. **Compare with SYSTEM_OVERVIEW**:
   - Identify references that are outdated (e.g., removed paths or renamed folders).
   - Detect missing new components not documented yet.
   - Spot stale descriptions or outdated dependency notes.

3. **Decide update level**:
   - **Minor Update:** File paths, names, or descriptions slightly changed.
   - **Moderate Update:** New modules or restructured directories.
   - **Major Update:** Core architecture shifted (new services, databases, queues, etc.).

---

## 🧠 Update Workflow (follow these steps)

### Step 1 — Assess Drift
**Goal:** Determine how much the repository diverged from what’s documented.  
**Sources:** `docs/ai/SYSTEM_OVERVIEW.md`, recent commits, top-level directory scan.  
**Output:** Summary of detected differences (added, changed, removed).  
**Validation:** Cross-check file existence.

### Step 2 — Select Update Mode
**Goal:** Decide update intensity.  
**Modes:**  
- `none` – No changes detected.  
- `light` – Minor corrections only.  
- `moderate` – Add or update relevant sections.  
- `major` – Rebuild sections per `/system-overview-plan`.

### Step 3 — Apply Updates
**Goal:** Edit SYSTEM_OVERVIEW.md to match current architecture.  
**Method:**  
- For **light/moderate**, modify in-place using unified diff format (preserving structure).  
- For **major**, regenerate affected sections (Services, Data, or Deployment) while keeping stable parts intact.  
**Validation:** Ensure Markdown structure remains valid; repository paths are real.

### Step 4 — Verify Consistency
**Goal:** Confirm internal coherence and correctness.  
**Method:**  
- Re-read updated sections and check consistency with the directory tree.  
- Verify all mentioned components or paths exist.  
**Output:** Short confirmation summary of what changed.

---

## 🧾 Output Requirements

- If updates are made:
  - Output a unified diff showing only changed sections of `docs/ai/SYSTEM_OVERVIEW.md`.  
  - Include a short summary like:
    > “Updated Services section — added `/src/worker/` and `/infra/ci/`. Adjusted Data & Deployment notes.”
- If no update is required:
  - Output:
    > “SYSTEM_OVERVIEW.md is up to date. No structural changes detected.”
- Always conclude with:
  > “Would you like me to run a full verification pass (re-read all sections) or keep this as incremental?”
- If there are sops in @docs/ai/SOPs folder, make sure they are also 'indexed' / referenced in system overview
---

## 🧩 Optional Helper Snippet (for drift detection)
You can use this directory map generator (up to 3 levels) to revalidate project layout:

```python
def print_directory_structure(root_dir, indent="", exclude_dirs=None, depth=0, max_depth=3):
    exclude_dirs = exclude_dirs or []
    if depth > max_depth:
        return
    for item in os.listdir(root_dir):
        path = os.path.join(root_dir, item)
        if os.path.isdir(path):
            if item in exclude_dirs:
                continue
            print(f"{indent}├── {item}/")
            print_directory_structure(path, indent + "│   ", exclude_dirs, depth + 1, max_depth)
        else:
            print(f"{indent}├── {item}")
```

---

## 🧾 Output Format

When updates are needed, produce:

```md
# SYSTEM_OVERVIEW Update Summary

## Update Mode
<none | light | moderate | major>

## Changes
- <summary of modified sections>
- <paths added or removed>
- <notes about external dependencies or data layers>

## Verification
- <short validation report>
```