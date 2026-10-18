import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { loadSession, saveSession } from '../session'
import {
  HOST_ME,
  installFakeWebSocket,
  jsonError,
  makeTournamentSnapshot,
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

function finishedTournament() {
  const t = makeTournamentSnapshot({}, { current: null, champion_id: 'c-pizza' }).tournament!
  t.rounds[0][0] = { ...t.rounds[0][0], status: 'decided', winner_id: 'c-pizza', outcome: 'votes', votes_a: 2, votes_b: 1 }
  t.rounds[0][1] = { ...t.rounds[0][1], status: 'decided', winner_id: 'c-sushi', outcome: 'coin_flip' }
  t.rounds[1][0] = {
    ...t.rounds[1][0],
    contender_a_id: 'c-pizza',
    contender_b_id: 'c-sushi',
    status: 'decided',
    winner_id: 'c-pizza',
    outcome: 'votes',
    votes_a: 3,
    votes_b: 0,
  }
  return t
}

function results(overrides = {}) {
  return {
    code: 'ABC234',
    title: 'Where should we eat?',
    description: 'Friday night',
    finished_at: '2026-10-17T12:05:00+00:00',
    participants: [
      { id: 'p-host', nickname: 'Host', avatar: 0 },
      { id: 'p-guest', nickname: 'Sam', avatar: 1 },
    ],
    tournament: finishedTournament(),
    rematch_code: null,
    ...overrides,
  }
}

describe('results page', () => {
  it('shows the question, champion, bracket and players without needing to have played', async () => {
    const { calls } = mockApi({ 'GET /api/rooms/ABC234/results': () => results() })
    renderRoute('/r/ABC234/results')

    expect(await screen.findByRole('heading', { name: 'Where should we eat?' })).toBeInTheDocument()
    expect(screen.getByText('Friday night')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /champion/i })).toHaveTextContent('Pizza')
    const bracket = screen.getByRole('region', { name: /bracket/i })
    expect(within(bracket).getAllByText('Sushi').length).toBeGreaterThan(0)
    expect(screen.getByText(/host, sam/i)).toBeInTheDocument()
    expect(calls[0].headers.get('Authorization')).toBeNull()
  })

  it('links to the rematch when there is one', async () => {
    mockApi({ 'GET /api/rooms/ABC234/results': () => results({ rematch_code: 'NEW234' }) })
    renderRoute('/r/ABC234/results')

    expect(await screen.findByRole('link', { name: /rematch/i })).toHaveAttribute('href', '/r/NEW234')
  })

  it('explains when the game has not finished yet', async () => {
    mockApi({
      'GET /api/rooms/ABC234/results': () => jsonError(409, 'Results are available once the tournament finishes.'),
    })
    renderRoute('/r/ABC234/results')

    expect(await screen.findByRole('alert')).toHaveTextContent(/once the tournament finishes/i)
    expect(screen.getByRole('link', { name: /go to the room/i })).toHaveAttribute('href', '/r/ABC234')
  })

  it('explains when results no longer exist', async () => {
    mockApi({ 'GET /api/rooms/ABC234/results': () => jsonError(404, 'Room not found.') })
    renderRoute('/r/ABC234/results')

    expect(await screen.findByRole('alert')).toHaveTextContent(/kept for 30 days/i)
  })
})

describe('after the champion is crowned', () => {
  function finishedSnapshot(overrides = {}) {
    return makeTournamentSnapshot(
      { status: 'finished', finished_at: '2026-10-17T12:05:00+00:00', ...overrides },
      { ...finishedTournament() },
    )
  }

  it('links to the shareable results page', async () => {
    saveSession('ABC234', { participantId: 'p-guest', token: 'guest-token' })
    mockApi({ 'GET /api/rooms/ABC234': () => finishedSnapshot() })
    renderRoute('/r/ABC234')

    expect(await screen.findByRole('link', { name: /view results/i })).toHaveAttribute('href', '/r/ABC234/results')
    expect(screen.getByRole('button', { name: /copy results link/i })).toBeInTheDocument()
  })

  it('lets the host start a rematch and moves them into the new lobby', async () => {
    saveSession('ABC234', { participantId: 'p-host', token: 'host-token' })
    const user = userEvent.setup()
    mockApi({
      'GET /api/rooms/ABC234': () => finishedSnapshot({ me: HOST_ME }),
      'POST /api/rooms/ABC234/rematch': () => ({
        code: 'NEW234',
        participant_id: 'p-host-2',
        nickname: 'Host',
        token: 'new-host-token',
        host_recovery_token: 'new-recovery',
      }),
      'GET /api/rooms/NEW234': () =>
        makeTournamentSnapshot({ code: 'NEW234', status: 'lobby', me: HOST_ME, contenders: [] }, {}),
    })
    renderRoute('/r/ABC234')

    await user.click(await screen.findByRole('button', { name: /play again/i }))

    await waitFor(() => expect(loadSession('NEW234')).toEqual({ participantId: 'p-host-2', token: 'new-host-token' }))
    expect(await screen.findByText(/new-recovery/)).toBeInTheDocument()
  })

  it('tells guests to wait for the host until a rematch exists', async () => {
    saveSession('ABC234', { participantId: 'p-guest', token: 'guest-token' })
    mockApi({ 'GET /api/rooms/ABC234': () => finishedSnapshot() })
    renderRoute('/r/ABC234')

    expect(await screen.findByText(/waiting for the host/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /play again/i })).not.toBeInTheDocument()
  })

  it('lets guests join the rematch with their nickname in one click', async () => {
    saveSession('ABC234', { participantId: 'p-guest', token: 'guest-token' })
    const user = userEvent.setup()
    const { calls } = mockApi({
      'GET /api/rooms/ABC234': () => finishedSnapshot({ rematch_code: 'NEW234' }),
      'POST /api/rooms/NEW234/join': () => ({
        code: 'NEW234',
        participant_id: 'p-guest-2',
        nickname: 'Sam',
        token: 'new-guest-token',
      }),
      'GET /api/rooms/NEW234': () => makeTournamentSnapshot({ code: 'NEW234', status: 'lobby' }, {}),
    })
    renderRoute('/r/ABC234')

    await user.click(await screen.findByRole('button', { name: /join the rematch/i }))

    await waitFor(() => expect(loadSession('NEW234')?.token).toBe('new-guest-token'))
    expect(calls.find((c) => c.path.endsWith('/NEW234/join'))?.body).toEqual({ nickname: 'Sam' })
  })
})

describe('expired rooms', () => {
  it('says the room expired instead of showing a lobby', async () => {
    saveSession('ABC234', { participantId: 'p-guest', token: 'guest-token' })
    mockApi({ 'GET /api/rooms/ABC234': () => makeTournamentSnapshot({ status: 'expired', tournament: null }, {}) })
    renderRoute('/r/ABC234')

    expect(await screen.findByText(/this room expired/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /add option/i })).not.toBeInTheDocument()
  })
})
