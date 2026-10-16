import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { loadSession, saveSession } from '../session'
import {
  FakeWebSocket,
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

describe('joining', () => {
  it('asks for a nickname when there is no stored session, then shows the lobby', async () => {
    const user = userEvent.setup()
    const { calls } = mockApi({
      'POST /api/rooms/ABC234/join': () => ({
        code: 'ABC234',
        participant_id: 'p-guest',
        nickname: 'Sam',
        token: 'guest-token',
      }),
      'GET /api/rooms/ABC234': () => makeSnapshot(),
    })
    renderRoute('/r/ABC234')

    await user.type(screen.getByLabelText(/your nickname/i), 'Sam')
    await user.click(screen.getByRole('button', { name: /join/i }))

    expect(await screen.findByRole('heading', { name: 'Where should we eat?' })).toBeInTheDocument()
    expect(calls[0].body).toEqual({ nickname: 'Sam' })
    expect(loadSession('ABC234')).toEqual({ participantId: 'p-guest', token: 'guest-token' })
  })

  it('shows why joining failed', async () => {
    const user = userEvent.setup()
    mockApi({ 'POST /api/rooms/ABC234/join': () => jsonError(409, 'This room is full.') })
    renderRoute('/r/ABC234')

    await user.type(screen.getByLabelText(/your nickname/i), 'Sam')
    await user.click(screen.getByRole('button', { name: /join/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('This room is full.')
  })

  it('drops a rejected stored token and asks to join again', async () => {
    saveSession('ABC234', { participantId: 'p-old', token: 'stale' })
    mockApi({ 'GET /api/rooms/ABC234': () => jsonError(401, 'Invalid participant token.') })
    renderRoute('/r/ABC234')

    expect(await screen.findByRole('heading', { name: /join room ABC234/i })).toBeInTheDocument()
    expect(loadSession('ABC234')).toBeNull()
  })
})

describe('lobby (guest)', () => {
  beforeEach(() => {
    saveSession('ABC234', { participantId: 'p-guest', token: 'guest-token' })
  })

  it('shows room info, participants, presence and the option count', async () => {
    mockApi({
      'GET /api/rooms/ABC234': () =>
        makeSnapshot({ description: 'Friday night', option_count: 4 }),
    })
    renderRoute('/r/ABC234')

    expect(await screen.findByRole('heading', { name: 'Where should we eat?' })).toBeInTheDocument()
    expect(screen.getByText('Friday night')).toBeInTheDocument()
    expect(screen.getByText('ABC234')).toBeInTheDocument()
    const people = within(screen.getByRole('list', { name: /players/i }))
    expect(people.getByText('Host')).toBeInTheDocument()
    expect(people.getByText(/host/i, { selector: '.badge' })).toBeInTheDocument()
    expect(people.getByText('Sam')).toBeInTheDocument()
    expect(people.getByLabelText('Host is online')).toBeInTheDocument()
    expect(people.getByLabelText('Sam is offline')).toBeInTheDocument()
    expect(screen.getByText(/4 options submitted/i)).toBeInTheDocument()
  })

  it('submits an option and refreshes', async () => {
    const user = userEvent.setup()
    let mine = [] as { id: string; text: string }[]
    const { calls } = mockApi({
      'GET /api/rooms/ABC234': () => makeSnapshot({ my_submissions: mine }),
      'POST /api/rooms/ABC234/submissions': (body) => {
        mine = [{ id: 's1', text: (body as { text: string }).text }]
        return mine[0]
      },
    })
    renderRoute('/r/ABC234')

    const input = await screen.findByRole('textbox', { name: /your option/i })
    await user.type(input, 'Pizza')
    await user.click(screen.getByRole('button', { name: /add option/i }))

    const list = within(await screen.findByRole('list', { name: /your options/i }))
    expect(await list.findByText('Pizza')).toBeInTheDocument()
    expect(input).toHaveValue('')
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ text: 'Pizza' })
    expect(screen.getByText(/1 of 3 used/i)).toBeInTheDocument()
  })

  it('disables submitting once the limit is reached', async () => {
    mockApi({
      'GET /api/rooms/ABC234': () =>
        makeSnapshot({
          settings: { max_participants: 20, max_submissions: 1, vote_seconds: 30 },
          my_submissions: [{ id: 's1', text: 'Pizza' }],
        }),
    })
    renderRoute('/r/ABC234')

    expect(await screen.findByRole('button', { name: /add option/i })).toBeDisabled()
  })

  it('removes one of my options', async () => {
    const user = userEvent.setup()
    const { calls } = mockApi({
      'GET /api/rooms/ABC234': () => makeSnapshot({ my_submissions: [{ id: 's1', text: 'Pizza' }] }),
      'DELETE /api/rooms/ABC234/submissions/s1': () => undefined,
    })
    renderRoute('/r/ABC234')

    await user.click(await screen.findByRole('button', { name: /remove pizza/i }))

    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE')).toBe(true))
  })

  it('shows a submission error', async () => {
    const user = userEvent.setup()
    mockApi({
      'GET /api/rooms/ABC234': () => makeSnapshot(),
      'POST /api/rooms/ABC234/submissions': () => jsonError(422, 'Option text cannot be empty.'),
    })
    renderRoute('/r/ABC234')

    await user.type(await screen.findByRole('textbox', { name: /your option/i }), '!!!')
    await user.click(screen.getByRole('button', { name: /add option/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Option text cannot be empty.')
  })

  it('does not show host controls', async () => {
    mockApi({ 'GET /api/rooms/ABC234': () => makeSnapshot() })
    renderRoute('/r/ABC234')

    await screen.findByRole('heading', { name: 'Where should we eat?' })
    expect(screen.queryByRole('heading', { name: /all options/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /settings/i })).not.toBeInTheDocument()
  })
})

describe('lobby (host)', () => {
  beforeEach(() => {
    saveSession('ABC234', { participantId: 'p-host', token: 'host-token' })
  })

  const contenders = [
    {
      key: 'pizza',
      display_text: 'Pizza',
      submissions: [
        { id: 's1', text: 'Pizza', participant_id: 'p-host' },
        { id: 's2', text: 'pizza!', participant_id: 'p-guest' },
      ],
    },
    {
      key: 'pizza hut',
      display_text: 'Pizza Hut',
      submissions: [{ id: 's3', text: 'Pizza Hut', participant_id: 'p-guest' }],
    },
  ]

  it('lists every option with who submitted it', async () => {
    mockApi({
      'GET /api/rooms/ABC234': () => makeSnapshot({ me: HOST_ME, contenders, option_count: 2 }),
    })
    renderRoute('/r/ABC234')

    const options = within(await screen.findByRole('list', { name: /all options/i }))
    expect(options.getByText('Pizza', { selector: 'span' })).toBeInTheDocument()
    expect(options.getByText(/Host, Sam/)).toBeInTheDocument()
  })

  it('merges one option into another', async () => {
    const user = userEvent.setup()
    const { calls } = mockApi({
      'GET /api/rooms/ABC234': () => makeSnapshot({ me: HOST_ME, contenders, option_count: 2 }),
      'POST /api/rooms/ABC234/contenders/merge': () => null,
    })
    renderRoute('/r/ABC234')

    await user.selectOptions(
      await screen.findByLabelText(/merge pizza hut into/i),
      'pizza',
    )

    await waitFor(() =>
      expect(calls.find((c) => c.path.endsWith('/merge'))?.body).toEqual({
        source_key: 'pizza hut',
        target_key: 'pizza',
      }),
    )
  })

  it('removes an option', async () => {
    const user = userEvent.setup()
    const { calls } = mockApi({
      'GET /api/rooms/ABC234': () => makeSnapshot({ me: HOST_ME, contenders, option_count: 2 }),
      'POST /api/rooms/ABC234/contenders/remove': () => null,
    })
    renderRoute('/r/ABC234')

    const options = within(await screen.findByRole('list', { name: /all options/i }))
    await user.click(options.getByRole('button', { name: /remove option pizza hut/i }))

    await waitFor(() =>
      expect(calls.find((c) => c.path.endsWith('/remove'))?.body).toEqual({ key: 'pizza hut' }),
    )
  })

  it('saves settings', async () => {
    const user = userEvent.setup()
    const { calls } = mockApi({
      'GET /api/rooms/ABC234': () => makeSnapshot({ me: HOST_ME, contenders: [] }),
      'PATCH /api/rooms/ABC234': () => ({ max_participants: 20, max_submissions: 5, vote_seconds: 30 }),
    })
    renderRoute('/r/ABC234')

    const perPerson = await screen.findByLabelText(/options per person/i)
    await user.clear(perPerson)
    await user.type(perPerson, '5')
    await user.click(screen.getByRole('button', { name: /save settings/i }))

    await waitFor(() =>
      expect(calls.find((c) => c.method === 'PATCH')?.body).toMatchObject({ max_submissions: 5 }),
    )
  })

  it('makes another player host', async () => {
    const user = userEvent.setup()
    const { calls } = mockApi({
      'GET /api/rooms/ABC234': () => makeSnapshot({ me: HOST_ME, contenders: [] }),
      'POST /api/rooms/ABC234/host/transfer': () => null,
    })
    renderRoute('/r/ABC234')

    await user.click(await screen.findByRole('button', { name: /make sam host/i }))

    await waitFor(() =>
      expect(calls.find((c) => c.path.endsWith('/transfer'))?.body).toEqual({
        participant_id: 'p-guest',
      }),
    )
  })
})

describe('realtime', () => {
  beforeEach(() => {
    saveSession('ABC234', { participantId: 'p-guest', token: 'guest-token' })
  })

  it('connects with the token and refetches the snapshot on events', async () => {
    let count = 1
    mockApi({ 'GET /api/rooms/ABC234': () => makeSnapshot({ option_count: count }) })
    renderRoute('/r/ABC234')
    await screen.findByText(/1 option submitted/i)

    const socket = FakeWebSocket.latest()
    expect(socket.url).toMatch(/\/api\/rooms\/ABC234\/ws\?token=guest-token$/)

    count = 2
    socket.emit({ type: 'submissions_changed', version: 4, data: { option_count: 2 } })

    expect(await screen.findByText(/2 options submitted/i)).toBeInTheDocument()
  })

  it('reconnects after the connection drops', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      mockApi({ 'GET /api/rooms/ABC234': () => makeSnapshot() })
      renderRoute('/r/ABC234')
      await screen.findByRole('heading', { name: 'Where should we eat?' })
      const first = FakeWebSocket.latest()

      first.serverClose()
      await vi.advanceTimersByTimeAsync(5000)

      expect(FakeWebSocket.instances.length).toBeGreaterThan(1)
      expect(FakeWebSocket.latest()).not.toBe(first)
    } finally {
      vi.useRealTimers()
    }
  })
})
