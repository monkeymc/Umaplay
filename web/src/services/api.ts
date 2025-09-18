import axios from 'axios'
import type { Skill, RacesMap } from '@/models/datasets'

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

export async function updateFromGithub(): Promise<{status:string; branch:string; steps:any[]}> {
  const r = await fetch('/admin/update', { method: 'POST' })
  if (!r.ok) {
    let msg = 'Update failed'
    try { const e = await r.json(); msg = e.detail?.message || e.detail || msg } catch {}
    throw new Error(msg)
  }
  return r.json()
}

export async function getVersion(): Promise<{version:string}> {
  const r = await fetch('/admin/version')
  if (!r.ok) throw new Error('version check failed')
  return r.json()
}

export async function checkUpdate(): Promise<any> {
  const r = await fetch('/admin/check_update')
  if (!r.ok) throw new Error('update check failed')
  return r.json()
}