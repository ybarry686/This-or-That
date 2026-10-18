import { useSyncExternalStore } from 'react'

/**
 * Per-device presentation settings (SPEC §10): audio is off until the player turns it on, and
 * motion follows the system's reduced-motion preference unless overridden here.
 */
export type Settings = {
  sound: boolean
  music: boolean
  crt: boolean
  /** null = follow the system preference. */
  reduceMotion: boolean | null
}

const STORAGE_KEY = 'tot:settings'
const DEFAULTS: Settings = { sound: false, music: false, crt: true, reduceMotion: null }

function load(): Settings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULTS
    const parsed = JSON.parse(raw)
    const pick = <K extends keyof Settings>(key: K, valid: (v: unknown) => boolean): Settings[K] =>
      valid(parsed?.[key]) ? parsed[key] : DEFAULTS[key]
    const isBool = (v: unknown) => typeof v === 'boolean'
    return {
      sound: pick('sound', isBool),
      music: pick('music', isBool),
      crt: pick('crt', isBool),
      reduceMotion: pick('reduceMotion', (v) => v === null || isBool(v)),
    }
  } catch {
    return DEFAULTS
  }
}

let current: Settings = load()
const listeners = new Set<() => void>()

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function getSettings(): Settings {
  return current
}

export function setSetting<K extends keyof Settings>(key: K, value: Settings[K]) {
  current = { ...current, [key]: value }
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(current))
  } catch {
    // Without storage the setting lasts until the page is reloaded.
  }
  listeners.forEach((listener) => listener())
}

export function resetSettingsForTests() {
  current = load()
  listeners.forEach((listener) => listener())
}

export function useSettings(): Settings {
  return useSyncExternalStore(subscribe, getSettings)
}

const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)'

function subscribeToSystemMotion(listener: () => void) {
  if (typeof window.matchMedia !== 'function') return () => {}
  const query = window.matchMedia(REDUCED_MOTION_QUERY)
  query.addEventListener?.('change', listener)
  return () => query.removeEventListener?.('change', listener)
}

function systemPrefersReducedMotion() {
  return typeof window.matchMedia === 'function' && window.matchMedia(REDUCED_MOTION_QUERY).matches
}

export function useReducedMotion(): boolean {
  const { reduceMotion } = useSettings()
  const system = useSyncExternalStore(subscribeToSystemMotion, systemPrefersReducedMotion)
  return reduceMotion ?? system
}
