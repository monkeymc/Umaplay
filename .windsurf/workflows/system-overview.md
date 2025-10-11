---
description: Generate a comprehensive architecture overview of this repository
auto_execution_mode: 3
---

> **Task:** Create a structured, multi-step PLAN to generate or update the repository’s architecture documentation in `docs/ai/SYSTEM_OVERVIEW.md`.

---

## 🎯 Goal
Design a precise, incremental plan for building or refreshing a complete architecture overview of the system — showing how everything fits together **end-to-end**.  
The plan will then be executed step by step when I say **“continue.”**

The final generated document must:
- Be **accurate** (real paths, verified components)
- Be **maintainable** (no line numbers or volatile details)
- Be **human-readable** (clear, structured, useful for onboarding)
- Live in `docs/ai/SYSTEM_OVERVIEW.md` as a single file

---

## ⚙️ Operating Rules

- **Truth-first:** Always verify by reading real files; never invent structure, services, or paths.  
- **No speculation:** If something can’t be confirmed, mark it as *pending verification* for later steps.  
- **Granularity:** Use real **file paths**, module names, and folders — but **no line numbers or anchors**.  
- **Context control:** Keep context usage efficient (≤ 40%) by summarizing instead of expanding large codebases.  
- **Noise filtering:** Ignore non-architectural folders like:
```

.git, node_modules, .next, dist, build, **pycache**,
.pytest_cache, .ruff_cache, migrations, temp, dev_utils,
.terraform, terraform, .github, frontend-websockets-test

```
- **Format discipline:** Use Markdown lists, tables, and diagrams-as-text where helpful; no code dumps.  
- **Evolution-safe:** The overview should remain valid even as file line numbers or small configs change.  

---

## 🧠 Step Planning Guidelines

When constructing the PLAN, organize the work in **5–8 sequential steps** that progressively build the SYSTEM_OVERVIEW.  
Each step should have:

- **Goal:** What to accomplish in this step.  
- **Sources:** Which files or directories to analyze.  
- **Method:** How to extract or infer architecture information.  
- **Output:** What section(s) of the SYSTEM_OVERVIEW it will produce or update.  
- **Validation:** How to confirm correctness (file evidence or internal consistency).  

When you output the PLAN:
1. Do **not** yet produce the final document.  
2. Ensure each step can be executed independently and incrementally.  
3. Ensure coverage across:
 - High-level project purpose
 - Module/directory structure
 - Services/apps/components
 - Data & persistence
 - Cross-cutting concerns
 - Deployment and environments
 - Performance, security, and risks
 - Open questions / source references  

---

## 🧾 Final Document Target Structure

The completed `docs/ai/SYSTEM_OVERVIEW.md` will follow this layout (for reference only; do not generate yet):

```md
---
date: <ISO 8601 with timezone>
status: complete
repository: <repo name>
default_branch: <branch>
current_branch: <branch>
git_commit: <short SHA>
tags: [architecture, overview]
---

# System Overview
Brief paragraph summarizing what the system does and its overall design.

## Directory Map
Concise tree (2–3 levels) showing services, packages, and major components.

## SOPs.
<If there are sops in @docs/ai/SOPs folder, make sure they are also 'indexed' / referenced in system overview>

## Runtime Topology (diagram as text)
Service ↔ DB, API ↔ Worker, etc.

## Services / Apps
### <Service or Component Name>
- Purpose
- Entrypoints (file paths only)
- Public interfaces (HTTP, CLI, queues, etc.)
- Key internal dependencies
- External dependencies / SDKs / APIs
- Data and configuration locations
- Observability (logs, metrics, traces)
- Testing coverage notes

## Data & Persistence
Databases, ORMs, caches, queues, migration paths.

## External Integrations
Third-party systems, auth providers, payment APIs, messaging.

## Cross-Cutting Concerns
Authentication, configuration, logging, metrics, feature flags, security.

## Frontend Architecture (if present)
Routing, state management, design system, styling, build output.

## Environments & Deployment
CI/CD, containerization, environments, config layering.

## Performance & Reliability
Hot paths, concurrency, caching, scaling strategies.

## Risks & Hotspots
Modules that are brittle, complex, or overdue for refactor.

## Related Docs
READMEs, ADRs, SOPs, diagrams, or infra references.

## Open Questions
Explicit unknowns or pending confirmations.

## Source References
Concrete files and directories consulted for this document.
```

---

## 🪜 Expected PLAN Output Format

The model must output the **PLAN** in this format:

```md
# PLAN — System Overview Generation

## Step 1: <title>
**Goal:** <brief purpose>  
**Sources:** <paths or files to inspect>  
**Method:** <how to extract info>  
**Output:** <target section(s) of SYSTEM_OVERVIEW.md>  
**Validation:** <how to check accuracy>

## Step 2: ...
...
## Step N: Final Review & Assembly
**Goal:** Validate coherence and completeness of all sections.  
**Sources:** SYSTEM_OVERVIEW draft, progress files, or diffs.  
**Method:** Merge, normalize, and finalize Markdown.  
**Output:** Complete `docs/ai/SYSTEM_OVERVIEW.md`.  
**Validation:** Consistency across services, paths, and terminology.
```

---

## 🧾 Output Requirements

* Return only the **PLAN**, not the final overview.
* Ensure each step is actionable and can be executed incrementally when I later say “continue.”
* Make the PLAN general enough to apply on future updates — not just one-time generation.
* Mention when a step can safely be reused (e.g., “Step 1 can be repeated when adding a new service”).

---