import { create } from 'zustand'
import { persist, subscribeWithSelector } from 'zustand/middleware'
import type {
  EventSetup,
  SelectedSupport,
  SelectedScenario,
  SelectedTrainee,
  EventPrefs,
  SupportPriority,
  RewardCategory,
} from '@/types/events'

type State = {
  // internal revision to trigger subscribers (e.g., to sync into preset)
  revision: number
  setup: EventSetup
  // actions
  reset(): void
  importSetup(s: Partial<EventSetup> | undefined | null): void
  getSetup(): EventSetup
  setSupport(slot: number, ref: null | Omit<SelectedSupport, 'slot'>): void
  setScenario(ref: SelectedScenario | null): void
  setTrainee(ref: SelectedTrainee | null): void
  setPrefs(p: Partial<EventPrefs>): void
  setOverride(keyStep: string, pick: number): void
  setSupportPriority(slot: number, priority: SupportPriority): void
  setRewardPriority(priority: RewardCategory[]): void
}

export const DEFAULT_REWARD_PRIORITY: RewardCategory[] = ['skill_pts', 'stats', 'hints']

const EMPTY: EventSetup = {
  supports: [null, null, null, null, null, null],
  scenario: null,
  trainee: null,
  prefs: {
    overrides: {},
    patterns: [],
    defaults: { support: 1, trainee: 1, scenario: 1 },
    rewardPriority: [...DEFAULT_REWARD_PRIORITY],
  },
}

// --- Narrowing helpers ---
const VALID_RARITIES = ['SSR', 'SR', 'R'] as const
type ValidRarity = typeof VALID_RARITIES[number]
const isValidRarity = (x: unknown): x is ValidRarity =>
  VALID_RARITIES.includes(x as ValidRarity)

const VALID_ATTRS = ['SPD', 'STA', 'PWR', 'GUTS', 'WIT', 'PAL'] as const
type ValidAttr = typeof VALID_ATTRS[number]
const isValidAttr = (x: unknown): x is ValidAttr =>
  VALID_ATTRS.includes(x as ValidAttr)

const ensureBoolean = (val: unknown, fallback = true): boolean =>
  typeof val === 'boolean' ? val : fallback

const normalizeRewardPriority = (raw: unknown, fallback?: RewardCategory[]): RewardCategory[] => {
  const allowed: RewardCategory[] = ['skill_pts', 'stats', 'hints']
  const result: RewardCategory[] = []
  const seen = new Set<RewardCategory>()

  if (Array.isArray(raw)) {
    for (const item of raw) {
      if (typeof item !== 'string') continue
      const key = item.trim().toLowerCase()
      const normalized = key === 'skill_points' ? 'skill_pts' : (allowed.includes(key as RewardCategory) ? (key as RewardCategory) : undefined)
      if (!normalized) continue
      if (!seen.has(normalized)) {
        seen.add(normalized)
        result.push(normalized)
      }
    }
  }

  const fallbackList = fallback && fallback.length ? fallback : DEFAULT_REWARD_PRIORITY
  for (const cat of fallbackList) {
    if (!seen.has(cat)) {
      seen.add(cat)
      result.push(cat)
    }
  }
  return result
}

const pickSupport = (raw: unknown, slot: number, fallback?: SelectedSupport | null): SelectedSupport | null => {
  if (!raw || typeof raw !== 'object') return fallback ?? null
  if (!('name' in raw) || typeof (raw as any).name !== 'string') return fallback ?? null
  if (!('rarity' in raw) || !isValidRarity((raw as any).rarity)) return fallback ?? null
  if (!('attribute' in raw) || !isValidAttr((raw as any).attribute)) return fallback ?? null
  const priority = normalizePriority((raw as any).priority)
  const avoidEnergyOverflow = ensureBoolean(
    (raw as any).avoidEnergyOverflow ?? (raw as any).avoid_energy_overflow,
    fallback?.avoidEnergyOverflow ?? true
  )
  return {
    slot,
    name: (raw as any).name,
    rarity: (raw as any).rarity,
    attribute: (raw as any).attribute,
    priority,
    avoidEnergyOverflow,
  }
}

const pickEntity = <T extends { name: string; avoidEnergyOverflow?: boolean }>(
  raw: unknown,
  fallback: T | null
): T | null => {
  if (!raw || typeof raw !== 'object' || !('name' in raw)) return fallback
  const name = (raw as any).name
  if (typeof name !== 'string' || !name.trim()) return fallback
  return {
    name,
    avoidEnergyOverflow: ensureBoolean(
      (raw as any).avoidEnergyOverflow ?? (raw as any).avoid_energy_overflow,
      fallback?.avoidEnergyOverflow ?? true
    ),
  } as T
}

const DEFAULT_PRIORITY: SupportPriority = {
  enabled: true,
  scoreBlueGreen: 0.75,
  scoreOrangeMax: 0.5,
}

const normalizePriority = (raw: unknown): SupportPriority => {
  if (!raw || typeof raw !== 'object') return { ...DEFAULT_PRIORITY }
  const enabled = typeof (raw as any).enabled === 'boolean' ? (raw as any).enabled : true
  const scoreBlueGreen = Number.isFinite((raw as any).scoreBlueGreen)
    ? clampNumber((raw as any).scoreBlueGreen, 0, 10)
    : DEFAULT_PRIORITY.scoreBlueGreen
  const scoreOrangeMax = Number.isFinite((raw as any).scoreOrangeMax)
    ? clampNumber((raw as any).scoreOrangeMax, 0, 10)
    : DEFAULT_PRIORITY.scoreOrangeMax
  return { enabled, scoreBlueGreen, scoreOrangeMax }
}

const clampNumber = (val: number, min: number, max: number): number => {
  const n = Number(val)
  if (!Number.isFinite(n)) return min
  return Math.min(max, Math.max(min, n))
}

export const useEventsSetupStore = create<State>()(
  persist(
    subscribeWithSelector((set, get) => ({
      revision: 0,
      setup: { ...EMPTY },

      reset() {
        set({ setup: { ...EMPTY }, revision: get().revision + 1 })
      },

      importSetup(s) {
        // If not provided, reset to EMPTY so we never leak data across presets.
        if (!s) {
          set({ setup: JSON.parse(JSON.stringify(EMPTY)), revision: get().revision + 1 })
          return
        }
        const cur = get().setup
        const curPrefs = cur.prefs || EMPTY.prefs
        // supports: if the field exists, rebuild from it; otherwise keep current
        const supports: (SelectedSupport|null)[] =
          ('supports' in s)
            ? Array.from({ length: 6 }, (_v, i) => {
                const raw = Array.isArray(s.supports)
                  ? (s.supports[i] as Partial<SelectedSupport> | null | undefined)
                  : undefined
                return pickSupport(raw, i, cur.supports[i] ?? null)
              })
            : cur.supports

        // scenario/trainee: honor explicit null if the key is present
        const scenario: SelectedScenario =
          ('scenario' in s) ? pickEntity<NonNullable<SelectedScenario>>(s.scenario, cur.scenario) : cur.scenario
        const trainee: SelectedTrainee =
          ('trainee' in s) ? pickEntity<NonNullable<SelectedTrainee>>(s.trainee, cur.trainee) : cur.trainee

        // prefs: if present, normalize; otherwise keep current
        const prefs: EventPrefs =
          ('prefs' in s && s.prefs)
            ? {
                overrides: { ...(s.prefs.overrides || {}) },
                patterns:  Array.isArray(s.prefs.patterns) ? s.prefs.patterns.slice() : [],
                defaults: {
                  support:  Number(s.prefs.defaults?.support  ?? 1),
                  trainee:  Number(s.prefs.defaults?.trainee  ?? 1),
                  scenario: Number(s.prefs.defaults?.scenario ?? 1),
                },
                rewardPriority: normalizeRewardPriority(
                  (s.prefs as any).rewardPriority ?? (s.prefs as any).reward_priority,
                  curPrefs.rewardPriority,
                ),
              }
            : curPrefs

        set({ setup: { supports, scenario, trainee, prefs }, revision: get().revision + 1 })
      },

      getSetup() {
        // Return a deep clone so callers can safely serialize/mutate
        return JSON.parse(JSON.stringify(get().setup)) as EventSetup
      },

      setSupport(slot, ref) {
        const s = get().setup
        const idx = Math.max(0, Math.min(5, slot))
        const supports = s.supports.slice()
        if (ref) {
          const nextPriority = ref.priority
            ? normalizePriority(ref.priority)
            : supports[idx]?.priority || { ...DEFAULT_PRIORITY }
          const avoidEnergyOverflow = ensureBoolean(
            ref.avoidEnergyOverflow,
            supports[idx]?.avoidEnergyOverflow ?? true
          )
          supports[idx] = {
            slot: idx,
            name: ref.name,
            rarity: ref.rarity,
            attribute: ref.attribute,
            priority: nextPriority,
            avoidEnergyOverflow,
          }
        } else {
          supports[idx] = null
        }
        set({ setup: { ...s, supports }, revision: get().revision + 1 })
      },

      setScenario(ref) {
        const s = get().setup
        const next = ref
          ? {
              name: ref.name,
              avoidEnergyOverflow: ensureBoolean(
                ref.avoidEnergyOverflow,
                s.scenario?.avoidEnergyOverflow ?? true
              ),
            }
          : null
        set({ setup: { ...s, scenario: next }, revision: get().revision + 1 })
      },

      setTrainee(ref) {
        const s = get().setup
        const next = ref
          ? {
              name: ref.name,
              avoidEnergyOverflow: ensureBoolean(
                ref.avoidEnergyOverflow,
                s.trainee?.avoidEnergyOverflow ?? true
              ),
            }
          : null
        set({ setup: { ...s, trainee: next }, revision: get().revision + 1 })
      },

      setPrefs(p) {
        const s = get().setup
        const cur = s.prefs || EMPTY.prefs
        const next: EventPrefs = {
          overrides: { ...cur.overrides, ...(p.overrides || {}) },
          patterns:  Array.isArray(p.patterns) ? p.patterns.slice() : cur.patterns,
          defaults: {
            support: Number(p.defaults?.support ?? cur.defaults.support),
            trainee: Number(p.defaults?.trainee ?? cur.defaults.trainee),
            scenario:Number(p.defaults?.scenario ?? cur.defaults.scenario),
          },
          rewardPriority: normalizeRewardPriority(p.rewardPriority, cur.rewardPriority),
        }
        set({ setup: { ...s, prefs: next }, revision: get().revision + 1 })
      },
      setOverride(keyStep, pick) {
        const s = get().setup
        const next: EventPrefs = {
          ...s.prefs,
          overrides: { ...(s.prefs?.overrides ?? {}), [keyStep]: Number(pick) },
        }
        set({ setup: { ...s, prefs: next }, revision: get().revision + 1 })
      },
      setSupportPriority(slot, priority) {
        const s = get().setup
        const idx = Math.max(0, Math.min(5, slot))
        const supports = s.supports.slice()
        const target = supports[idx]
        if (!target) return
        supports[idx] = {
          ...target,
          priority: normalizePriority(priority),
        }
        set({ setup: { ...s, supports }, revision: get().revision + 1 })
      },
      setRewardPriority(priority) {
        const s = get().setup
        const nextPriority = normalizeRewardPriority(priority, s.prefs?.rewardPriority)
        set({
          setup: {
            ...s,
            prefs: {
              ...s.prefs,
              rewardPriority: nextPriority,
            },
          },
          revision: get().revision + 1,
        })
      },
    })),
    {
      name: 'uma_event_setup_v1',          // LocalStorage key
      version: 1,
      partialize: (s) => ({ setup: s.setup }), // only persist the data (not revision)
    }
  )
)