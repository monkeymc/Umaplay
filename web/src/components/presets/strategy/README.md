# Strategy Components Architecture

## Overview
Scenario-specific Bot Strategy/Policy UI components live here, following a **registry pattern** for clean separation and easy extensibility.

## Structure
```
strategy/
├── index.ts                  # Component registry/loader
├── UraStrategy.tsx           # URA Finale strategy controls
├── UnityCupStrategy.tsx      # Unity Cup strategy controls
└── README.md                 # This file
```

## Design Principles

### 1. **Component Interface**
All strategy components implement `StrategyComponentProps`:
```tsx
export interface StrategyComponentProps {
  preset: Preset
}
```

### 2. **Registry Pattern**
The `index.ts` file maintains a mapping of scenario keys → components:
```tsx
const strategyRegistry: Record<string, FC<StrategyComponentProps>> = {
  ura: UraStrategy,
  unity_cup: UnityCupStrategy,
}
```

### 3. **Dynamic Loading**
`PresetPanel.tsx` uses `getStrategyComponent(scenarioKey)` to dynamically render the correct component based on the active scenario.

## Adding a New Scenario

To add a new scenario (e.g., Grand Masters):

1. **Create the component file** `GrandMastersStrategy.tsx`:
```tsx
import type { StrategyComponentProps } from './UraStrategy'
import Section from '@/components/common/Section'
// ... other imports

export default function GrandMastersStrategy({ preset }: StrategyComponentProps) {
  const patchPreset = useConfigStore((s) => s.patchPreset)
  
  return (
    <Section title="Bot Strategy / Policy" sx={{ variant: 'plain', px: 0, py: 0 }}>
      {/* Your scenario-specific controls here */}
    </Section>
  )
}
```

2. **Register in `index.ts`**:
```tsx
import GrandMastersStrategy from './GrandMastersStrategy'

const strategyRegistry: Record<string, FC<StrategyComponentProps>> = {
  ura: UraStrategy,
  unity_cup: UnityCupStrategy,
  grand_masters: GrandMastersStrategy, // Add this line
}
```

3. **Done!** The component will automatically be used when that scenario is active.

## Shared Components
If multiple scenarios share common UI elements, extract them into separate components:
- `SharedStrategyField.tsx` for reusable controls
- Import and compose them within scenario-specific files

## Benefits
- ✅ **Separation of Concerns**: Each scenario owns its strategy UI
- ✅ **Type Safety**: TypeScript ensures consistent interfaces
- ✅ **Easy Extension**: Adding scenarios is a two-step process
- ✅ **No Conditionals**: No sprawling if/else chains in parent components
- ✅ **Maintainability**: Changes to one scenario don't affect others

## Migration Notes
Previously, the Bot Strategy section was hardcoded in `PresetPanel.tsx`. This has been refactored to use the registry pattern, with URA and Unity Cup as the initial implementations.
