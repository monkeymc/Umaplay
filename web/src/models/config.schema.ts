import { z } from 'zod'
import type { AppConfig, GeneralConfig, Preset, StatKey } from './types'

// Lightweight re-declare to avoid circulars in schema:
const eventDefaults = { support: 1, trainee: 1, scenario: 1 }
const defaultRewardPriority = ['skill_pts', 'stats', 'hints'] as const
export const defaultEventSetup = () => ({
  supports: [null, null, null, null, null, null],
  scenario: null,
  trainee: null,
  prefs: { overrides: {}, patterns: [], defaults: eventDefaults, rewardPriority: [...defaultRewardPriority] },
})

export const STAT_KEYS: StatKey[] = ['SPD', 'STA', 'PWR', 'GUTS', 'WIT']

export const generalSchema = z.object({
  mode: z.enum(['steam', 'scrcpy', 'bluestack']).default('steam'),
  windowTitle: z.string().default('Umamusume'),
  fastMode: z.boolean().default(false),
  tryAgainOnFailedGoal: z.boolean().default(true),
  maxFailure: z.number().int().min(0).max(99).default(20),
  acceptConsecutiveRace: z.boolean().default(true),
  advanced: z.object({
    hotkey: z.enum(['F1', 'F2', 'F3', 'F4']).default('F2'),
    debugMode: z.boolean().default(true),
    useExternalProcessor: z.boolean().default(false),
    externalProcessorUrl: z.string().url().default('http://127.0.0.1:8001'),
    autoRestMinimum: z.number().int().min(0).max(100).default(26),
    undertrainThreshold: z.number().min(0).max(100).default(6),
    topStatsFocus: z.number().int().min(1).max(5).default(3),
    skillCheckInterval: z.number().int().min(1).max(12).default(3),
    skillPtsDelta: z.number().int().min(0).max(1000).default(60),
  }).default({
    hotkey: 'F2',
    debugMode: true,
    useExternalProcessor: false,
    externalProcessorUrl: 'http://127.0.0.1:8001',
    autoRestMinimum: 18,
    undertrainThreshold: 6,
    topStatsFocus: 3,
    skillCheckInterval: 3,
    skillPtsDelta: 60,
  }),
})


export const presetSchema = z.object({
  id: z.string(),
  name: z.string(),
  priorityStats: z.array(z.enum(STAT_KEYS)).min(5).max(5),
  targetStats: z.record(z.enum(STAT_KEYS), z.number().int().min(0)),
  minimalMood: z.enum(['AWFUL', 'BAD', 'NORMAL', 'GOOD', 'GREAT']),
  juniorStyle: z.enum(['end', 'late', 'pace', 'front']).nullable(),
  skillsToBuy: z.array(z.string()),
  skillPtsCheck: z.number().int().min(0).default(600),
  plannedRaces: z.record(z.string(), z.string()),
  raceIfNoGoodValue: z.boolean().default(false),
  prioritizeHint: z.boolean().default(false),
  // Make optional on input, but always present on output via default()
  event_setup: (() => {
    const rarity = z.enum(['SSR','SR','R'])
    const attr   = z.enum(['SPD','STA','PWR','GUTS','WIT','PAL'])
    const supportPriority = z.object({
      enabled: z.boolean().default(true),
      scoreBlueGreen: z.number().min(0).max(10).default(0.75),
      scoreOrangeMax: z.number().min(0).max(10).default(0.5),
    }).default({ enabled: true, scoreBlueGreen: 0.75, scoreOrangeMax: 0.5 })

    const selectedSupport = z.object({
      slot: z.number(),
      name: z.string(),
      rarity,
      attribute: attr,
      priority: supportPriority.optional(),
      avoidEnergyOverflow: z.boolean().default(true).optional(),
    })
    const selectedScenario = z.object({
      name: z.string(),
      avoidEnergyOverflow: z.boolean().default(true).optional(),
    }).nullable()
    const selectedTrainee  = z.object({
      name: z.string(),
      avoidEnergyOverflow: z.boolean().default(true).optional(),
    }).nullable()

    const defaults = { support: 1, trainee: 1, scenario: 1 }
    const eventPrefs = z.object({
      // IMPORTANT: string keys! (EventKey)
      overrides: z.record(z.string(), z.number()).default({}),
      patterns: z.array(z.object({ pattern: z.string(), pick: z.number() })).default([]),
      defaults: z.object({
        support: z.number().default(1),
        trainee: z.number().default(1),
        scenario: z.number().default(1),
      }).default(defaults),
      rewardPriority: z
        .array(z.enum(['skill_pts', 'stats', 'hints']))
        .default(['skill_pts', 'stats', 'hints']),
    })

    const eventSetup = z.object({
      supports: z.array(selectedSupport.nullable()).length(6).default([null, null, null, null, null, null]),
      scenario: selectedScenario.default(null),
      trainee:  selectedTrainee.default(null),
      prefs:    eventPrefs.default({
        overrides: {},
        patterns: [],
        defaults: { support: 1, trainee: 1, scenario: 1 },
        rewardPriority: ['skill_pts', 'stats', 'hints'],
      }),
    })

    return eventSetup
  })().default({
    supports: [null, null, null, null, null, null],
    scenario: null,
    trainee:  null,
    prefs: {
      overrides: {},
      patterns: [],
      defaults: { support: 1, trainee: 1, scenario: 1 },
      rewardPriority: ['skill_pts', 'stats', 'hints'],
    },
  }),
})

export const appConfigSchema = z.object({
  version: z.number().int(),
  general: generalSchema,
  presets: z.array(presetSchema),
  activePresetId: z.string().optional(),
})

export const defaultGeneral: GeneralConfig = generalSchema.parse({})
export const defaultPreset = (id: string, name: string): Preset => ({
  id,
  name,
  priorityStats: ['SPD', 'STA', 'WIT', 'PWR', 'GUTS'],
  raceIfNoGoodValue: false,
  prioritizeHint: false,
  skillPtsCheck: 600,
  targetStats: {
    SPD: 1150,
    STA: 900,
    PWR: 700,
    GUTS: 250,
    WIT: 300,
  },
  minimalMood: 'NORMAL',
  juniorStyle: null,
  skillsToBuy: [],
  plannedRaces: {},
  // let schema inject defaults; or be explicit:
  event_setup: defaultEventSetup(),
})

export const defaultAppConfig = (): AppConfig => ({
  version: 1,
  general: defaultGeneral,
  presets: [defaultPreset(crypto.randomUUID(), 'Preset 1')],
  activePresetId: undefined,
})
