import axios from 'axios'
import type { Skill, RacesMap } from '@/models/datasets'
import type { EventsRoot } from '@/types/events'

export const api = axios.create({
  baseURL: '/', // vite proxy will forward /config and /api/* to 127.0.0.1:8000
  timeout: 15000,
})

export const fetchServerConfig = async (): Promise<Record<string, unknown>> => {
  const { data } = await api.get('/config')
  return data
}

export const fetchSkills = async (): Promise<Skill[]> => {
  try {
    const { data } = await api.get('/api/skills')
    return Array.isArray(data) ? data : []
  } catch {
    return [] // graceful when backend route not ready
  }
}

export const fetchRaces = async (): Promise<RacesMap> => {
  try {
    const { data } = await api.get('/api/races')
    return data || {}
  } catch {
    return {}
  }
}

// Save whole app config to backend (server writes root config.json)
export async function saveServerConfig(payload: unknown): Promise<void> {
  const r = await fetch('/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!r.ok) {
    const msg = await r.text().catch(() => '')
    throw new Error(`Failed to save config: ${r.status} ${msg}`)
  }
}

// --- Admin / Update helpers
export async function getVersion(): Promise<{ version: string }> {
  const r = await fetch('/admin/version')
  if (!r.ok) throw new Error('Failed to fetch version')
  return r.json()
}

export async function updateFromGithub(): Promise<any> {
  const r = await fetch('/admin/update', { method: 'POST' })
  if (!r.ok) throw new Error('Update failed')
  return r.json()
}

export async function forceUpdate(): Promise<any> {
  const r = await fetch('/admin/force_update', { method: 'POST' })
  if (!r.ok) {
    const txt = await r.text().catch(() => '')
    throw new Error(txt || 'Force update failed')
  }
  return r.json()
}

export async function checkUpdate(): Promise<any> {
  const r = await fetch('/admin/check_update')
  if (!r.ok) throw new Error('update check failed')
  return r.json()
}

export const fetchEvents = async (): Promise<EventsRoot> => {
  try {
    const { data } = await api.get('/api/events')
    return Array.isArray(data) ? data : []
  } catch {
    return []
  }
}

// Config (existing)
export async function fetchConfig() {
  const res = await fetch('/config', { cache: 'no-store' })
  if (!res.ok) throw new Error('Failed to load config')
  return res.json()
}

export async function saveConfig(cfg: any) {
  const res = await fetch('/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cfg),
  })
  if (!res.ok) throw new Error('Failed to save config')
  return res.json()
}

// Focused preset event_setup endpoints
import type { EventSetup } from '@/types/events'

export async function fetchPresetEventSetup(presetId: string): Promise<Partial<EventSetup>> {
  const res = await fetch(`/api/presets/${encodeURIComponent(presetId)}/event_setup`, { cache: 'no-store' })
  if (res.status === 404) return {}
  if (!res.ok) throw new Error('Failed to load preset event setup')
  return res.json()
}

export async function savePresetEventSetup(presetId: string, setup: EventSetup) {
  const res = await fetch(`/api/presets/${encodeURIComponent(presetId)}/event_setup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(setup),
  })
  if (!res.ok) throw new Error('Failed to save preset event setup')
  return res.json()
}