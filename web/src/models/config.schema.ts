import { z } from 'zod'
import type { AppConfig, GeneralConfig, Preset, StatKey } from './types'

export const STAT_KEYS: StatKey[] = ['SPD', 'STA', 'PWR', 'GUTS', 'WIT']

export const generalSchema = z.object({
  mode: z.enum(['steam', 'scrcpy', 'bluestack']).default('steam'),
  windowTitle: z.string().default('Umamusume'),
  fastMode: z.boolean().default(false),
  tryAgainOnFailedGoal: z.boolean().default(true),
  prioritizeHint: z.boolean().default(false),
  maxFailure: z.number().int().min(0).max(99).default(20),
  skillPtsCheck: z.number().int().min(0).default(600),
  acceptConsecutiveRace: z.boolean().default(true),
  advanced: z.object({
    hotkey: z.enum(['F1', 'F2', 'F3', 'F4']).default('F2'),
    debugMode: z.boolean().default(true),
    useExternalProcessor: z.boolean().default(false),
    externalProcessorUrl: z.string().url().default('http://127.0.0.1:8001'),
    autoRestMinimum: z.number().int().min(0).max(100).default(26),
  }).default({
    hotkey: 'F2',
    debugMode: true,
    useExternalProcessor: false,
    externalProcessorUrl: 'http://127.0.0.1:8001',
    autoRestMinimum: 22,
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
  plannedRaces: z.record(z.string(), z.string()),
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
  targetStats: {
    SPD: 1150,
    STA: 1000,
    PWR: 530,
    GUTS: 270,
    WIT: 250,
  },
  minimalMood: 'NORMAL',
  juniorStyle: null,
  skillsToBuy: [],
  plannedRaces: {},
})

export const defaultAppConfig = (): AppConfig => ({
  version: 1,
  general: defaultGeneral,
  presets: [defaultPreset(crypto.randomUUID(), 'Preset 1')],
  activePresetId: undefined,
})
