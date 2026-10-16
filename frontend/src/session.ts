/**
 * Per-room guest identity kept in localStorage (SPEC §3). Storage can be unavailable (private
 * mode, blocked site data), so every access is guarded and failures fall back to "no session".
 */

export type StoredSession = { participantId: string; token: string }

const key = (code: string) => `tot:session:${code.toUpperCase()}`

export function loadSession(code: string): StoredSession | null {
  try {
    const raw = localStorage.getItem(key(code))
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return typeof parsed?.token === 'string' && typeof parsed?.participantId === 'string'
      ? { participantId: parsed.participantId, token: parsed.token }
      : null
  } catch {
    return null
  }
}

export function saveSession(code: string, session: StoredSession): void {
  try {
    localStorage.setItem(key(code), JSON.stringify(session))
  } catch {
    // Without storage the session lasts only for this page view.
  }
}

export function clearSession(code: string): void {
  try {
    localStorage.removeItem(key(code))
  } catch {
    // Nothing to clear.
  }
}
