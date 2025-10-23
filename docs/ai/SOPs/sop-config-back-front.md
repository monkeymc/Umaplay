---
title: SOP – Manage Frontend-Backend Config Changes
date: 2025-10-06T21:49:08-05:00
version: 1.0.0
owner: Umaplay maintainers
applies_to: [web-ui, schema, config-store, backend-settings]
last_validated: 2025-10-06
related_prs: []
related_docs: [docs/ai/SYSTEM_OVERVIEW.md, web/README.md]
risk_level: medium
---

# Purpose
This SOP provides a template for making configuration changes that span frontend and backend, including schema updates, data migration, and backward compatibility. Use this when adding, removing, or modifying configuration options that need to be synchronized between UI and backend services. The Daily Races preferences tab (`web/src/components/nav/DailyRacePrefs.tsx`) is the reference implementation: Zustand writes to `/nav` via FastAPI, while the scenario tab stays mounted to avoid reloading datasets when switching.

> **Example**: This was used to move `prioritizeHint` from General to Preset config while maintaining backward compatibility.

# Scope & Preconditions
- **Preconditions**
  - Node.js and npm for web UI; Python 3.10+ for backend.
  - Local repo with latest changes.
  - Understanding of the config structure (General vs. Preset).
- **Systems/components affected**
  - Web UI: types, schema, store, and relevant UI components (including nav preference stores when Daily Races toggles change).
  - Backend: settings mapping and any consumers of those settings.
  - Configuration import/export functionality.
  - Optional remote services that consume the same settings (e.g., template matching when OpenCV is unavailable locally).
- **Estimated time**
  - 15–30 minutes per config change, depending on complexity.

# Inputs & Parameters
- **New config structure**
  - `presets[].newSetting: type` (new per-preset setting)
  - Example: `presets[].prioritizeHint: boolean`
- **Legacy structure (if migrating)**
  - `general.oldSetting: type` (to be deprecated but still supported)
  - Example: `general.prioritizeHint: boolean`
- **Related settings**
  - List any settings that interact with or depend on this change
  - Example: `presets[].raceIfNoGoodValue: boolean`
- **Configuration locations**
  - UI: Path to relevant component (e.g., `web/src/components/presets/PresetPanel.tsx`)
  - Schema: `web/src/models/config.schema.ts`
  - Store: `web/src/store/configStore.ts`
  - Backend: `core/settings.py`
  - Reference: `prefs/config.sample.json`

# Step-by-Step Procedure

## 1. Update Types and Schema
- **Files to modify**:
  - `web/src/models/types.ts` - Update TypeScript interfaces
  - `web/src/models/config.schema.ts` - Update Zod schemas
- **Steps**:
  - Add/remove fields from relevant interfaces (`GeneralConfig`, `Preset`, etc.)
  - Update schema validation with `.default()` for new fields
  - Add migration logic in `defaultPreset()` if needed
- **Example**:
  ```typescript
  // In types.ts
  export interface Preset {
    // ...
    newSetting?: boolean;  // Optional during transition
  }

  // In config.schema.ts
export const presetSchema = z.object({
  // ...
  newSetting: z.boolean().default(false),  // Default for new presets
  // ...
});
  ```

## 2. Implement Data Migration
- **Files to modify**:
  - `web/src/store/configStore.ts`
- **Key functions**:
  - `replaceConfig` - Migrate on load
  - `importJson` - Handle imported configs
  - `exportJson` - Ensure backward compatibility
- **Pattern**:
  ```typescript
  // In replaceConfig/importJson
  const migrated = {
    ...config,
    presets: config.presets.map(preset => ({
      ...preset,
      // Migrate from old location or set default
      newSetting: preset.newSetting ?? config.general.oldSetting ?? defaultValue,
    })),
    // Optionally clean up old field after migration
    general: {
      ...config.general,
      // oldSetting: undefined // Uncomment to remove after migration
    }
  };
  ```

## 3. Update UI Components
- **Files to modify**:
  - Add/remove controls from relevant components
  - Example: `web/src/components/presets/PresetPanel.tsx`
- **Pattern**:
  ```tsx
  <FormControlLabel
    control={
      <Switch
        checked={active.newSetting}
        onChange={(e) => patchPreset(active.id!, 'newSetting', e.target.checked)}
      />
    }
    label="Descriptive label"
  />
  ```

## 4. Update Backend Mapping
- **Files to modify**:
  - `core/settings.py`
- **Pattern**:
  ```python
  class Settings:
      # Class variable with default
      NEW_SETTING = False
  
      @classmethod
      def apply_config(cls, config: dict):
          # ...
          # Get from new location first, fall back to old location
          if 'preset' in config and 'newSetting' in config['preset']:
              cls.NEW_SETTING = bool(config['preset']['newSetting'])
          elif 'general' in config and 'oldSetting' in config['general']:
              cls.NEW_SETTING = bool(config['general']['oldSetting'])
          
          # Persist for runtime access
          cls._last_config = config
  ```

## 5. Update Consumers (if needed)
- **Files to check**:
  - Any code that reads the affected settings
  - Example: `core/actions/training_policy.py`
- **Pattern**:
  ```python
  from core.settings import Settings
  
  def some_function():
      if Settings.NEW_SETTING:
          # New behavior
      else:
          # Old/default behavior
  ```

# Verification & Acceptance Criteria
- **Web UI behavior**
  - Open Preset panel Strategy: ensure a "Prioritize hint tiles" toggle is visible per preset (`web/src/components/presets/PresetPanel.tsx`).
  - Export config: verify JSON contains `presets[i].prioritizeHint` and also `general.prioritizeHint` mirroring the active preset.
- **Legacy import**
  - Import an old JSON that only has `general.prioritizeHint`.
  - Confirm after import each preset has `prioritizeHint` set accordingly and General mirrors the active preset’s value (see `configStore.ts`).
- **Backend mapping**
  - Start the app so backend loads config and applies settings:
```bash
# Windows PowerShell / CMD examples
python main.py
```
  - Confirm that `Settings.HINT_IS_IMPORTANT` reflects the active preset’s toggle.
- **Acceptance criteria**
  - Per-preset toggle persists across save/export/reload.
  - Legacy JSON imports without errors and behaves equivalently.
  - Training decisions respect hint priority when enabled.

# Observability
- **Logs to watch**
  - Backend: `logger_uma` debug/info around training policy decisions in `core/actions/training_policy.py`. Look for lines mentioning "hint" or undertrain/hint precedence.
  - Web console (dev): outputs from `configStore.loadLocal()` and import/export flows.
- **Grep examples**
```bash
# From repo root (PowerShell use Select-String)
rg "prioritizeHint" web/ core/
```

# Failure Modes & Recovery

## Common Issues

### UI Issues
- **Symptom**: Control not appearing in UI
  - Check component rendering logic
  - Verify props are being passed correctly
  - Look for console errors

### Import/Export Problems
- **Symptom**: Import fails with schema errors
  - Check Zod schema validation
  - Verify migration logic handles all edge cases
  - Test with minimal config

### Backend Issues
- **Symptom**: Setting not taking effect
  - Verify `Settings.apply_config()` is called
  - Check for tycos in config keys
  - Ensure backend is restarted after config changes

## Rollback Procedure
1. Revert schema changes
2. Remove new UI controls
3. Restore old setting in backend
4. Test thoroughly

## Safe Retry Steps
1. Clear local storage
2. Restart development server
3. Try with minimal config
4. Check browser console and backend logs

# Security & Compliance
- No secrets/PII involved.
- Normal repo access rights are sufficient.

# Maintenance & Change Management
- Review defaults in `defaultPreset()` and `config.schema.ts` if strategy behavior changes.
- Keep `Settings.apply_config()` consistent with schema when adding new preset fields.
- Owner: Umaplay maintainers; escalate via repository issues.

# References
- Code locations:
  - `web/src/models/types.ts`
  - `web/src/models/config.schema.ts`
  - `web/src/store/configStore.ts`
  - `web/src/components/presets/PresetPanel.tsx`
  - `web/src/components/general/GeneralForm.tsx`
  - `core/settings.py`
  - `core/actions/training_policy.py`
- Docs:
  - `docs/ai/SYSTEM_OVERVIEW.md`
  - `web/README.md`

# Open Questions
- Older desktop builds of the UI: exact versions that require the general mirroring are unknown. Validate by loading exported JSON on older builds and confirming the General toggle reads the mirrored value.

# Change Log
- 2025-10-06 – v1.0.0 – Initial SOP for moving prioritizeHint to preset; validated on local environment.
