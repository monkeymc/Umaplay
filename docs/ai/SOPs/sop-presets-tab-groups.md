---
title: SOP – Preset Tab Groups (Chrome-like UI)
date: 2025-11-14T22:23:00-05:00
version: 1.0.0
owner: Umaplay team
applies_to: [web-presets-ui, web-config-store]
last_validated: 2025-11-14
related_prs: []
related_docs: [docs/ai/features/better-presets-management/RESEARCH.md, docs/ai/features/better-presets-management/PLAN.md]
risk_level: low
---

# Purpose
Describe how to use and maintain the **preset tab grouping UI** in the Web config (Chrome-like groups with colors, collapse, and drag-and-drop) so users and maintainers know how it behaves and how to debug it.

# Scope & Preconditions
- Applies to the React Web UI served by the FastAPI config server at `/`.
- Affects **preset management** for URA and Unity Cup:
  - `web/src/components/presets/PresetsTabs.tsx`
  - `web/src/store/configStore.ts`
  - `web/src/models/config.schema.ts`
- Requires the config UI to be reachable (bot running or config server started).
- No special feature flags; grouping is always available once the UI loads.
- Estimated time: 5–10 minutes to learn and verify behavior.

# Inputs & Parameters
- **Preset data:**
  - Stored in `prefs/config.json` under `scenarios[scenarioKey].presets`.
  - Each preset may optionally have `group: string | null`.
- **Scenarios:** `general.activeScenario` (either `ura` or `unity_cup`).
- **User actions:** mouse (right-click, drag), keyboard (typing group names, Enter to apply).

# Step-by-Step Procedure

1. Open the presets tab groups UI
   - **Files/paths:**
     - `web/src/components/presets/PresetsShell.tsx`
     - `web/src/components/presets/PresetsTabs.tsx`
   - **Commands:**
     ```bash
     # From repo root
     python main.py  # starts bot + config server, then open http://127.0.0.1:8000
     ```
   - **Notes:**
     - Navigate to the **Presets** section in the Web UI (Home → Presets tab).
     - Ensure you have at least one preset for the active scenario.

2. Create a new group via right-click
   - **Files/paths:** `web/src/components/presets/PresetsTabs.tsx` (tab context menu, group menu)
   - **Steps:**
     1. Right-click any preset tab.
     2. In the popup menu, use the **"Group name"** field.
        - Type a new name (e.g., `Speed`, `Unity Scores`).
        - Press **Enter** or click **"Apply name"**.
     3. The selected preset now belongs to that group; a **colored group chip** appears above the tabs.
   - **Notes:**
     - Group colors are deterministic: the first group gets the first color in `GROUP_COLORS`, and so on.
     - Renaming a group updates **all presets** that belonged to the old name.

3. Add presets to an existing group via drag-and-drop
   - **Files/paths:** `web/src/components/presets/PresetsTabs.tsx` (`handleDropOnGroup`, `handleDropOnTab`)
   - **Steps:**
     1. Ensure at least one group chip is visible (e.g., `Speed`).
     2. Click and drag another preset tab.
     3. Drop it onto the desired **group chip**.
     4. The tab’s underline color matches the group, and it is now considered part of that group.
   - **Notes:**
     - Dragging a tab over **linked group chips** will show the drop cursor; release to assign.
     - This mirrors Chrome’s "drag tab into group" behavior.

4. Reorder tabs via drag-and-drop
   - **Files/paths:** `web/src/components/presets/PresetsTabs.tsx` (`handleDropOnTab`, `reorderPresets`), `web/src/store/configStore.ts` (`reorderPresets`)
   - **Steps:**
     1. Click and drag a tab within the preset strip.
     2. Drop it before or after another tab.
     3. The order updates immediately and is stored via the `reorderPresets` action in the config store.
   - **Notes:**
     - Ordering is **per scenario**; URA and Unity Cup maintain separate lists.
     - Order persists in `prefs/config.json` and browser localStorage.

5. Collapse and expand groups
   - **Files/paths:** `web/src/components/presets/PresetsTabs.tsx` (`collapsedGroups` state, `toggleGroupCollapse`)
   - **Steps:**
     1. Click a group chip (e.g., `Speed`).
     2. The chip toggles between `▼` (expanded) and `▶` (collapsed).
     3. When collapsed, tabs in that group are hidden from the strip **except** the currently selected one.
   - **Notes:**
     - Collapsing helps when many presets exist; use it like Chrome’s group collapse.

6. Ungroup presets and use the Ungrouped bucket
   - **Files/paths:** `web/src/components/presets/PresetsTabs.tsx` (Ungrouped chip; `handleDropOnGroup` with `null`, `setPresetGroup`)
   - **Steps:**
     1. Drag a grouped tab onto the **Ungrouped** chip → preset’s `group` becomes `null`.
     2. Alternatively, select a preset and manually set its group to empty via the group popup (rename to empty string) to clear the group name for that cluster.
   - **Notes:**
     - Ungrouped presets have no color underline.
     - The Ungrouped pill stays visible as a drop target and can be highlighted by clicking (UX affordance only).

7. Rename or delete groups
   - **Files/paths:** `web/src/components/presets/PresetsTabs.tsx` (`renamePresetGroup`, `deletePresetGroup`), `web/src/store/configStore.ts`
   - **Steps:**
     1. Right-click any tab **inside** the target group.
     2. In the popup, edit **Group name** and click **Apply name**:
        - Non-empty new name → `renamePresetGroup(oldName, newName)`; all presets with the old group are updated.
        - Clearing the name and applying → `deletePresetGroup(groupName)`; all presets become ungrouped.
   - **Notes:**
     - This works per scenario; URA and Unity Cup groups are independent.

8. Explain the UX to users (what to tell them)
   - **Files/paths:** `web/src/components/presets/PresetsTabs.tsx` (hint Typography)
   - **Key points to communicate:**
     - "Right-click a tab to create or rename groups."
     - "Drag tabs between groups or onto 'Ungrouped' to reorganize."
     - Group chips are clickable headers that collapse/expand each cluster.

# Verification & Acceptance Criteria
- After grouping and reordering:
  - Tabs show colored underlines that match their group chips.
  - Collapsing/expanding groups only hides/shows tabs, not their data.
  - Ungrouping a tab removes its group color and sets `group` to `null` in the config.
- Exported `config.json` includes `group` fields where expected and still loads correctly via the Web UI.
- Reloading the page preserves grouping, ordering, and active preset selection per scenario.

# Rollback & Failure Modes
- **Rollback:**
  - If grouping UX misbehaves, you can temporarily disable it by reverting `PresetsTabs.tsx` and `configStore.ts` to a known-good commit; data in `config.json` remains valid because `group` is optional.
- **Common issues:**
  - *Tabs not draggable:* ensure the browser isn’t intercepting drag events (extensions, devtools detachments).
  - *Groups lost after reload:* verify `saveLocal`/`loadLocal` in `configStore` and ensure localStorage isn’t blocked.
  - *Unexpected grouping after importing configs:* check for `group` fields inside the imported JSON; remove or normalize as needed.

# Open Questions
- Should groups eventually support per-group color customization (like Chrome’s palette) via the UI?
- Do we want keyboard shortcuts for moving tabs between groups, or keep grouping mouse-only?
