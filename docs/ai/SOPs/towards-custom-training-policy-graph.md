---
title: SOP – Canonical Training Policy Graph Deployment
date: 2025-10-11T18:24:00-05:00
version: 1.0.0
owner: Maintainers of `core/policy/`
applies_to: [core/actions, core/policy, web/policy-editor]
last_validated: 2025-10-11
related_prs: []
related_docs: []
risk_level: medium
---

# Purpose
Document how to regenerate, publish, and validate the canonical training-policy graph that mirrors `decide_action_training()` using the shared graph interpreter. Follow this when refreshing parity after logic updates or when syncing UI defaults with backend behavior.

# Scope & Preconditions
- Maintainable on developer workstations with Python >= 3.10, Node >= 18, and repo dependencies installed via `pip install -r requirements.txt` and `npm install` in `web/`.
- Requires write access to the repository and ability to run `pytest` and `npm` scripts.
- Impacts `core/actions/training_policy.py`, `core/policy/`, `web/src/constants/`, `web/src/models/`, and `web/src/store/`.
- Estimated time: 45–60 minutes including test and lint cycles.

# Inputs & Parameters
- **TrainAction enum**: defined in `core/actions/training_types.py`; no configuration required.
- **Policy graph version**: set in `DEFAULT_POLICY_VERSION` within `web/src/constants/canonicalPolicyGraph.ts` and reused via `policyDefaults()`.
- **Energy gates, SV thresholds**: pulled from `PolicyContext`; no additional runtime parameters.
- **Optional layout tuning**: node coordinates in `canonicalPolicyGraph.ts`; adjust as needed for UI clarity.

# Step-by-Step Procedure
1. Refresh backend graph source of truth.
   - **Files/paths:**
     - `core/policy/training_steps.py`: authoritative predicate order and decision helpers.
     - `core/policy/default_graph.py`: serializes `STEP_SEQUENCE` into a `PolicyGraph` structure.
   - **Per-file actions:**
     - Open `training_steps.py` and confirm `STEP_SEQUENCE` lists predicates in the exact execution order. When adding new predicates, update accompanying helper functions and the `_PREDICATE_DESCRIPTIONS` map in `default_graph.py` to avoid missing nodes.
     - Validate that every helper returns a `DecisionResult` with `TrainAction` drawn from `core/actions/training_types.py` and that predicates append meaningful `state.because(...)` strings for parity logging.
     - In `default_graph.py`, ensure the `chain = STEP_NODE_IDS + [FINAL_NODE_ID]` logic still covers every predicate from `STEP_SEQUENCE`. For structural changes (branching, additional actions), add explicit `PolicyNode` definitions rather than relying solely on the linear chain template.
   - **Commands:**
     ```bash
     # Ensure STEP_SEQUENCE exports the desired decision order
     python -m compileall core/policy/training_steps.py
     python -m compileall core/policy/default_graph.py
     ```
   - **Notes:** `DEFAULT_POLICY_GRAPH` must traverse predicates in `STEP_SEQUENCE` order and end with `final_noop` → `resolve_action`. Compilation catches syntax errors before downstream tooling consumes the modules.

2. Reconcile shared types to avoid circular imports.
   - **Files/paths:**
     - `core/actions/training_types.py`: canonical definition of `TrainAction`.
     - `core/policy/training_steps.py`, `core/policy/adapters.py`, `core/actions/training_policy.py`: consumers of the enum.
   - **Per-file actions:**
     - Confirm `TrainAction` contains all actions referenced in decision helpers (`TRAIN_WIT`, `TRAIN_MAX`, etc.). Extend the enum here first when adding new actions.
     - In `training_steps.py` and `adapters.py`, verify the import path is `from core.actions.training_types import TrainAction`. Remove any remaining imports from `training_policy.py` to break cycles.
     - Check `core/actions/training_policy.py` imports the enum from `training_types.py` and re-exports it only if necessary. Keep `decide_action_training()` focused on context construction to prevent new circular dependencies.
   - **Commands:**
     ```bash
     rg "TrainAction" core/actions core/policy -n
     ```
   - **Notes:** When linting fails due to duplicate import paths, prefer editing the consumer modules rather than reintroducing the enum to `training_policy.py`.

3. Expose canonical graph dict for interpreter adapters.
   - **Files/paths:**
     - `core/policy/default_graph.py`: exports `DEFAULT_POLICY_GRAPH` and `DEFAULT_POLICY_GRAPH_DICT`.
     - `core/policy/adapters.py`: wiring between graph interpreter predicates and backend helpers.
   - **Per-file actions:**
     - Ensure `default_graph.py` exports both the `PolicyGraph` object and its JSON-ready `dict` via `graph_to_dict()` for downstream serialization.
     - In `adapters.py`, import `DEFAULT_POLICY_GRAPH_DICT` and assign it as the fallback graph when user presets lack overrides. Confirm `_make_predicate()` covers every predicate id emitted by `STEP_SEQUENCE`.
     - Verify the adapter stores the `DecisionResult` (`state.store("decision_result", result)`) prior to `resolve_decision` execution so the final action node can emit the stored outcome.
   - **Commands:**
     ```bash
     python - <<'PY'
     from core.policy.default_graph import DEFAULT_POLICY_GRAPH_DICT
     assert "entry" in DEFAULT_POLICY_GRAPH_DICT
     assert isinstance(DEFAULT_POLICY_GRAPH_DICT["nodes"], dict)
     PY
     ```
   - **Notes:** Adapter should default to the new graph when external JSON is absent. Re-run unit tests if predicate ids change.

4. Provide reusable canonical graph to frontend consumers.
   - **Files/paths:** `web/src/constants/canonicalPolicyGraph.ts`
   - **Per-file actions:**
     - Maintain `DEFAULT_POLICY_VERSION` (string) and update when breaking schema changes are introduced.
     - Keep `predicateIds` synchronized with backend `STEP_SEQUENCE`; append new ids in order and adjust `conditionDescriptions` accordingly.
     - Adjust the `nodePosition()` helper or `predicate()` factory if the UI layout requires spacing tweaks; ensure nodes referenced by `on_false` exist.
   - **Commands:**
     ```bash
     npm --prefix web run lint constants/canonicalPolicyGraph.ts
     ```
   - **Notes:** Use deterministic layout helpers; keep `predicateIds` aligned with `STEP_SEQUENCE`.

5. Update schema defaults so presets ship with canonical graph.
   - **Files/paths:** `web/src/models/config.schema.ts`
   - **Per-file actions:**
     - Import `CANONICAL_POLICY_GRAPH` and `DEFAULT_POLICY_VERSION` via alias paths; confirm tsconfig paths resolve.
     - In `policyDefaults()`, deep-clone the canonical graph (`JSON.parse(JSON.stringify(...))`) to prevent store mutations from altering the shared constant.
     - Update `policySchema` defaults to match, so incoming configs missing `policy.graph` automatically hydrate with the canonical structure.
   - **Commands:**
     ```bash
     npm --prefix web run lint src/models/config.schema.ts
     ```
   - **Notes:** `policyDefaults()` must deep-clone `CANONICAL_POLICY_GRAPH`; avoid sharing references.

6. Align policy editor store and UI with canonical reset flow.
   - **Files/paths:** `web/src/store/policyEditorStore.ts`, `web/src/components/policy/PolicyEditor.tsx`
   - **Per-file actions:**
     - Replace the old `createMagodyGraph()` helper with `coerceGraphFromUnknown(CANONICAL_POLICY_GRAPH)` to guarantee consistent initialization. Remove the legacy node definitions entirely.
     - Rename store action to `resetGraphToCanonical` and propagate the new key to `PolicyEditorActions` type exports.
     - Update `loadFromPreset()` to fall back to the canonical graph when presets omit custom JSON.
     - In `PolicyEditor.tsx`, swap UI strings (“Reset to Canonical”) and ensure the handler sets the preset version using `policyDefaults().version`.
   - **Commands:**
     ```bash
     npm --prefix web run lint src/store/policyEditorStore.ts src/components/policy/PolicyEditor.tsx
     ```
   - **Notes:** Replace `resetGraphToMagody` with `resetGraphToCanonical`; ensure `PolicyEditorActions` pick reflects the new key.

7. Serialize graph output when persisting presets.
   - **Files/paths:** `web/src/store/policyEditorStore.ts`
   - **Commands:**
     ```bash
     npm --prefix web run test -- PolicyEditorStore
     ```
   - **Notes:** Ensure `preparePolicyPayload()` emits `DEFAULT_POLICY_VERSION` when input is empty.

8. Run backend and frontend verification suites.
   - **Files/paths:** `tests/policy/test_graph_parity.py`, `web/`
   - **Commands:**
     ```bash
     pytest tests/policy/test_graph_parity.py
     npm --prefix web run test
     ```
   - **Notes:** Confirm parity test passes and TypeScript builds cleanly.

9. Document and stage changes.
   - **Files/paths:** `docs/ai/SOPs/`, commit diff
   - **Commands:**
     ```bash
     git status
     git diff
     ```
   - **Notes:** Capture summary for release notes; ensure SOP references relevant files.

# Verification & Acceptance Criteria
- `pytest tests/policy/test_graph_parity.py` passes, confirming canonical graph parity with legacy rules.
- `npm --prefix web run lint` and `npm --prefix web run test` succeed, verifying TypeScript integrity.
- Loading policy editor in the web UI shows the canonical graph, and “Reset to Canonical” restores the expected nodes.
- Serialized presets contain `policy.version == DEFAULT_POLICY_VERSION` and embed the canonical graph structure.

# Observability
- **Logs:** Backend decisions emit via `core.utils.logger_uma`; check for predicate-step messages when running automation.
- **Metrics/dashboards:** Not applicable.
- **Alerts/traces:** Not applicable.

# Failure Modes & Recovery
- **TypeScript key mismatch → compile error:** Ensure `PolicyEditorActions` pick list matches store keys; rerun lint.
- **Canonical graph parse failure → runtime error:** Validate `CANONICAL_POLICY_GRAPH` with `parseGraphObject()`; ensure every node referenced by `on_true`/`on_false` exists.
- **Parity test regression → logic drift:** Recompare `STEP_SEQUENCE` vs. legacy flow; update canonical graph and training steps together, then rerun tests.
- **UI reset stuck → stale state:** Clear local storage for presets or reload page; confirm store initializes via `policyDefaults()`.

# Security & Compliance
- No secrets or PII involved; operations touch static configuration only.
- Standard repo write permissions suffice; no elevated RBAC required.
- Keep commit history auditable by referencing SOP in PR descriptions.

# Maintenance & Change Management
- Revalidate this SOP whenever `STEP_SEQUENCE` or `PolicyContext` fields change.
- Escalate issues to the maintainers of `core/policy/` and `web/src/store/` modules.
- Update `DEFAULT_POLICY_VERSION` when breaking changes alter node semantics or schema shape.

# References
- Code: `core/policy/default_graph.py`, `core/policy/training_steps.py`, `web/src/constants/canonicalPolicyGraph.ts`, `web/src/store/policyEditorStore.ts`, `web/src/models/config.schema.ts`, `web/src/components/policy/PolicyEditor.tsx`
- Tests: `tests/policy/test_graph_parity.py`
- Enums/Types: `core/actions/training_types.py`

# Open Questions
- Owner contact for canonical policy maintenance is undefined; coordinate with project leads to assign responsibility.
- Canonical node layout could benefit from UX validation; gather feedback from frontend maintainers.

# Change Log
- 2025-10-11 – v1.0.0 – Initial SOP for canonical training policy graph deployment; validated in local development environment.
