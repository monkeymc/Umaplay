import { create } from 'zustand'
import { appConfigSchema, defaultAppConfig, defaultPreset } from '@/models/config.schema'
import type { AppConfig, GeneralConfig, Preset } from '@/models/types'

const LS_KEY = 'uma:config:v1'

type State = {
  config: AppConfig
  uiTheme: 'dark' | 'light'
  uiGeneralCollapsed: boolean
}

type Actions = {
  // general
  setGeneral: (patch: Partial<GeneralConfig>) => void

  // presets
  setActivePresetId: (id: string) => void
  addPreset: () => void
  copyPreset: (id: string) => void
  deletePreset: (id: string) => void
  renamePreset: (id: string, name: string) => void
  patchPreset: <K extends keyof Preset>(id: string, key: K, value: Preset[K]) => void

  // io
  replaceConfig: (cfg: AppConfig) => void
  saveLocal: () => void
  loadLocal: () => void
  exportJson: () => void
  importJson: (raw: unknown) => { ok: boolean; error?: string }

  // theme
  setUiTheme: (mode: 'dark' | 'light') => void

  setGeneralCollapsed: (v: boolean) => void
}

const newId = () => (crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2))

export const useConfigStore = create<State & Actions>((set, get) => ({
  config: defaultAppConfig(),
  uiTheme: 'light',
  uiGeneralCollapsed: false,

  // ---- general
  setGeneral: (patch) =>
    set((s) => ({ config: { ...s.config, general: { ...s.config.general, ...patch } } })),

  // ---- presets
  setActivePresetId: (id) =>
    set((s) => ({ config: { ...s.config, activePresetId: id } })),

  addPreset: () =>
    set((s) => {
      const preset = defaultPreset(newId(), `Preset ${s.config.presets.length + 1}`)
      return { config: { ...s.config, presets: [...s.config.presets, preset], activePresetId: preset.id } }
    }),

  copyPreset: (id) =>
    set((s) => {
      const src = s.config.presets.find((p) => p.id === id)
      if (!src) return {}
      const clone: Preset = { ...src, id: newId(), name: src.name + ' (copy)' }
      return { config: { ...s.config, presets: [...s.config.presets, clone], activePresetId: clone.id } }
    }),

  deletePreset: (id) =>
    set((s) => {
      const left = s.config.presets.filter((p) => p.id !== id)
      const nextActive = left[left.length - 1]?.id
      return { config: { ...s.config, presets: left.length ? left : [defaultPreset(newId(), 'Preset 1')], activePresetId: nextActive } }
    }),

  renamePreset: (id, name) =>
    set((s) => ({
      config: {
        ...s.config,
        presets: s.config.presets.map((p) => (p.id === id ? { ...p, name } : p)),
      },
    })),

  patchPreset: (id, key, value) =>
    set((s) => ({
      config: {
        ...s.config,
        presets: s.config.presets.map((p) => (p.id === id ? { ...p, [key]: value } : p)),
      },
    })),

  // ---- io
  replaceConfig: (cfg) => set({ config: cfg }),

  saveLocal: () => {
    const { config } = get()
    localStorage.setItem(LS_KEY, JSON.stringify(config))
  },

  loadLocal: () => {
    const raw = localStorage.getItem(LS_KEY)
    if (!raw) return
    try {
      const parsed = JSON.parse(raw)
      const safe = appConfigSchema.parse(parsed)
      set({ config: safe })
    } catch {
      // ignore
    }
  },

  exportJson: () => {
    const { config } = get()
    const data = JSON.parse(JSON.stringify(config))
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'config.json'
    a.click()
    URL.revokeObjectURL(url)
  },

  importJson: (raw) => {
    try {
      const safe = appConfigSchema.parse(raw)
      set({ config: safe })
      return { ok: true }
    } catch (e: any) {
      return { ok: false, error: String(e?.message || e) }
    }
  },

  // ---- theme
  setUiTheme: (mode) => set({ uiTheme: mode }),
  setGeneralCollapsed: (v: boolean) => set({ uiGeneralCollapsed: v }),
}))
