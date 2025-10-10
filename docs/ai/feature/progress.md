# Plan: Undertrain Threshold Configuration

## Context & Goal
Add configuration for undertrain threshold in advanced settings to control when stats are considered undertrained. This helps fine-tune the training behavior based on stat development needs.

## Decisions
1. Move `undertrainThreshold` into `advanced` object in [GeneralConfig](cci:2://file:///d:/GitHub/UmAutoplay/web/src/models/types.ts:8:0-24:1)
2. Set default threshold to 6%
3. Range limit to 0-100%

## Files & Anchors
- [web/src/models/types.ts](cci:7://file:///d:/GitHub/UmAutoplay/web/src/models/types.ts:0:0-0:0) - Update GeneralConfig interface
- [web/src/models/config.schema.ts](cci:7://file:///d:/GitHub/UmAutoplay/web/src/models/config.schema.ts:0:0-0:0) - Add schema validation
- [web/src/components/general/AdvancedSettings.tsx](cci:7://file:///d:/GitHub/UmAutoplay/web/src/components/general/AdvancedSettings.tsx:0:0-0:0) - Add UI control

## Implementation Plan
1. [ ] Update TypeScript types
2. [ ] Add schema validation
3. [ ] Create UI component
4. [ ] Connect UI to state management
5. [ ] Add tooltip/help text
6. [ ] Test with different threshold values
7. [ ] Document new feature

## Current Status
- Basic type definition added
- Schema and UI pending

## Next Step
Update [config.schema.ts](cci:7://file:///d:/GitHub/UmAutoplay/web/src/models/config.schema.ts:0:0-0:0) to include undertrainThreshold in advanced settings validation.

- context_usage_estimate: 30%
- ready_to_reseed: yes