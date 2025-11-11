---
description: doc policy scenario diagrams
auto_execution_mode: 1
---

> **Task:**
> Explore the repository to infer scenario policies from source code and project notes, then update or create Mermaid flowcharts and notes under `docs\ai\policies\<scenario>\` (e.g., `unity_cup`, `ura`) so that the diagrams and notes accurately reflect the current logic.

---

## 🎯 Goal

Produce accurate, readable, and maintainable **Lobby** and **Training** flowcharts (`flow_lobby.mmd`, `flow_training.mmd`) plus a concise `notes.txt` that documents thresholds, gates, and tie-break rules. Prefer **small, safe edits** when the code evolved slightly; perform **full rewrites** only when logic materially changed. For **minor** findings, adjust wording and edge labels; for **major** changes, update nodes/branches and the thresholds legend, and record rationale in `notes.txt`.

---

## ⚙️ Operating Rules

* **Source of truth:** derive behavior from code, configs, and in-repo docs only.
* **Two viewpoints per scenario:**

  1. **Lobby** (pre-training turn screening: infirmary, mood, summer/race windows, schedule).
  2. **Training** (on the training screen: SV collection, caps, hints, director/pal, spirits/flames, WIT/REST/RACE gates, thresholds).
* **Mermaid style (parse-safe):**

  * ASCII only (no Unicode arrows/quotes). Use `<=`, `>=`, `%`, plain digits.
  * No ampersands in labels; write “and”.
  * Avoid parentheses inside node labels; fold into words.
  * Node IDs alphanumeric with underscores; short labels; keep decisions as diamonds.
  * End nodes with “then end turn” only when they truly end the turn.
* **Thresholds & vocabulary:**

  * Extract numeric gates (e.g., SV bins, energy %, mood levels) from code/constants.
  * Define **named bins** in `notes.txt` (e.g., `SV_high`, `SV_mid`, `SV_late`) and reflect them in the diagrams with explicit numbers.
  * Describe tie-break/priority guard succinctly in notes; keep edges short.
* **Validation & truth-checking:**

  * Cross-check each branch against code comments and conditionals.
  * Ensure each decision has complete outgoing paths, no orphan nodes, and consistent terminology across files.
* **Non-destructive edits:** preserve structure when possible; keep changelog context in the report, not in diagrams.

---

## 🔍 Update Detection Method

1. **Scan recent signals:**

   * Diff relevant code modules, policy helpers, and constants; read recent commits, TODOs, and comments related to policy/thresholds.
   * Inspect existing `flow_*.mmd` and `notes.txt` for drift (missing branches, outdated thresholds).
2. **Compare with reference:**

   * Map code branches → diagram nodes/edges; list mismatches (missing node, wrong threshold, renamed concept, reordered priority).
   * Check whether resource files for the target **scenario** exist; if not, mark as “new”.
3. **Decide update level:**

   * **Minor:** wording/labels, threshold number nudges, legend tweaks.
   * **Moderate:** add/remove a branch, update bins, add Director/Spirit or Race windows.
   * **Major:** rewrite significant sections, split/merge nodes, add new ladders or modes.

---

## 🧠 Workflow

### Step 1 — Assess

Define scenario (`<scenario>`), purpose (which files to touch), inputs (code, configs, current diagrams), expected outputs (two `.mmd` files + `notes.txt`), and validation (Mermaid parse sanity, branch coverage, threshold consistency).

### Step 2 — Select Mode

Choose **light / moderate / major** based on the number and impact of mismatches (see “Update Detection Method”). Prefer light when only text or constants changed; move to major if core policy flow diverged.

### Step 3 — Apply

* Update `flow_lobby.mmd`:

  * Include: **race day checks**, junior/debut gates, **goals** (G1, maiden, fans) if they affect decision, **infirmary/mood**, **summer proximity**, schedule/skip toggles, and the decision to enter training.
  * Summarize algorithms in natural language labels (no internal math).
* Update `flow_training.mmd`:

  * Start with snapshot → **SV computation and risk gate**.
  * **Caps & hint override**, **undertrained distribution** nudge, **SV bins** (high/mid/late), **Director** (color/window), **WIT** soft-skip rules, **spirits/flames** impact (white/blue + combo summary), **PAL/Reporter** cameo notes (if modeled), **energy** gates, **race fallback**, **final-season** rules (e.g., secure 600/1170/1200 targets).
* Update `notes.txt`:

  * Enumerate thresholds (SV bins, energy %, mood), tie-break/priority guard, distribution undertrain rule (threshold and gap logic), Director windows/colors, spirit/flame scoring and combos, summer logic, fast-mode differences, and any scenario-specific toggles.
* Keep diagrams parse-safe (see rules).

### Step 4 — Verify

* **Syntax sanity:** ensure each `.mmd` compiles in a strict Mermaid renderer; decisions have all exits; no dangling nodes.
* **Semantic checks:** thresholds in diagrams match `notes.txt` and code; naming is consistent across both flow files.
* **Completeness:** Lobby covers pre-checks and the jump to training; Training covers in-screen choices and terminal actions.

---

## 🧾 Output Requirements

* If updates occur:

  * Overwrite/create:

    * `docs\ai\policies\<scenario>\flow_lobby.mmd`
    * `docs\ai\policies\<scenario>\flow_training.mmd`
    * `docs\ai\policies\<scenario>\notes.txt`
  * Provide a **summary report** with update mode, changed files, and a concise change list (bullets). Include short before/after snippets for non-trivial edits.
* If no updates needed:

  * Output a brief report stating **no changes**, with the checks you performed and where each rule was validated in code.
* Conclude with an optional prompt proposing the next scenario/file to refresh.

---

## 🧾 Output Format

```md
# <scenario> Policy Diagrams Update Summary

## Update Mode
<none | light | moderate | major>

## Files
- docs\ai\policies\<scenario>\flow_lobby.mmd  — <created|updated|unchanged>
- docs\ai\policies\<scenario>\flow_training.mmd  — <created|updated|unchanged>
- docs\ai\policies\<scenario>\notes.txt  — <created|updated|unchanged>

## Changes
- <short bullet per change: what/why; thresholds, branches, labels>

## Verification
- Mermaid parse: <ok|failed> (tool or reasoning)
- Threshold consistency: <ok|notes>
- Branch coverage: <ok|notes>

## Next Suggested Action (optional)
- <e.g., refresh URA or add new scenario placeholders>
```


Here’s a compact, general-purpose rule set to keep Mermaid **flowcharts** safe and parser-friendly:

1. **Use plain ASCII text only.**
   Stick to basic letters, digits, spaces, and underscores. Avoid any non-ASCII or decorative characters.

2. **Keep node and edge labels simple.**
   Write brief, descriptive phrases using plain words. Do not include symbols, formulas, or coded syntax inside labels.

3. **Avoid punctuation that Mermaid might treat as syntax.**
   Skip parentheses, angle brackets, ampersands, semicolons, backticks, or other special marks in node titles or labels.

4. **Use one idea per label.**
   Instead of multi-line or combined statements, break complex logic into smaller connected nodes.

5. **Keep identifiers alphanumeric with underscores.**
   Node IDs should not include spaces, symbols, or punctuation.

6. **Maintain consistent direction and structure.**
   Declare the flow direction once (`TD`, `LR`, etc.) and ensure all nodes connect in a logical order.

7. **Separate comments clearly.**
   Place comments on their own lines starting with `%%` and never append them to flow statements.

8. **Use plain words for conditions.**
   Replace any mathematical or symbolic comparisons with descriptive text such as “if energy low” or “check threshold”.

9. **Avoid multi-line strings or escapes.**
   Keep each node label and arrow label on one line; use concise wording instead of manual line breaks.

10. **Close every open block or branch.**
    Make sure subgraphs and decision branches connect to valid endpoints.

Following these guidelines ensures your diagrams remain valid across all Mermaid versions and render consistently without syntax errors.

kept plain ASCII, short single-line labels, and clear newlines between every edge so Mermaid won’t glue lines together.