import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { RoomSnapshot } from '../api/client'
import { audio } from '../audio'
import { saveSession } from '../session'
import {
  HOST_ME,
  installFakeWebSocket,
  jsonError,
  makeMatchup,
  makeSnapshot,
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

function asGuest() {
  saveSession('ABC234', { participantId: 'p-guest', token: 'guest-token' })
}

function asHost() {
  saveSession('ABC234', { participantId: 'p-host', token: 'host-token' })
}

function serve(snapshot: () => RoomSnapshot, extra: Parameters<typeof mockApi>[0] = {}) {
  return mockApi({ 'GET /api/rooms/ABC234': () => snapshot(), ...extra })
}

describe('starting the tournament', () => {
  beforeEach(asHost)

  it('is disabled with an explanation until there are two options', async () => {
    serve(() => makeSnapshot({ me: HOST_ME, contenders: [], option_count: 1 }))
    renderRoute('/r/ABC234')

    expect(await screen.findByRole('button', { name: /start tournament/i })).toBeDisabled()
    expect(screen.getByText(/at least 2 options/i)).toBeInTheDocument()
  })

  it('starts the tournament', async () => {
    const user = userEvent.setup()
    const { calls } = serve(() => makeSnapshot({ me: HOST_ME, contenders: [], option_count: 2 }), {
      'POST /api/rooms/ABC234/start': () => ({ status: 'in_progress' }),
    })
    renderRoute('/r/ABC234')

    await user.click(await screen.findByRole('button', { name: /start tournament/i }))

    await waitFor(() => expect(calls.some((c) => c.path.endsWith('/start'))).toBe(true))
  })

  it('is not offered to guests', async () => {
    asGuest()
    serve(() => makeSnapshot({ option_count: 3 }))
    renderRoute('/r/ABC234')

    await screen.findByRole('heading', { name: 'Where should we eat?' })
    expect(screen.queryByRole('button', { name: /start tournament/i })).not.toBeInTheDocument()
  })
})

describe('matchup screen', () => {
  beforeEach(asGuest)

  it('shows the open matchup, the round, progress and a countdown', async () => {
    serve(() => makeTournamentSnapshot())
    renderRoute('/r/ABC234')

    const matchup = await screen.findByRole('region', { name: /current matchup/i })
    expect(within(matchup).getByRole('button', { name: /vote for pizza/i })).toBeEnabled()
    expect(within(matchup).getByRole('button', { name: /vote for tacos/i })).toBeEnabled()
    expect(within(matchup).getByText(/round 1 of 2/i)).toBeInTheDocument()
    expect(within(matchup).getByText(/0\/2 voted/i)).toBeInTheDocument()
    expect(within(matchup).getByText(/\d+s left/i)).toBeInTheDocument()
  })

  it('casts a vote and highlights my choice', async () => {
    const user = userEvent.setup()
    let myVote: string | null = null
    const { calls } = serve(
      () =>
        makeTournamentSnapshot({}, {
          current: { ...makeTournamentSnapshot().tournament!.current!, my_vote: myVote, voted_participant_ids: myVote ? ['p-guest'] : [] },
        }),
      {
        'POST /api/rooms/ABC234/votes': (body) => {
          myVote = (body as { contender_id: string }).contender_id
          return { contender_id: myVote }
        },
      },
    )
    renderRoute('/r/ABC234')

    await user.click(await screen.findByRole('button', { name: /vote for tacos/i }))

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /vote for tacos/i })).toHaveAttribute('aria-pressed', 'true'),
    )
    expect(calls.find((c) => c.path.endsWith('/votes'))?.body).toEqual({
      matchup_id: 'm1',
      contender_id: 'c-tacos',
    })
    expect(screen.getByText(/1\/2 voted/i)).toBeInTheDocument()
  })

  it('plays a blip when voting', async () => {
    const play = vi.spyOn(audio, 'play')
    const user = userEvent.setup()
    serve(() => makeTournamentSnapshot(), { 'POST /api/rooms/ABC234/votes': (body) => body })
    renderRoute('/r/ABC234')

    await user.click(await screen.findByRole('button', { name: /vote for pizza/i }))

    expect(play).toHaveBeenCalledWith('vote')
  })

  it('votes with the keyboard', async () => {
    const user = userEvent.setup()
    const { calls } = serve(() => makeTournamentSnapshot(), {
      'POST /api/rooms/ABC234/votes': (body) => body,
    })
    renderRoute('/r/ABC234')
    await screen.findByRole('region', { name: /current matchup/i })

    await user.keyboard('{ArrowRight}')
    await user.keyboard('1')

    await waitFor(() => expect(calls.filter((c) => c.path.endsWith('/votes'))).toHaveLength(2))
    const votes = calls.filter((c) => c.path.endsWith('/votes')).map((c) => (c.body as { contender_id: string }).contender_id)
    expect(votes).toEqual(['c-tacos', 'c-pizza'])
  })

  it('shows a vote error', async () => {
    const user = userEvent.setup()
    serve(() => makeTournamentSnapshot(), {
      'POST /api/rooms/ABC234/votes': () => jsonError(409, 'Voting has closed for this matchup.'),
    })
    renderRoute('/r/ABC234')

    await user.click(await screen.findByRole('button', { name: /vote for pizza/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Voting has closed for this matchup.')
  })

  it('tells late joiners to wait for the next matchup', async () => {
    serve(() =>
      makeTournamentSnapshot({}, { current: { ...makeTournamentSnapshot().tournament!.current!, can_vote: false } }),
    )
    renderRoute('/r/ABC234')

    expect(await screen.findByText(/vote in the next one/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /vote for pizza/i })).toBeDisabled()
  })

  it('counts down to the next matchup during the reveal pause', async () => {
    serve(() =>
      makeTournamentSnapshot({}, {
        current: {
          ...makeTournamentSnapshot().tournament!.current!,
          starts_at: '2026-10-17T12:00:05+00:00',
          ends_at: '2026-10-17T12:00:35+00:00',
        },
      }),
    )
    renderRoute('/r/ABC234')

    expect(await screen.findByText(/voting opens in \d+s/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /vote for pizza/i })).toBeDisabled()
  })

  it('announces a sudden-death revote with the tied score', async () => {
    const tied = makeTournamentSnapshot()
    tied.tournament!.rounds[0][0] = { ...tied.tournament!.rounds[0][0], status: 'revote', votes_a: 1, votes_b: 1 }
    tied.tournament!.current = { ...tied.tournament!.current!, phase: 'revote' }
    serve(() => tied)
    renderRoute('/r/ABC234')

    const matchup = await screen.findByRole('region', { name: /current matchup/i })
    expect(within(matchup).getByText(/tie.*1.*1/i)).toBeInTheDocument()
    expect(within(matchup).getByText(/sudden-death revote/i)).toBeInTheDocument()
  })

  it('lets only the host end voting early', async () => {
    serve(() => makeTournamentSnapshot())
    renderRoute('/r/ABC234')
    await screen.findByRole('region', { name: /current matchup/i })

    expect(screen.queryByRole('button', { name: /end voting/i })).not.toBeInTheDocument()
  })

  it('host ends voting early', async () => {
    asHost()
    const user = userEvent.setup()
    const { calls } = serve(() => makeTournamentSnapshot({ me: HOST_ME }), {
      'POST /api/rooms/ABC234/matchups/m1/close': () => ({ status: 'decided' }),
    })
    renderRoute('/r/ABC234')

    await user.click(await screen.findByRole('button', { name: /end voting/i }))

    await waitFor(() => expect(calls.some((c) => c.path.endsWith('/m1/close'))).toBe(true))
  })
})

describe('results and bracket', () => {
  beforeEach(asGuest)

  function afterFirstMatchup(outcome: 'votes' | 'coin_flip') {
    const snap = makeTournamentSnapshot()
    const t = snap.tournament!
    t.rounds[0][0] = {
      ...t.rounds[0][0],
      status: 'decided',
      winner_id: 'c-pizza',
      outcome,
      votes_a: outcome === 'votes' ? 2 : 1,
      votes_b: 1,
    }
    t.rounds[0][1] = { ...t.rounds[0][1], status: 'voting' }
    t.rounds[1][0] = { ...t.rounds[1][0], contender_a_id: 'c-pizza' }
    t.current = { ...t.current!, matchup_id: 'm2' }
    return snap
  }

  it('shows the last result', async () => {
    serve(() => afterFirstMatchup('votes'))
    renderRoute('/r/ABC234')

    expect(await screen.findByText(/pizza beat tacos 2–1/i)).toBeInTheDocument()
  })

  it('says when a coin flip decided it', async () => {
    serve(() => afterFirstMatchup('coin_flip'))
    renderRoute('/r/ABC234')

    expect(await screen.findByText(/pizza beat tacos on a coin flip/i)).toBeInTheDocument()
  })

  it('draws every round of the bracket', async () => {
    serve(() => afterFirstMatchup('votes'))
    renderRoute('/r/ABC234')

    const bracket = await screen.findByRole('region', { name: /bracket/i })
    expect(within(bracket).getByRole('heading', { name: /round 1/i })).toBeInTheDocument()
    expect(within(bracket).getByRole('heading', { name: /final/i })).toBeInTheDocument()
    for (const name of ['Pizza', 'Tacos', 'Sushi', 'Ramen']) {
      expect(within(bracket).getAllByText(name).length).toBeGreaterThan(0)
    }
  })

  it('labels byes', async () => {
    const snap = makeTournamentSnapshot()
    snap.tournament!.rounds[0][1] = makeMatchup({
      id: 'm2', round: 0, index: 1, contender_a_id: 'c-sushi', winner_id: 'c-sushi', is_bye: true, status: 'decided', outcome: 'bye',
    })
    serve(() => snap)
    renderRoute('/r/ABC234')

    const bracket = await screen.findByRole('region', { name: /bracket/i })
    expect(within(bracket).getByText(/bye/i)).toBeInTheDocument()
  })

  it('crowns the champion when the tournament is finished', async () => {
    const snap = makeTournamentSnapshot({ status: 'finished' }, { current: null, champion_id: 'c-pizza' })
    serve(() => snap)
    renderRoute('/r/ABC234')

    expect(await screen.findByRole('heading', { name: /champion/i })).toHaveTextContent('Pizza')
    expect(screen.queryByRole('region', { name: /current matchup/i })).not.toBeInTheDocument()
  })
})
