import type { components } from './schema'

type Schemas = components['schemas']
export type RoomSnapshot = Schemas['RoomSnapshot']
export type Participant = Schemas['ParticipantOut']
export type Contender = Schemas['ContenderOut']
export type RoomSettings = Schemas['RoomSettings']
export type SessionResponse = Schemas['SessionResponse']
export type CreateRoomResponse = Schemas['CreateRoomResponse']
// Fields with server-side defaults (description, settings) may be omitted.
export type CreateRoomRequest = Pick<Schemas['CreateRoomRequest'], 'title' | 'nickname'> &
  Partial<Schemas['CreateRoomRequest']>
export type UpdateRoomRequest = Schemas['UpdateRoomRequest']

const API_BASE = '/api'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

type ValidationIssue = { loc?: (string | number)[]; msg?: string }

function errorMessage(detail: unknown, status: number): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return (detail as ValidationIssue[])
      .map((issue) => `${issue.loc?.slice(1).join('.') ?? 'input'}: ${issue.msg ?? 'invalid'}`)
      .join('; ')
  }
  return `Request failed (${status})`
}

async function request<T>(
  method: string,
  path: string,
  { token, body }: { token?: string; body?: unknown } = {},
): Promise<T> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = `Bearer ${token}`

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new ApiError(response.status, errorMessage(payload.detail, response.status))
  }
  if (response.status === 204) return undefined as T
  return response.json()
}

const room = (code: string) => `/rooms/${encodeURIComponent(code)}`

export const api = {
  createRoom: (body: CreateRoomRequest) =>
    request<CreateRoomResponse>('POST', '/rooms', { body }),
  joinRoom: (code: string, nickname: string) =>
    request<SessionResponse>('POST', `${room(code)}/join`, { body: { nickname } }),
  getRoom: (code: string, token: string) => request<RoomSnapshot>('GET', room(code), { token }),
  updateRoom: (code: string, token: string, body: UpdateRoomRequest) =>
    request<RoomSettings>('PATCH', room(code), { token, body }),
  submitOption: (code: string, token: string, text: string) =>
    request<Schemas['SubmissionOut']>('POST', `${room(code)}/submissions`, {
      token,
      body: { text },
    }),
  deleteSubmission: (code: string, token: string, submissionId: string) =>
    request<void>('DELETE', `${room(code)}/submissions/${encodeURIComponent(submissionId)}`, {
      token,
    }),
  mergeContenders: (code: string, token: string, sourceKey: string, targetKey: string) =>
    request<void>('POST', `${room(code)}/contenders/merge`, {
      token,
      body: { source_key: sourceKey, target_key: targetKey },
    }),
  removeContender: (code: string, token: string, key: string) =>
    request<void>('POST', `${room(code)}/contenders/remove`, { token, body: { key } }),
  transferHost: (code: string, token: string, participantId: string) =>
    request<void>('POST', `${room(code)}/host/transfer`, {
      token,
      body: { participant_id: participantId },
    }),
  startTournament: (code: string, token: string) =>
    request<Schemas['StartTournamentResponse']>('POST', `${room(code)}/start`, { token }),
  castVote: (code: string, token: string, matchupId: string, contenderId: string) =>
    request<Schemas['VoteResponse']>('POST', `${room(code)}/votes`, {
      token,
      body: { matchup_id: matchupId, contender_id: contenderId },
    }),
  closeMatchup: (code: string, token: string, matchupId: string) =>
    request<Schemas['CloseMatchupResponse']>(
      'POST',
      `${room(code)}/matchups/${encodeURIComponent(matchupId)}/close`,
      { token },
    ),
  recoverHost: (code: string, recoveryToken: string) =>
    request<SessionResponse>('POST', `${room(code)}/host/recover`, {
      body: { recovery_token: recoveryToken },
    }),
}

export function roomSocketUrl(code: string, token: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}${API_BASE}${room(code)}/ws?token=${encodeURIComponent(token)}`
}
