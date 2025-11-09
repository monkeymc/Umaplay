import type { FC } from 'react'
import type { StrategyComponentProps } from './UraStrategy'
import UraStrategy from './UraStrategy'
import UnityCupStrategy from './UnityCupStrategy'

/**
 * Strategy component registry
 * Maps scenario keys to their respective Bot Strategy UI components
 * 
 * To add a new scenario:
 * 1. Create a new file (e.g., GrandMastersStrategy.tsx) implementing StrategyComponentProps
 * 2. Import it here
 * 3. Register it in the map below
 * 
 * The loader will fall back to URA if the scenario is not registered
 */
const strategyRegistry: Record<string, FC<StrategyComponentProps>> = {
  ura: UraStrategy,
  unity_cup: UnityCupStrategy,
  // Add new scenarios here:
  // grand_masters: GrandMastersStrategy,
  // aoharu: AoharuStrategy,
}

/**
 * Get the appropriate Strategy component for a given scenario
 * @param scenario - The scenario key (e.g., 'ura', 'unity_cup')
 * @returns The corresponding Strategy component, or URA as fallback
 */
export function getStrategyComponent(scenario: string): FC<StrategyComponentProps> {
  return strategyRegistry[scenario] ?? strategyRegistry.ura
}

export type { StrategyComponentProps }
