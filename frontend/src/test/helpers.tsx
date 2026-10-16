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
    ...overrides,
  }
}

export const HOST_ME = { id: 'p-host', nickname: 'Host', avatar: 0, is_host: true, connected: true }
