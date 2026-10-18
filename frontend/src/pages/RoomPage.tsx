import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useParams } from 'react-router'
import { api } from '../api/client'
import Lobby from '../components/Lobby'
import { Card, ErrorMessage, Page, buttonClass, inputClass } from '../components/ui'
import { clearSession, loadSession, saveSession, type StoredSession } from '../session'

export default function RoomPage() {
  const code = (useParams().code ?? '').toUpperCase()
  // Keyed by code so moving to another room (e.g. a rematch) starts from that room's identity.
  return <Room key={code} code={code} />
}

function Room({ code }: { code: string }) {
  const [session, setSession] = useState<StoredSession | null>(() => loadSession(code))

  if (!session) {
    return (
      <JoinForm
        code={code}
        onJoined={(joined) => {
          saveSession(code, joined)
          setSession(joined)
        }}
      />
    )
  }
  return (
    <Lobby
      code={code}
      session={session}
      onSessionRejected={() => {
        clearSession(code)
        setSession(null)
      }}
    />
  )
}

function JoinForm({ code, onJoined }: { code: string; onJoined: (session: StoredSession) => void }) {
  const [nickname, setNickname] = useState('')
  const join = useMutation({
    mutationFn: () => api.joinRoom(code, nickname),
    onSuccess: (joined) => onJoined({ participantId: joined.participant_id, token: joined.token }),
  })

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    join.mutate()
  }

  return (
    <Page>
      <Card>
        <h1 className="mb-4 font-arcade text-sm leading-relaxed text-coin sm:text-base">Join room {code}</h1>
        <form onSubmit={onSubmit} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm">
            Your nickname
            <input
              className={inputClass}
              value={nickname}
              onChange={(e) => setNickname(e.target.value)}
              maxLength={20}
              required
              autoFocus
            />
          </label>
          <ErrorMessage error={join.error} />
          <button type="submit" className={buttonClass} disabled={join.isPending}>
            Join
          </button>
        </form>
      </Card>
    </Page>
  )
}
