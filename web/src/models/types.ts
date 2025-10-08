import type { EventSetup } from "@/types/events"

export type Mode = 'steam' | 'scrcpy' | 'bluestack'
export type Hotkey = 'F1' | 'F2' | 'F3' | 'F4'

export type StatKey = 'SPD' | 'STA' | 'PWR' | 'GUTS' | 'WIT'
export type MoodName = 'AWFUL' | 'BAD' | 'NORMAL' | 'GOOD' | 'GREAT'

export interface GeneralConfig {
  mode: Mode
  windowTitle: string
  fastMode: boolean
  tryAgainOnFailedGoal: boolean
  maxFailure: number
  skillPtsCheck: number
  acceptConsecutiveRace: boolean
  advanced: {
    hotkey: Hotkey
    debugMode: boolean
    useExternalProcessor: boolean
    externalProcessorUrl: string
    autoRestMinimum: number
    undertrainThreshold: number // Percentage threshold for undertraining stats (0-100)
    topStatsFocus: number // Number of top stats to focus on (1-5)
  }
}

export interface Preset {
  id: string
  name: string
  priorityStats: StatKey[]
  targetStats: Record<StatKey, number>
  minimalMood: MoodName
  juniorStyle: 'end' | 'late' | 'pace' | 'front' | null
  skillsToBuy: string[]
  event_setup?: EventSetup
  plannedRaces: Record<string, string> // dateKey -> raceName (Y{year}-{MM}-{half})
  raceIfNoGoodValue?: boolean // Whether to race even if no good training options are available
  prioritizeHint?: boolean // Moved from general to per-preset
}

export interface AppConfig {
  version: number
  general: GeneralConfig
  presets: Preset[]
  activePresetId?: string
}
