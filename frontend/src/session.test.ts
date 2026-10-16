import { afterEach, describe, expect, it, vi } from 'vitest'
import { clearSession, loadSession, saveSession } from './session'

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

describe('session storage', () => {
  it('saves and loads a session per room code', () => {
    saveSession('ABC234', { participantId: 'p1', token: 't1' })

    expect(loadSession('ABC234')).toEqual({ participantId: 'p1', token: 't1' })
    expect(loadSession('abc234')).toEqual({ participantId: 'p1', token: 't1' })
    expect(loadSession('ZZZZZZ')).toBeNull()
  })

  it('clears a session', () => {
    saveSession('ABC234', { participantId: 'p1', token: 't1' })
    clearSession('ABC234')

    expect(loadSession('ABC234')).toBeNull()
  })

  it('returns null for corrupt data', () => {
    localStorage.setItem('tot:session:ABC234', '{not json')

    expect(loadSession('ABC234')).toBeNull()
  })

  it('does not throw when storage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })

    expect(() => saveSession('ABC234', { participantId: 'p', token: 't' })).not.toThrow()
    expect(loadSession('ABC234')).toBeNull()
  })
})
