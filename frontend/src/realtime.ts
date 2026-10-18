import { useEffect, useRef } from 'react'
import { roomSocketUrl } from './api/client'

export type RoomEvent = { type: string; version: number; data: Record<string, unknown> }

const MAX_BACKOFF_MS = 5000

/**
 * Keeps a WebSocket open to the room and calls `onChange` whenever the room may have changed:
 * on every event and on every (re)connect, since events may have been missed while away (SPEC §9).
 */
export function useRoomEvents(code: string, token: string | null, onChange: (event?: RoomEvent) => void) {
  const onChangeRef = useRef(onChange)
  useEffect(() => {
    onChangeRef.current = onChange
  })

  useEffect(() => {
    if (!token) return
    let socket: WebSocket | null = null
    let retryTimer: ReturnType<typeof setTimeout> | undefined
    let attempt = 0
    let stopped = false

    const connect = () => {
      socket = new WebSocket(roomSocketUrl(code, token))
      socket.onopen = () => {
        attempt = 0
        onChangeRef.current()
      }
      socket.onmessage = (message) => {
        try {
          onChangeRef.current(JSON.parse(message.data) as RoomEvent)
        } catch {
          onChangeRef.current()
        }
      }
      socket.onclose = () => {
        if (stopped) return
        attempt += 1
        retryTimer = setTimeout(connect, Math.min(MAX_BACKOFF_MS, 250 * 2 ** attempt))
      }
    }

    // Deferred one tick so a mount that is immediately undone (React StrictMode) never opens a
    // throwaway connection.
    retryTimer = setTimeout(connect, 0)
    return () => {
      stopped = true
      clearTimeout(retryTimer)
      socket?.close()
    }
  }, [code, token])
}
