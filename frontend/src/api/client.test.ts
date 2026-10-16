import { afterEach, describe, expect, it, vi } from 'vitest'
import { jsonError, mockApi } from '../test/helpers'
import { ApiError, api } from './client'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('api client', () => {
  it('sends JSON bodies and the bearer token', async () => {
    const { calls } = mockApi({
      'POST /api/rooms/ABC234/submissions': () => ({ id: 's1', text: 'Pizza' }),
    })

    const result = await api.submitOption('ABC234', 'tok', 'Pizza')

    expect(result).toEqual({ id: 's1', text: 'Pizza' })
    expect(calls[0].body).toEqual({ text: 'Pizza' })
    expect(calls[0].headers.get('Authorization')).toBe('Bearer tok')
    expect(calls[0].headers.get('Content-Type')).toBe('application/json')
  })

  it('raises ApiError with the server detail', async () => {
    mockApi({ 'GET /api/rooms/ABC234': () => jsonError(401, 'Invalid participant token.') })

    const error = await api.getRoom('ABC234', 'bad').catch((e) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(401)
    expect(error.message).toBe('Invalid participant token.')
  })

  it('summarizes validation errors', async () => {
    mockApi({
      'POST /api/rooms': () =>
        new Response(
          JSON.stringify({ detail: [{ loc: ['body', 'title'], msg: 'String should have at least 1 character' }] }),
          { status: 422 },
        ),
    })

    const error = await api
      .createRoom({ title: '', nickname: 'Ana' })
      .catch((e) => e)

    expect(error.status).toBe(422)
    expect(error.message).toContain('title')
  })

  it('handles empty 204 responses', async () => {
    mockApi({ 'DELETE /api/rooms/ABC234/submissions/s1': () => undefined })

    await expect(api.deleteSubmission('ABC234', 'tok', 's1')).resolves.toBeUndefined()
  })
})
