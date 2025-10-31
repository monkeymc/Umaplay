import { create } from 'zustand'
import { appConfigSchema, defaultAppConfig, defaultPreset, defaultEventSetup } from '@/models/config.schema'
import type { AppConfig, GeneralConfig, Preset } from '@/models/types'

const LS_KEY = 'uma:config:v1'

type State = {
  config: AppConfig
  uiTheme: 'dark' | 'light'
  uiGeneralCollapsed: boolean
  uiSelectedPresetId?: string
}

type Actions = {
  // general
  setGeneral: (patch: Partial<GeneralConfig>) => void

  // presets
  setActivePresetId: (id: string) => void
  setSelectedPresetId: (id: string) => void
  getActivePreset: () => { id: string | undefined; preset: Preset | undefined }
  getSelectedPreset: () => { id: string | undefined; preset: Preset | undefined }
  commitSelectedPreset: () => void
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
  uiSelectedPresetId: undefined,

  // ---- general
  setGeneral: (patch) =>
    set((s) => ({ config: { ...s.config, general: { ...s.config.general, ...patch } } })),

  // ---- presets
  setActivePresetId: (id) =>
    set((s) => ({
      config: {
        ...s.config,
        activePresetId: id,
      },
    })),

  setSelectedPresetId: (id) => set({ uiSelectedPresetId: id }),

  getActivePreset: () => {
    const { config } = get()
    const activeId = config.activePresetId ?? config.presets[0]?.id
    return {
      id: activeId,
      preset: activeId ? config.presets.find((p) => p.id === activeId) : undefined,
    }
  },

  getSelectedPreset: () => {
    const { config, uiSelectedPresetId } = get()
    const selectedId = uiSelectedPresetId ?? config.activePresetId ?? config.presets[0]?.id
    return {
      id: selectedId,
      preset: selectedId ? config.presets.find((p) => p.id === selectedId) : undefined,
    }
  },

  commitSelectedPreset: () =>
    set((s) => {
      const selectedId = s.uiSelectedPresetId ?? s.config.activePresetId ?? s.config.presets[0]?.id
      if (!selectedId) return {}
      return {
        config: {
          ...s.config,
          activePresetId: selectedId,
        },
        uiSelectedPresetId: selectedId,
      }
    }),

  addPreset: () =>
    set((s) => {
      // Make sure event_setup is a fresh object for every preset
      const base = defaultPreset(newId(), `Preset ${s.config.presets.length + 1}`)
      const preset: Preset = { ...base, event_setup: defaultEventSetup() }
      return {
        config: { ...s.config, presets: [...s.config.presets, preset] },
        uiSelectedPresetId: preset.id,
      }
    }),

  copyPreset: (id) =>
    set((s) => {
      const src = s.config.presets.find((p) => p.id === id)
      if (!src) return {}
      // Deep-clone event_setup so copies don’t share references
      const clone: Preset = {
        ...src,
        id: newId(),
        name: src.name + ' (copy)',
        event_setup: JSON.parse(JSON.stringify(src.event_setup ?? defaultEventSetup())),
      }
      return {
        config: { ...s.config, presets: [...s.config.presets, clone] },
        uiSelectedPresetId: clone.id,
      }
    }),

  deletePreset: (id) =>
    set((s) => {
      const left = s.config.presets.filter((p) => p.id !== id)
      let presets: Preset[]
      if (left.length) {
        presets = left
      } else {
        const fallback: Preset = { ...defaultPreset(newId(), 'Preset 1'), event_setup: defaultEventSetup() }
        presets = [fallback]
      }
      const nextSelected = presets[presets.length - 1]?.id
      let nextActive = s.config.activePresetId
      if (!nextActive || !presets.find((p) => p.id === nextActive)) {
        nextActive = nextSelected
      }
      return {
        config: { ...s.config, presets, activePresetId: nextActive },
        uiSelectedPresetId: nextSelected,
      }
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
  replaceConfig: (cfg) => set(() => {
    // Normalize presets, migrate prioritizeHint from general -> preset if needed
    const migrated = (() => {
      const fallbackSkillPts = Number((cfg.general as any)?.skillPtsCheck ?? 600)
      const presets = (cfg.presets || []).map((p) => ({
        ...p,
        event_setup: p.event_setup ?? defaultEventSetup(),
        prioritizeHint: typeof p.prioritizeHint === 'boolean' ? p.prioritizeHint : (cfg.general as any)?.prioritizeHint ?? false,
        skillPtsCheck: Number.isFinite(Number(p.skillPtsCheck))
          ? Math.max(0, Number(p.skillPtsCheck))
          : Math.max(0, fallbackSkillPts),
      }))
      const activeId = cfg.activePresetId ?? presets[0]?.id
      const active = presets.find((p) => p.id === activeId)
      // Mirror back to general for backward compat on-disk
      const general = { ...cfg.general, prioritizeHint: active ? !!active.prioritizeHint : (cfg.general as any)?.prioritizeHint ?? false }
      return { ...cfg, general, presets, activePresetId: active?.id ?? presets[0]?.id }
    })()
    return { config: migrated, uiSelectedPresetId: migrated.activePresetId }
  }),

  saveLocal: () => {
    const { config, getActivePreset } = get()
    const { id: activeId, preset: active } = getActivePreset()
    const data = JSON.parse(JSON.stringify(config)) as AppConfig
    data.activePresetId = active?.id ?? activeId ?? config.presets[0]?.id
    // Mirror active preset's prioritizeHint into general for backward compat
    ;(data.general as any).prioritizeHint = active ? !!active.prioritizeHint : (data.general as any)?.prioritizeHint ?? false
    ;(data.general as any).skillPtsCheck = active?.skillPtsCheck ?? (data.general as any)?.skillPtsCheck ?? 600
    localStorage.setItem(LS_KEY, JSON.stringify(data))
  },

  loadLocal: () => {
    const raw = localStorage.getItem(LS_KEY)
    console.log(LS_KEY, raw)
    if (!raw) return
    try {
      const parsed = JSON.parse(raw)
      const safe = appConfigSchema.parse(parsed)
      // Migrate general.prioritizeHint -> preset.prioritizeHint, and mirror back
      const fallbackSkillPts = Number((safe.general as any)?.skillPtsCheck ?? 600)
      const presets = safe.presets.map((p) => ({
        ...p,
        event_setup: p.event_setup ?? defaultEventSetup(),
        prioritizeHint: typeof p.prioritizeHint === 'boolean' ? p.prioritizeHint : (safe.general as any)?.prioritizeHint ?? false,
        skillPtsCheck: Number.isFinite(Number(p.skillPtsCheck))
          ? Math.max(0, Number(p.skillPtsCheck))
          : Math.max(0, fallbackSkillPts),
      }))
      const activeId = safe.activePresetId ?? presets[0]?.id
      const active = presets.find((p) => p.id === activeId)
      const general = { ...safe.general, prioritizeHint: active ? !!active.prioritizeHint : (safe.general as any)?.prioritizeHint ?? false }
      ;(general as any).skillPtsCheck = active?.skillPtsCheck ?? Math.max(0, fallbackSkillPts)
      set({ config: { ...safe, general, presets, activePresetId: active?.id ?? presets[0]?.id }, uiSelectedPresetId: active?.id ?? presets[0]?.id })
    } catch {
      // ignore
    }
  },

  exportJson: () => {
    const { config, getActivePreset } = get()
    const data = JSON.parse(JSON.stringify(config)) as AppConfig
    const { id: activeId, preset: active } = getActivePreset()
    data.activePresetId = active?.id ?? activeId ?? data.presets[0]?.id
    // Mirror active preset's prioritizeHint into general for backward compat
    ;(data.general as any).prioritizeHint = active ? !!active.prioritizeHint : (data.general as any)?.prioritizeHint ?? false
    ;(data.general as any).skillPtsCheck = active?.skillPtsCheck ?? (data.general as any)?.skillPtsCheck ?? 600
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
      // Normalize + migrate prioritizeHint
      const fallbackSkillPts = Number((safe.general as any)?.skillPtsCheck ?? 600)
      const presets = safe.presets.map((p) => ({
        ...p,
        event_setup: p.event_setup ?? defaultEventSetup(),
        prioritizeHint: typeof p.prioritizeHint === 'boolean' ? p.prioritizeHint : (safe.general as any)?.prioritizeHint ?? false,
        skillPtsCheck: Number.isFinite(Number(p.skillPtsCheck))
          ? Math.max(0, Number(p.skillPtsCheck))
          : Math.max(0, fallbackSkillPts),
      }))
      const activeId = safe.activePresetId ?? presets[0]?.id
      const active = presets.find((p) => p.id === activeId)
      const general = { ...safe.general, prioritizeHint: active ? !!active.prioritizeHint : (safe.general as any)?.prioritizeHint ?? false }
      ;(general as any).skillPtsCheck = active?.skillPtsCheck ?? Math.max(0, fallbackSkillPts)
      const normalized: AppConfig = { ...safe, general, presets, activePresetId: active?.id ?? presets[0]?.id }
      set({ config: normalized, uiSelectedPresetId: normalized.activePresetId })
      return { ok: true }
    } catch (e: any) {
      return { ok: false, error: String(e?.message || e) }
    }
  },

  // ---- theme
  setUiTheme: (mode) => set({ uiTheme: mode }),
  setGeneralCollapsed: (v: boolean) => set({ uiGeneralCollapsed: v }),
}))
