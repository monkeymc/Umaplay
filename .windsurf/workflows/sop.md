---
description: Generate a Standard Operating Procedure
auto_execution_mode: 3
---

> **Task:** Generate a complete, team-ready Standard Operating Procedure (SOP) for the work implemented during this session.

The SOP must be factual, minimal, and reproducible — suitable for on-call, maintenance, or handoff scenarios.

---

## ⚙️ Core Principles
- **Truth-based:** Use only real data from the workspace (files, diffs, PRs).  
- **Compact:** Prefer short, precise bullets over paragraphs.  
- **Reproducible:** Include actual file paths, commands, and verified configuration.  
- **Auditable:** If any fact is missing, state it explicitly under *Open Questions*.  
- **Actionable:** Anyone with system access should be able to repeat and validate it end-to-end.

---

## 🔍 Sources to Consult (in priority order)
1. The most recent PR or commit range and its unified diff.  
2. All files that were created or modified, including tests and docs.  
3. Supporting documentation: `docs/ai/feature/progress.md`, `PLAN.md`, and `RESEARCH.md`.  
4. CI logs, run scripts, `Makefile`, `Taskfile`, `docker-compose.yml`, `Dockerfile`, package or lock files, and `.env` templates.

---

## 🧱 Output Format (Markdown Only)

Create the SOP exactly in the following structure and fill it with verified, concrete values.  
When possible, use absolute or repo-relative paths.  
When multiple services are affected, list them all under `applies_to`.

```md
---
title: SOP – <concise_operation_name>
date: <ISO_8601_with_timezone>
version: 1.0.0
owner: <team_or_contact>
applies_to: [<service_or_module_names>]
last_validated: <ISO_date>
related_prs: [<PR_numbers_or_links>]
related_docs: [<relative_doc_links>]
risk_level: low|medium|high
---

# Purpose
One paragraph describing what this SOP achieves and when to use it.

# Scope & Preconditions
- Environment(s) and required access (e.g., staging, prod)
- Feature flags, secrets, or data seeds required
- Systems/components impacted
- Estimated time to complete

# Inputs & Parameters
- Required inputs (env vars, CLI args, config keys)
- Optional parameters with defaults
- Where to configure them (paths or admin panels)

# Step-by-Step Procedure
1. <action>
   - **Files/paths:** `path/to/file.ext` (anchors if relevant)
   - **Commands:**
     ```bash
     # exact commands to execute
     ```
   - **Notes:** <idempotency, ordering, pitfalls>

2. <next_action>
   - **Files/paths:** …
   - **Commands:**
     ```bash
     ```
   - **Notes:** …

# Verification & Acceptance Criteria
- Steps or commands to verify success
- Expected outputs, status codes, or UI changes
- Post-conditions that must be true

# Observability
- Logs to monitor (include grep examples or logger names)
- Metrics/dashboards (exact URLs or panels)
- Alerts/traces relevant to this procedure

# Failure Modes & Recovery
- Common failures (symptom → cause → resolution)
- Safe retry guidance
- Rollback procedure (commands, reversibility notes)

# Security & Compliance
- Secrets or PII touched and proper handling
- Required approvals or RBAC notes
- Audit trail or ticketing references

# Maintenance & Change Management
- Periodic reviews or scheduled tasks (cron, tokens, thresholds)
- Ownership/escalation contacts
- How to update this SOP when behavior changes

# References
- PRs, design docs, ADRs, or related code sections
- Test files covering this functionality
- External documentation links

# Open Questions
- Unknowns or unverifiable items
- How to find the missing info (file path, command, contact)

# Change Log
- <ISO_date> – v1.0.0 – Initial SOP for <operation>; validated on <environment>.
```

---

## 🧩 Behavioral Rules

1. **No placeholders** — every section must use verified, real data or explicitly say “Not applicable.”
2. **If uncertain**, open and inspect the file, diff, or PR to confirm. Never guess.
3. **Link out** rather than embed long background details.
4. **Be minimal but complete** — just enough for a competent engineer to execute confidently.
5. **If the workspace lacks data** (e.g., no recent PR), include under *Open Questions*:

   * What is missing
   * How to locate or regenerate it (command, API, or path)

---

## 🧾 Output Requirements

* Return the SOP as Markdown only.
* Also write the SOP to `docs/ai/SOPs/<slug>.md` if the tool supports file output.

  * `<slug>` = kebab-case of the operation name (e.g., `quote-detail-refactor`).
* Ensure all links are relative (never absolute URLs to local machines).
* Keep total length concise (≤ 300 lines preferred).
