import { act, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { RoomSnapshot } from '../api/client'
import { saveSession } from '../session'
import { resetSettingsForTests, setSetting } from '../settings'
import {
  FakeWebSocket,
  installFakeWebSocket,
  makeTournamentSnapshot,
  mockApi,
  renderRoute,
} from '../test/helpers'

let current: RoomSnapshot

beforeEach(() => {
  installFakeWebSocket()
  localStorage.clear()
  resetSettingsForTests()
  saveSession('ABC234', { participantId: 'p-guest', token: 'guest-token' })
  current = makeTournamentSnapshot()
  mockApi({ 'GET /api/rooms/ABC234': () => current })
})

afterEach(() => {
  localStorage.clear()
  vi.unstubAllGlobals()
})

async function open() {
  renderRoute('/r/ABC234')
  await screen.findByRole('region', { name: /current matchup/i })
}

/** Swap in the next server state and let the client refetch it, as a WebSocket event would. */
async function serverMovesTo(next: RoomSnapshot, waitFor: RegExp) {
  current = next
  await act(async () => {
    FakeWebSocket.latest().emit({ type: 'any', version: next.version, data: {} })
  })
  return screen.findByRole('status', { name: waitFor })
}

function firstMatchupDecided(outcome: 'votes' | 'coin_flip'): RoomSnapshot {
  const snap = makeTournamentSnapshot({ version: 10 })
  const t = snap.tournament!
  t.rounds[0][0] = { ...t.rounds[0][0], status: 'decided', winner_id: 'c-pizza', outcome, votes_a: 2, votes_b: 1 }
  t.rounds[0][1] = { ...t.rounds[0][1], status: 'voting' }
  t.rounds[1][0] = { ...t.rounds[1][0], contender_a_id: 'c-pizza' }
  t.current = { ...t.current!, matchup_id: 'm2' }
  return snap
}

describe('announcements', () => {
  it('does not replay anything when the page first loads', async () => {
    current = firstMatchupDecided('votes')
    await open()

    expect(screen.queryByRole('status', { name: /k\.o\./i })).not.toBeInTheDocument()
    expect(screen.queryByRole('status', { name: /fight/i })).not.toBeInTheDocument()
  })

  it('opens the tournament with a round call when the host starts it', async () => {
    current = makeTournamentSnapshot({ status: 'lobby', option_count: 4 }, {})
    current.tournament = null
    renderRoute('/r/ABC234')
    await screen.findByRole('heading', { name: 'Where should we eat?' })

    expect(await serverMovesTo(makeTournamentSnapshot({ version: 10 }), /round 1.*fight/i)).toBeInTheDocument()
  })

  it('announces a knockout when a matchup is decided', async () => {
    await open()

    const ko = await serverMovesTo(firstMatchupDecided('votes'), /k\.o\./i)

    expect(ko).toHaveTextContent(/pizza wins 2–1/i)
  })

  it('announces a coin flip', async () => {
    await open()

    const flip = await serverMovesTo(firstMatchupDecided('coin_flip'), /coin flip/i)

    expect(flip).toHaveTextContent(/pizza/i)
  })

  it('announces a sudden-death revote', async () => {
    await open()
    const tied = makeTournamentSnapshot({ version: 10 })
    tied.tournament!.rounds[0][0] = { ...tied.tournament!.rounds[0][0], status: 'revote', votes_a: 1, votes_b: 1 }
    tied.tournament!.current = { ...tied.tournament!.current!, phase: 'revote' }

    expect(await serverMovesTo(tied, /sudden death/i)).toBeInTheDocument()
  })

  it('announces the next round after the knockout', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      await open()
      const final = firstMatchupDecided('votes')
      final.tournament!.rounds[0][1] = { ...final.tournament!.rounds[0][1], status: 'decided', winner_id: 'c-sushi', outcome: 'votes', votes_a: 1 }
      final.tournament!.rounds[1][0] = { ...final.tournament!.rounds[1][0], contender_a_id: 'c-pizza', contender_b_id: 'c-sushi', status: 'voting' }
      final.tournament!.current = { ...final.tournament!.current!, matchup_id: 'm3' }

      await serverMovesTo(final, /k\.o\./i)
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000)
      })

      expect(await screen.findByRole('status', { name: /final.*fight/i })).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('celebrates the champion with confetti', async () => {
    await open()
    const done = makeTournamentSnapshot({ status: 'finished', version: 10 }, { current: null, champion_id: 'c-pizza' })

    const reveal = await serverMovesTo(done, /champion/i)

    expect(reveal).toHaveTextContent(/pizza/i)
    expect(screen.getByTestId('confetti')).toBeInTheDocument()
  })

  it('skips confetti when motion is reduced', async () => {
    setSetting('reduceMotion', true)
    await open()
    const done = makeTournamentSnapshot({ status: 'finished', version: 10 }, { current: null, champion_id: 'c-pizza' })

    await serverMovesTo(done, /champion/i)

    expect(screen.queryByTestId('confetti')).not.toBeInTheDocument()
  })
})
