import { create } from 'zustand'
import { fetchNavPrefs, saveNavPrefs, type NavPrefs } from '@/services/api'

const DEFAULT_PREFS: NavPrefs = {
  shop: {
    alarm_clock: true,
    star_pieces: false,
    parfait: false,
  },
  team_trials: {
    preferred_banner: 3,
  },
}

type ShopKey = keyof NavPrefs['shop']

type NavPrefsState = {
  prefs: NavPrefs
  loaded: boolean
  loading: boolean
  saving: boolean
  error?: string
  load: () => Promise<void>
  toggleShop: (key: ShopKey, value: boolean) => void
  setTeamTrialsBanner: (slot: 1 | 2 | 3) => void
  save: () => Promise<NavPrefs>
  resetError: () => void
}

const defaultPrefs = (): NavPrefs => ({
  shop: { ...DEFAULT_PREFS.shop },
  team_trials: { ...DEFAULT_PREFS.team_trials },
})

const mergeWithDefaults = (prefs: NavPrefs | undefined): NavPrefs => ({
  shop: {
    alarm_clock: prefs?.shop?.alarm_clock ?? DEFAULT_PREFS.shop.alarm_clock,
    star_pieces: prefs?.shop?.star_pieces ?? DEFAULT_PREFS.shop.star_pieces,
    parfait: prefs?.shop?.parfait ?? DEFAULT_PREFS.shop.parfait,
  },
  team_trials: {
    preferred_banner: prefs?.team_trials?.preferred_banner ?? DEFAULT_PREFS.team_trials.preferred_banner,
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
  toggleShop: (key, value) =>
    set((state) => ({
      prefs: {
        ...state.prefs,
        shop: {
          ...state.prefs.shop,
          [key]: value,
        },
      },
      error: undefined,
    })),
  setTeamTrialsBanner: (slot) =>
    set((state) => ({
      prefs: {
        ...state.prefs,
        team_trials: {
          preferred_banner: slot,
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
