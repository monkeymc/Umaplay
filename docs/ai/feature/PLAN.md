---
status: plan_ready
---
# PLAN — Undertrain Stat Distribution

## Objectives
- Make undertrain stat percentage configurable via web UI (General config)
- Improve undertrain distribution to focus on top 3 stats
- Add option to disable racing when no good training options are available (per-preset)
- Ensure backward compatibility with existing configurations
- Maintain or improve performance of training decisions

## Changes by File

### Core Logic
- `core/actions/training_policy.py`
  - Add: `DEFAULT_UNDERTRAIN_THRESHOLD` constant (6%)
  - Edit: `decide_action_training()` - Replace hardcoded 6% with config value
  - Edit: `_best_tile()` - Update logic to consider top 3 stats
  - Add: `_is_good_training_option()` - Helper to evaluate training quality
  
- `core/settings.py`
  - Add: `undertrain_threshold` to Settings class with default 6%
  - Update: `apply_config()` to handle new setting
  - Update: `extract_runtime_preset()` to include undertrain settings

### Web UI
- `web/src/store/configStore.ts`
  - Add: `undertrainThreshold` to ConfigState interface
  - Add: `setUndertrainThreshold` action
  - Update: `loadConfig` and `saveConfig` to handle new setting

- `web/src/components/general/GeneralForm.tsx`
  - Add: Slider input for undertrain threshold (1-20%)
  - Add: Tooltip explaining the setting

- `web/src/components/presets/PresetPanel.tsx`
  - Add: Toggle for "Skip race if no good training"
  - Add: Training quality threshold input

### Backend API
- `server/main.py`
  - Update: `/config` endpoint schema to include new settings
  - Add: Input validation for new settings

## Snippet Anchors to Touch
- `core/actions/training_policy.py` - `def decide_action_training():` (lines ~157-639)
- `core/settings.py` - `class Settings:` (around line 39-198)
- `web/src/store/configStore.ts` - `interface ConfigState` and related actions
- `web/src/components/general/GeneralForm.tsx` - Form layout section
- `web/src/components/presets/PresetPanel.tsx` - Preset options section

## Test Plan

### Unit Tests
- Verify undertrain threshold is applied correctly in training decisions
- Test top 3 stat focus logic with various stat distributions
- Verify race skipping behavior with different training quality thresholds
- Test edge cases (e.g., all stats equal, empty training options)

### Integration Tests
- End-to-end test of configuration flow from UI to backend
- Verify settings persistence across app restarts
- Test preset switching with different undertrain configurations

### UX/Visual
- Verify slider and toggle controls work as expected
- Ensure tooltips provide clear explanations
- Check mobile responsiveness of new form elements
- Confirm settings are clearly labeled and organized

## Verification Checklist
- [ ] All unit tests pass
- [ ] Integration tests cover new functionality
- [ ] Settings are correctly saved and loaded
- [ ] Training decisions respect the new configuration
- [ ] Race skipping works as expected
- [ ] No console errors in development mode
- [ ] Documentation is updated

## Rollback / Mitigation
- Feature flag: `ENABLE_UNDERTRAIN_CONFIG` can be set to `false` to revert to hardcoded behavior
- Database migration will be backward compatible with existing configs
- Default values ensure reasonable behavior if new settings are missing

## Open Questions
1. Should the undertrain threshold be a global setting or per-preset?
2. What's the ideal range for the undertrain threshold (e.g., 1-20%)?
3. What defines a "good" training option for race skipping purposes?
4. Should there be visual feedback when races are skipped due to training quality?
