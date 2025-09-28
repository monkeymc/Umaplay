import type { EventPrefs, EventKey } from '@/types/events'

export function pickFor(
  prefs: EventPrefs,
  keyStepAware: EventKey,
  legacyKey: EventKey | null,
  eventDefault?: number,
  type: 'support'|'trainee'|'scenario' = 'support'
): number {
  // 1) exact override step-aware
  if (prefs.overrides[keyStepAware] != null) return prefs.overrides[keyStepAware]
  // 2) legacy key
  if (legacyKey && prefs.overrides[legacyKey] != null) return prefs.overrides[legacyKey]
  // 3) wildcard patterns
  for (const { pattern, pick } of prefs.patterns) {
    if (minimatch(keyStepAware, pattern)) return pick
    if (legacyKey && minimatch(legacyKey, pattern)) return pick
  }
  // 4) event default
  if (eventDefault != null) return eventDefault
  // 5) type default
  return prefs.defaults[type] ?? 1
}

// super-light minimatch (asterisk-only) to avoid bringing a full lib
function minimatch(text: string, patt: string): boolean {
  if (!patt.includes('*')) return text === patt
  const parts = patt.split('*').map(s => s.trim()).filter(Boolean)
  let idx = 0
  for (const part of parts) {
    const found = text.indexOf(part, idx)
    if (found === -1) return false
    idx = found + part.length
  }
  return true
}
