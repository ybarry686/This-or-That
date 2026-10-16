import { screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { loadSession } from '../session'
import {
  HOST_ME,
  installFakeWebSocket,
  jsonError,
  makeSnapshot,
  mockApi,
  renderRoute,
} from '../test/helpers'

beforeEach(() => {
  installFakeWebSocket()
})

afterEach(() => {
  localStorage.clear()
  window.location.hash = ''
  vi.unstubAllGlobals()
})

describe('host recovery link', () => {
  it('exchanges the recovery token for a new host session', async () => {
    window.location.hash = '#secret-recovery'
    const { calls } = mockApi({
      'POST /api/rooms/ABC234/host/recover': () => ({
        code: 'ABC234',
        participant_id: 'p-host',
        nickname: 'Host',
        token: 'fresh-token',
      }),
      'GET /api/rooms/ABC234': () => makeSnapshot({ me: HOST_ME, contenders: [] }),
    })
    renderRoute('/r/ABC234/recover')

    expect(await screen.findByRole('heading', { name: 'Where should we eat?' })).toBeInTheDocument()
    expect(calls[0].body).toEqual({ recovery_token: 'secret-recovery' })
    expect(loadSession('ABC234')).toEqual({ participantId: 'p-host', token: 'fresh-token' })
  })

  it('explains an invalid link', async () => {
    window.location.hash = '#wrong'
    mockApi({
      'POST /api/rooms/ABC234/host/recover': () => jsonError(401, 'Invalid host recovery token.'),
    })
    renderRoute('/r/ABC234/recover')

    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid host recovery token.')
  })
})
