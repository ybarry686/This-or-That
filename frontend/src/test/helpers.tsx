import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { vi } from 'vitest'
import type { RoomSnapshot } from '../api/client'
import { AppRoutes } from '../App'

type Handler = (body: unknown, init: RequestInit) => unknown | Response

/** Stubs `fetch` with handlers keyed by "METHOD /path". Unmatched calls get a 404. */
export function mockApi(routes: Record<string, Handler>) {
  const calls: { method: string; path: string; body: unknown; headers: Headers }[] = []
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const method = (init.method ?? 'GET').toUpperCase()
    const path = String(input)
    const body = init.body ? JSON.parse(String(init.body)) : undefined
    calls.push({ method, path, body, headers: new Headers(init.headers) })

    const handler = routes[`${method} ${path}`]
    if (!handler) {
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 })
    }
    const result = handler(body, init)
    if (result instanceof Response) return result
    if (result === undefined) return new Response(null, { status: 204 })
    return new Response(JSON.stringify(result), { status: 200 })
  })
  vi.stubGlobal('fetch', fetchMock)
  return { fetchMock, calls }
}

export function jsonError(status: number, detail: string) {
  return new Response(JSON.stringify({ detail }), { status })
}

/** Minimal controllable WebSocket stand-in. */
export class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  closed = false
  url: string

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  open() {
    this.onopen?.()
  }

  emit(message: unknown) {
    this.onmessage?.({ data: JSON.stringify(message) })
  }

  close() {
    this.closed = true
  }

  serverClose() {
    this.onclose?.()
  }

  static latest() {
    return FakeWebSocket.instances[FakeWebSocket.instances.length - 1]
  }
}

export function installFakeWebSocket() {
  FakeWebSocket.instances = []
  vi.stubGlobal('WebSocket', FakeWebSocket)
}

export function renderRoute(path: string, state?: unknown) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[{ pathname: path, state }]}>
        <AppRoutes />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

export function makeSnapshot(overrides: Partial<RoomSnapshot> = {}): RoomSnapshot {
  const host = { id: 'p-host', nickname: 'Host', avatar: 0, is_host: true, connected: true }
  const guest = { id: 'p-guest', nickname: 'Sam', avatar: 1, is_host: false, connected: false }
  return {
    code: 'ABC234',
    title: 'Where should we eat?',
    description: '',
    status: 'lobby',
    version: 3,
    settings: { max_participants: 20, max_submissions: 3, vote_seconds: 30 },
    host_participant_id: host.id,
    me: guest,
    participants: [host, guest],
    option_count: 0,
    my_submissions: [],
    contenders: null,
    tournament: null,
    server_time: '2026-10-17T12:00:00+00:00',
    ...overrides,
  }
}

export const HOST_ME = { id: 'p-host', nickname: 'Host', avatar: 0, is_host: true, connected: true }

type Tournament = NonNullable<RoomSnapshot['tournament']>
type MatchupOut = Tournament['rounds'][number][number]

export function makeMatchup(overrides: Partial<MatchupOut> & Pick<MatchupOut, 'id' | 'round' | 'index'>): MatchupOut {
  return {
    contender_a_id: null,
    contender_b_id: null,
    winner_id: null,
    is_bye: false,
    status: 'pending',
    outcome: null,
    votes_a: 0,
    votes_b: 0,
    ...overrides,
  }
}

const SERVER_NOW = '2026-10-17T12:00:00+00:00'

/**
 * A 4-option tournament in its first matchup: Pizza vs Tacos (open), Sushi vs Ramen, then the final.
 * The server clock sits at the start of a 30 s voting window.
 */
export function makeTournamentSnapshot(
  overrides: Partial<RoomSnapshot> = {},
  tournament: Partial<Tournament> = {},
): RoomSnapshot {
  return makeSnapshot({
    status: 'in_progress',
    option_count: 4,
    server_time: SERVER_NOW,
    tournament: {
      contenders: [
        { id: 'c-pizza', display_text: 'Pizza', submitter_ids: ['p-host'] },
        { id: 'c-tacos', display_text: 'Tacos', submitter_ids: ['p-guest'] },
        { id: 'c-sushi', display_text: 'Sushi', submitter_ids: ['p-host'] },
        { id: 'c-ramen', display_text: 'Ramen', submitter_ids: ['p-guest'] },
      ],
      rounds: [
        [
          makeMatchup({ id: 'm1', round: 0, index: 0, contender_a_id: 'c-pizza', contender_b_id: 'c-tacos', status: 'voting' }),
          makeMatchup({ id: 'm2', round: 0, index: 1, contender_a_id: 'c-sushi', contender_b_id: 'c-ramen' }),
        ],
        [makeMatchup({ id: 'm3', round: 1, index: 0 })],
      ],
      current: {
        matchup_id: 'm1',
        phase: 'vote',
        starts_at: SERVER_NOW,
        ends_at: '2026-10-17T12:00:30+00:00',
        eligible_count: 2,
        voted_participant_ids: [],
        my_vote: null,
        can_vote: true,
      },
      champion_id: null,
      ...tournament,
    },
    ...overrides,
  })
}
