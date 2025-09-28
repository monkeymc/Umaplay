import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { EventKey, EventPrefs, EventSetup, SelectedScenario, SelectedSupport, SelectedTrainee } from '@/types/events'


type EventsSetupState = {
  // selection
  supports: (SelectedSupport | null)[] // length 6
  scenario: SelectedScenario
  trainee: SelectedTrainee

  // prefs (UI overrides)
  prefs: EventPrefs

  // actions
  setSupport(slot: number, sel: SelectedSupport | null): void
  swapSupports(a: number, b: number): void
  setScenario(sel: SelectedScenario): void
  setTrainee(sel: SelectedTrainee): void

  setOverride(key: EventKey, pick: number): void
  removeOverride(key: EventKey): void
  resetOverrides(): void

  importPrefs(p: Partial<EventPrefs>): void

  // snapshot helpers (for server round-trip)
  getSetup(): EventSetup
  importSetup(setup: Partial<EventSetup>): void
}

const defaultPrefs: EventPrefs = {
  overrides: {},
  patterns: [],
  defaults: { support: 1, trainee: 1, scenario: 1 },
}

export const useEventsSetupStore = create<EventsSetupState>()(
  persist(
    (set, get) => ({
  supports: [null, null, null, null, null, null],
  scenario: null,
  trainee: null,
  prefs: defaultPrefs,

  setSupport(slot, sel) {
    set(s => {
      const next = s.supports.slice()
      next[slot] = sel
      return { supports: next }
    })
  },

  swapSupports(a, b) {
    set(s => {
      const next = s.supports.slice()
      const t = next[a]; next[a] = next[b]; next[b] = t
      return { supports: next }
    })
  },

  setScenario(sel) { set({ scenario: sel }) },
  setTrainee(sel) { set({ trainee: sel }) },

  setOverride(key, pick) {
    set(s => ({ prefs: { ...s.prefs, overrides: { ...s.prefs.overrides, [key]: pick } } }))
  },
  removeOverride(key) {
    set(s => {
      const o = { ...s.prefs.overrides }
      delete o[key]
      return { prefs: { ...s.prefs, overrides: o } }
    })
  },
  resetOverrides() {
    set(s => ({ prefs: { ...s.prefs, overrides: {} } }))
  },

  importPrefs(p) {
    const curr = get().prefs
    set({ prefs: {
      overrides: p.overrides ?? curr.overrides,
      patterns:  p.patterns  ?? curr.patterns,
      defaults:  p.defaults  ?? curr.defaults,
    }})
  },

  getSetup() {
    const s = get()
    return {
      supports: s.supports,
      scenario: s.scenario,
      trainee: s.trainee,
      prefs: s.prefs,
    }
  },

  importSetup(setup) {
    if (!setup) return
    set(s => ({
      supports: setup.supports ?? s.supports,
      scenario:  setup.scenario  ?? s.scenario,
      trainee:   setup.trainee   ?? s.trainee,
      prefs:     setup.prefs     ?? s.prefs,
    }))
  },
}),
    {
      name: 'uma:events-setup:v1',
      version: 1,
      // only persist what we actually need
      partialize: (state) => ({
        supports: state.supports,
        scenario: state.scenario,
        trainee:  state.trainee,
        prefs:    state.prefs,
      }),
    }
  )
)
