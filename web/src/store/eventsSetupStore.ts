import { create } from 'zustand'
import { persist, subscribeWithSelector } from 'zustand/middleware'
import type {
  EventSetup,
  SelectedSupport,
  SelectedScenario,
  SelectedTrainee,
  EventPrefs,
  SupportPriority,
  AttrKey,
  Rarity,
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
}

const EMPTY: EventSetup = {
  supports: [null, null, null, null, null, null],
  scenario: null,
  trainee: null,
  prefs: {
    overrides: {},
    patterns: [],
    defaults: { support: 1, trainee: 1, scenario: 1 },
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

const pickName = (x: unknown): { name: string } | null => {
  if (x && typeof x === 'object' && 'name' in x && typeof (x as any).name === 'string') {
    return { name: (x as any).name }
  }
  return null
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
        // supports: if the field exists, rebuild from it; otherwise keep current
        const supports: (SelectedSupport|null)[] =
          ('supports' in s)
            ? Array.from({ length: 6 }, (_v, i) => {
                const raw = Array.isArray(s.supports)
                  ? (s.supports[i] as Partial<SelectedSupport> | null | undefined)
                  : undefined
                if (!raw || !raw.name || !raw.rarity || !raw.attribute) return null
                const rarity: Rarity   = isValidRarity(raw.rarity)   ? raw.rarity   : 'SR'
                const attribute: AttrKey = isValidAttr(raw.attribute) ? raw.attribute : 'SPD'
                return {
                  slot: i,
                  name: raw.name,
                  rarity,
                  attribute,
                  priority: normalizePriority((raw as any).priority),
                }
              })
            : cur.supports

        // scenario/trainee: honor explicit null if the key is present
        const scenario: SelectedScenario =
          ('scenario' in s) ? (pickName(s.scenario) ?? null) : cur.scenario
        const trainee: SelectedTrainee =
          ('trainee' in s) ? (pickName(s.trainee) ?? null) : cur.trainee

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
              }
            : cur.prefs

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
          supports[idx] = {
            slot: idx,
            name: ref.name,
            rarity: ref.rarity,
            attribute: ref.attribute,
            priority: nextPriority,
          }
        } else {
          supports[idx] = null
        }
        set({ setup: { ...s, supports }, revision: get().revision + 1 })
      },

      setScenario(ref) {
        const s = get().setup
        set({ setup: { ...s, scenario: ref ? { ...ref } : null }, revision: get().revision + 1 })
      },

      setTrainee(ref) {
        const s = get().setup
        set({ setup: { ...s, trainee: ref ? { ...ref } : null }, revision: get().revision + 1 })
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
    })),
    {
      name: 'uma_event_setup_v1',          // LocalStorage key
      version: 1,
      partialize: (s) => ({ setup: s.setup }), // only persist the data (not revision)
    }
  )
)