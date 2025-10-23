import { create } from 'zustand'
import { fetchNavPrefs, saveNavPrefs, type NavPrefs } from '@/services/api'

const DEFAULT_PREFS: NavPrefs = {
  daily_races: {
    alarm_clock: true,
    star_pieces: false,
    parfait: false,
  },
}

type DailyKey = keyof NavPrefs['daily_races']

type NavPrefsState = {
  prefs: NavPrefs
  loaded: boolean
  loading: boolean
  saving: boolean
  error?: string
  load: () => Promise<void>
  toggleDaily: (key: DailyKey, value: boolean) => void
  save: () => Promise<NavPrefs>
  resetError: () => void
}

const defaultPrefs = (): NavPrefs => ({
  daily_races: { ...DEFAULT_PREFS.daily_races },
})

const mergeWithDefaults = (prefs: NavPrefs | undefined): NavPrefs => ({
  daily_races: {
    alarm_clock: prefs?.daily_races?.alarm_clock ?? DEFAULT_PREFS.daily_races.alarm_clock,
    star_pieces: prefs?.daily_races?.star_pieces ?? DEFAULT_PREFS.daily_races.star_pieces,
    parfait: prefs?.daily_races?.parfait ?? DEFAULT_PREFS.daily_races.parfait,
  },
})

export const useNavPrefsStore = create<NavPrefsState>((set, get) => ({
  prefs: defaultPrefs(),
  loaded: false,
  loading: false,
  saving: false,
  error: undefined,
  load: async () => {
    if (get().loading) return
    set({ loading: true, error: undefined })
    try {
      const prefs = await fetchNavPrefs()
      set({ prefs: mergeWithDefaults(prefs), loading: false, loaded: true })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load nav preferences'
      set({ loading: false, error: message })
      throw err
    }
  },
  toggleDaily: (key, value) =>
    set((state) => ({
      prefs: {
        ...state.prefs,
        daily_races: {
          ...state.prefs.daily_races,
          [key]: value,
        },
      },
      error: undefined,
    })),
  save: async () => {
    set({ saving: true, error: undefined })
    const current = get().prefs
    try {
      const saved = await saveNavPrefs(current)
      const merged = mergeWithDefaults(saved)
      set({ prefs: merged, saving: false, loaded: true })
      return merged
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to save nav preferences'
      set({ saving: false, error: message })
      throw err
    }
  },
  resetError: () => set({ error: undefined }),
}))
