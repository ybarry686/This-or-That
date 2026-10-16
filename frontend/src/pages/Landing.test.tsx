import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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
  vi.unstubAllGlobals()
})

describe('Landing page', () => {
  it('creates a room, stores the session and opens the lobby with the recovery link', async () => {
    const user = userEvent.setup()
    const { calls } = mockApi({
      'POST /api/rooms': () => ({
        code: 'ABC234',
        participant_id: 'p-host',
        nickname: 'Ana',
        token: 'host-token',
        host_recovery_token: 'secret-recovery',
      }),
      'GET /api/rooms/ABC234': () => makeSnapshot({ me: HOST_ME, contenders: [] }),
    })
    renderRoute('/')

    await user.type(screen.getByLabelText(/question/i), 'Where should we eat?')
    await user.type(screen.getByLabelText(/your nickname/i, { selector: '#create-nickname' }), 'Ana')
    await user.click(screen.getByRole('button', { name: /create room/i }))

    expect(await screen.findByRole('heading', { name: 'Where should we eat?' })).toBeInTheDocument()
    expect(calls[0].body).toMatchObject({ title: 'Where should we eat?', nickname: 'Ana' })
    expect(loadSession('ABC234')).toEqual({ participantId: 'p-host', token: 'host-token' })
    expect(screen.getByText(/\/r\/ABC234\/recover#secret-recovery/)).toBeInTheDocument()
  })

  it('sends custom settings when changed', async () => {
    const user = userEvent.setup()
    const { calls } = mockApi({
      'POST /api/rooms': () => jsonError(422, 'nope'),
    })
    renderRoute('/')

    await user.type(screen.getByLabelText(/question/i), 'Movies?')
    await user.type(screen.getByLabelText(/your nickname/i, { selector: '#create-nickname' }), 'Ana')
    await user.clear(screen.getByLabelText(/vote timer/i))
    await user.type(screen.getByLabelText(/vote timer/i), '45')
    await user.click(screen.getByRole('button', { name: /create room/i }))

    expect(calls[0].body).toMatchObject({ settings: { vote_seconds: 45 } })
  })

  it('shows the server error when creation fails', async () => {
    const user = userEvent.setup()
    mockApi({ 'POST /api/rooms': () => jsonError(422, 'Title is required.') })
    renderRoute('/')

    await user.type(screen.getByLabelText(/question/i), 'x')
    await user.type(screen.getByLabelText(/your nickname/i, { selector: '#create-nickname' }), 'Ana')
    await user.click(screen.getByRole('button', { name: /create room/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Title is required.')
  })

  it('goes to a room by code', async () => {
    const user = userEvent.setup()
    mockApi({})
    renderRoute('/')

    await user.type(screen.getByLabelText(/room code/i), 'abc234')
    await user.click(screen.getByRole('button', { name: /^join$/i }))

    expect(await screen.findByRole('heading', { name: /join room ABC234/i })).toBeInTheDocument()
  })
})
