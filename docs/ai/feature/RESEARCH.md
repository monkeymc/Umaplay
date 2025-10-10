# RESEARCH — Undertrain Stat Distribution

## Research Question
Make undertrain stat % configurable in the web UI, improve undertrain distribution logic to focus on top 3 stats, and add an option to disable racing if no good options are available.

## Summary
- The undertrain stat distribution is currently hardcoded with a 6% threshold in `training_policy.py`
- The settings system uses a two-way flow between the React frontend and Python backend
- Configuration is persisted in `config.json` and applied at runtime
- The undertrain logic in `decide_action_training` will need updates to support the new features

## Detailed Findings

### Area: Training Policy
- **Why relevant**: Contains the core logic for undertrain stat handling
- **Files & anchors**:
  - `core/actions/training_policy.py:157-639` - Main training decision logic including undertrain stat handling
  - `core/actions/training_check.py:523-718` - Support value computation and risk assessment
- **Key Components**:
  - `decide_action_training()` - Main decision function that needs updates for new features
  - `_best_tile()` - Helper function that handles tile selection logic
  - `_exclude_capped()` - Filters out stats that have reached their targets
  - `_best_tile_of_type()` - Finds the best tile for a specific stat type
  - `_any_wit_rainbow()` - Checks for rainbow WIT tiles which have special handling
  - `_tiles_with_hint()` - Identifies tiles with hint indicators

### Area: Web UI & Configuration
- **Why relevant**: Handles user configuration and settings persistence
- **Files & anchors**:
  - `web/src/components/general/GeneralForm.tsx` - Main settings form component
  - `web/src/store/configStore.ts` - Zustand store for configuration state
  - `server/main.py` - Backend API endpoints for config management
  - `core/settings.py` - Runtime settings and configuration application
- **Data Flow**:
  1. User updates settings in the UI (e.g., GeneralForm)
  2. Changes are saved to the Zustand store
  3. Store persists changes via API calls to `/config` endpoint
  4. Backend saves to `config.json` and applies settings via `Settings.apply_config()`
- **Key Components**:
  - `useConfigStore` - Zustand store hook for managing configuration state
  - `apply_config()` - Method in Settings class that applies configuration changes
  - `extract_runtime_preset()` - Extracts preset-specific settings for the runtime

### Area: Preset System
- **Why relevant**: Settings can be saved and loaded as presets
- **Key Components**:
  - `Settings.extract_runtime_preset()` - Extracts preset-specific settings
  - `config.presets` array - Stores all available presets
  - `config.activePresetId` - Tracks the currently active preset
  - `PresetsShell.tsx` - Manages the preset selection and management UI
  - `PresetPanel.tsx` - Handles the display and editing of individual presets
- **Preset Structure**:
  ```typescript
  interface Preset {
    id: string;
    name: string;
    targetStats: Record<string, number>;
    priorityStats: string[];
    minimalMood: string;
    // ... other preset-specific settings
  }
  ```
- **Persistence**:
  - Presets are stored in the main config.json file
  - The active preset is applied when selected
  - Changes to presets are automatically saved

## 360° Around Target(s)
- **Target file(s)**: `core/actions/training_policy.py` 
- **Import or dependency graph (depth 2)**:
  - `core/actions/training_check.py` - Provides support value computation
  - `core/settings.py` - Contains configuration constants and application logic
  - `core/agent.py` - Main agent loop that uses the training policy
  - `web/src/store/configStore.ts` - Frontend configuration state (Zustand store)
  - `web/src/components/general/GeneralForm.tsx` - UI for configuration
  - `server/main.py` - Backend API endpoints for config management
  - `server/utils.py` - Low-level config loading/saving functions

## Open Questions / Ambiguities

### Undertrain Threshold UI
- **Location in UI**:
  - Should be placed in the General section or a new Training section?
  - Needs to be clearly labeled and include a tooltip explaining its purpose

- **Implementation Options**:
  1. **Per-preset setting** (Recommended)
     - Allows different strategies for different presets
     - Stored in the preset object in config
     - Default: 6% (matching current hardcoded value)
     - Range: 1-20% with 1% steps
     - UI: Slider with percentage display

  2. **Global setting**
     - Simpler implementation
     - Less flexible for different strategies
     - Would be stored in the general config section

- **Technical Considerations**:
  - Need to update the preset schema in `configStore.ts`
  - Add validation in the Settings class
  - Ensure proper type safety in TypeScript interfaces

### Top 3 Stats Focus
- **Implementation Options**:
  1. **Configurable Focus**
     - Add a toggle: "Focus on top 3 stats"
     - Default: Enabled (matching current behavior)
     - When disabled, consider all stats equally

  2. **Tie-Breaking Logic**:
     - Use `PRIORITY_STATS` order to break ties
     - Consider adding visual indicators in the UI for stat priority
     - Document the tie-breaking behavior

- **Technical Considerations**:
  - Need to modify `decide_action_training()` to respect this setting
  - Update the training policy to handle both modes
  - Consider performance implications of checking all stats vs top 3

### Race Disabling Logic
- **Race Quality Assessment**:
  - **High Priority Races** (Never skip):
    - G1 races
    - Races marked as important in the race plan
    - Races that are part of the main story progression
  
  - **Medium Priority Races** (Skip if better training available):
    - Regular planned races
    - Races that provide useful rewards
  
  - **Low Priority Races** (Skip if any good training available):
    - Unplanned races
    - Races with minimal rewards

- **Implementation Strategy**:
  1. Add a new setting: "Skip race if no good training options"
  2. Define what makes training "good enough":
     - Stat gain above a certain threshold
     - Presence of specific support cards
     - Current mood and energy levels
  3. Add a minimum stat threshold setting
  4. Consider adding a visual indicator in the UI for race priority

- **Technical Considerations**:
  - Need to modify the race decision logic in the training policy
  - Add new settings to the config schema
  - Ensure proper error handling for edge cases
  - Consider adding logging for skipped races for debugging

## Implementation Impact Analysis

### Affected Components
1. **Core Training Logic**
   - `training_policy.py` will need significant updates
   - New helper functions may be needed for the enhanced logic
   - Existing functions may need refactoring for better maintainability

2. **Configuration System**
   - Need to add new settings to the config schema
   - Update the settings application logic
   - Ensure backward compatibility with existing configs

3. **User Interface**
   - Add new controls to the settings panel
   - Update the preset editor
   - Add tooltips and help text

### Performance Considerations
- The new logic might have a performance impact during training decisions
- Consider adding caching for expensive calculations
- Profile the changes to ensure acceptable performance

## Suggested Next Steps
1. Create a detailed implementation plan in `PLAN.md` that includes:
   - Backend changes to make undertrain threshold configurable
   - Updates to the training policy for improved stat distribution
   - New UI components for configuration
   - Testing strategy for the new features
   - Documentation updates

2. Start with implementing the configurable undertrain threshold as it's the most straightforward change and provides immediate value.

3. Follow up with the improved distribution logic and race disabling features in subsequent iterations.
