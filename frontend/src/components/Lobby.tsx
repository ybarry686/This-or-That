import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState, type FormEvent } from 'react'
import { useLocation } from 'react-router'
import { ApiError, api, type RoomSnapshot } from '../api/client'
import { useRoomEvents } from '../realtime'
import type { StoredSession } from '../session'
import HostPanel from './HostPanel'
import Tournament from './Tournament'
import { Card, ErrorMessage, Page, buttonClass, inputClass, subtleButtonClass } from './ui'

type Props = { code: string; session: StoredSession; onSessionRejected: () => void }

export default function Lobby({ code, session, onSessionRejected }: Props) {
  const queryClient = useQueryClient()
  const queryKey = ['room', code, session.token]
  const room = useQuery({ queryKey, queryFn: () => api.getRoom(code, session.token) })
  const refresh = () => queryClient.invalidateQueries({ queryKey })

  useRoomEvents(code, session.token, () => {
    refresh()
  })

  const rejected = room.error instanceof ApiError && room.error.status === 401
  useEffect(() => {
    if (rejected) onSessionRejected()
  }, [rejected, onSessionRejected])

  if (room.isPending) {
    return (
      <Page>
        <p className="text-zinc-400">Loading room…</p>
      </Page>
    )
  }
  if (room.isError) {
    return (
      <Page>
        <ErrorMessage error={room.error} />
      </Page>
    )
  }

  const snapshot = room.data
  if (snapshot.status !== 'lobby' && snapshot.tournament) {
    return (
      <Page>
        <RoomHeader snapshot={snapshot} />
        <Tournament snapshot={snapshot} token={session.token} onChanged={refresh} />
      </Page>
    )
  }
  return (
    <Page>
      <RoomHeader snapshot={snapshot} />
      <RecoveryLinkNotice code={code} />
      <PlayerList snapshot={snapshot} token={session.token} onChanged={refresh} />
      <MyOptions snapshot={snapshot} token={session.token} onChanged={refresh} />
      {snapshot.me.is_host && (
        <HostPanel snapshot={snapshot} token={session.token} onChanged={refresh} />
      )}
    </Page>
  )
}

function RoomHeader({ snapshot }: { snapshot: RoomSnapshot }) {
  const inviteUrl = `${window.location.origin}/r/${snapshot.code}`
  const count = snapshot.option_count
  return (
    <header className="flex flex-col gap-2">
      <h1 className="text-3xl font-black">{snapshot.title}</h1>
      {snapshot.description && <p className="text-zinc-400">{snapshot.description}</p>}
      <div className="flex flex-wrap items-center gap-3 text-sm text-zinc-400">
        <span>
          Room code <strong className="font-mono text-lg tracking-widest text-zinc-100">{snapshot.code}</strong>
        </span>
        <button
          type="button"
          className={subtleButtonClass}
          onClick={() => navigator.clipboard?.writeText(inviteUrl).catch(() => {})}
        >
          Copy invite link
        </button>
        <span>
          {count} {count === 1 ? 'option' : 'options'} submitted
        </span>
      </div>
    </header>
  )
}

function RecoveryLinkNotice({ code }: { code: string }) {
  const state = useLocation().state as { recoveryToken?: string } | null
  const [dismissed, setDismissed] = useState(false)
  if (!state?.recoveryToken || dismissed) return null

  const link = `${window.location.origin}/r/${code}/recover#${state.recoveryToken}`
  return (
    <Card>
      <h2 className="font-bold">Save your host recovery link</h2>
      <p className="mt-1 text-sm text-zinc-400">
        It is shown only once. Open it on any device to get your host controls back.
      </p>
      <code className="mt-2 block break-all rounded bg-zinc-950 p-2 text-xs">{link}</code>
      <button type="button" className={`${subtleButtonClass} mt-2`} onClick={() => setDismissed(true)}>
        I saved it
      </button>
    </Card>
  )
}

type SectionProps = { snapshot: RoomSnapshot; token: string; onChanged: () => void }

function PlayerList({ snapshot, token, onChanged }: SectionProps) {
  const transfer = useMutation({
    mutationFn: (participantId: string) => api.transferHost(snapshot.code, token, participantId),
    onSuccess: onChanged,
  })

  return (
    <Card>
      <h2 className="mb-3 font-bold">
        Players ({snapshot.participants.length}/{snapshot.settings.max_participants})
      </h2>
      <ul aria-label="Players" className="flex flex-col gap-2">
        {snapshot.participants.map((p) => (
          <li key={p.id} className="flex items-center gap-2">
            <span
              role="img"
              aria-label={`${p.nickname} is ${p.connected ? 'online' : 'offline'}`}
              className={`h-2 w-2 rounded-full ${p.connected ? 'bg-emerald-400' : 'bg-zinc-600'}`}
            />
            <span>{p.nickname}</span>
            {p.is_host && (
              <span className="badge rounded bg-amber-400 px-1 text-xs font-bold text-zinc-900">HOST</span>
            )}
            {p.id === snapshot.me.id && <span className="text-xs text-zinc-500">(you)</span>}
            {snapshot.me.is_host && !p.is_host && (
              <button
                type="button"
                className={`${subtleButtonClass} ml-auto`}
                aria-label={`Make ${p.nickname} host`}
                onClick={() => transfer.mutate(p.id)}
              >
                Make host
              </button>
            )}
          </li>
        ))}
      </ul>
      <ErrorMessage error={transfer.error} />
    </Card>
  )
}

function MyOptions({ snapshot, token, onChanged }: SectionProps) {
  const [text, setText] = useState('')
  const limit = snapshot.settings.max_submissions
  const used = snapshot.my_submissions.length

  const submit = useMutation({
    mutationFn: () => api.submitOption(snapshot.code, token, text),
    onSuccess: () => {
      setText('')
      onChanged()
    },
  })
  const remove = useMutation({
    mutationFn: (submissionId: string) => api.deleteSubmission(snapshot.code, token, submissionId),
    onSuccess: onChanged,
  })

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    submit.mutate()
  }

  return (
    <Card>
      <h2 className="mb-1 font-bold">Your options</h2>
      <p className="mb-3 text-sm text-zinc-400">
        {used} of {limit} used. Other players' options stay hidden until the tournament starts.
      </p>
      <ul aria-label="Your options" className="mb-3 flex flex-col gap-2">
        {snapshot.my_submissions.map((s) => (
          <li key={s.id} className="flex items-center justify-between gap-2">
            <span>{s.text}</span>
            <button
              type="button"
              className={subtleButtonClass}
              aria-label={`Remove ${s.text}`}
              onClick={() => remove.mutate(s.id)}
            >
              Remove
            </button>
          </li>
        ))}
      </ul>
      <form onSubmit={onSubmit} className="flex gap-2">
        <input
          className={`${inputClass} flex-1`}
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={80}
          placeholder="Add an option"
          aria-label="Your option"
        />
        <button type="submit" className={buttonClass} disabled={used >= limit || submit.isPending}>
          Add option
        </button>
      </form>
      <ErrorMessage error={submit.error ?? remove.error} />
    </Card>
  )
}
