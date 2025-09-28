import { create } from 'zustand'
import { persist, subscribeWithSelector } from 'zustand/middleware'
import type {
  EventSetup,
  SelectedSupport,
  SelectedScenario,
  SelectedTrainee,
  EventPrefs,
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

export const useEventsSetupStore = create<State>()(
  persist(
    subscribeWithSelector((set, get) => ({
      revision: 0,
      setup: { ...EMPTY },

      reset() {
        set({ setup: { ...EMPTY }, revision: get().revision + 1 })
      },

      importSetup(s) {
        if (!s) return
        const cur = get().setup
        // normalize supports → fixed length 6 with slot index and strict unions
        // normalize supports (length=6 + slot + validated unions)
        const supports: (SelectedSupport|null)[] = Array.from({ length: 6 }, (_v, i) => {
          const raw = Array.isArray(s.supports)
            ? (s.supports[i] as Partial<SelectedSupport> | null | undefined)
            : undefined
          if (!raw || !raw.name || !raw.rarity || !raw.attribute) return cur.supports[i] ?? null
          const rarity: Rarity = isValidRarity(raw.rarity) ? raw.rarity : 'SR'
          const attribute: AttrKey = isValidAttr(raw.attribute) ? raw.attribute : 'SPD'
          return { slot: i, name: raw.name, rarity, attribute }
        })
        const scenario: SelectedScenario = pickName(s.scenario) ?? cur.scenario
        const trainee:  SelectedTrainee  = pickName(s.trainee)  ?? cur.trainee
        const prefs: EventPrefs = {
          overrides: { ...(cur.prefs?.overrides || {}), ...((s as any).prefs?.overrides || {}) },
          patterns:  Array.isArray((s as any).prefs?.patterns) ? (s as any).prefs.patterns.slice() : (cur.prefs?.patterns || []),
          defaults: {
            support:  Number((s as any).prefs?.defaults?.support  ?? cur.prefs?.defaults?.support  ?? 1),
            trainee:  Number((s as any).prefs?.defaults?.trainee  ?? cur.prefs?.defaults?.trainee  ?? 1),
            scenario: Number((s as any).prefs?.defaults?.scenario ?? cur.prefs?.defaults?.scenario ?? 1),
          },
        }
        const next: EventSetup = { supports, scenario, trainee, prefs }
        set({ setup: next, revision: get().revision + 1 })
      },

      getSetup() {
        // Return a deep clone so callers can safely serialize/mutate
        return JSON.parse(JSON.stringify(get().setup)) as EventSetup
      },

      setSupport(slot, ref) {
        const s = get().setup
        const idx = Math.max(0, Math.min(5, slot))
        const supports = s.supports.slice()
        supports[idx] = ref ? ({ slot: idx, ...ref } as SelectedSupport) : null
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
    })),
    {
      name: 'uma_event_setup_v1',          // LocalStorage key
      version: 1,
      partialize: (s) => ({ setup: s.setup }), // only persist the data (not revision)
    }
  )
)