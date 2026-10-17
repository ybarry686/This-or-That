import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { api } from '../api/client'
import { Card, ErrorMessage, NumberField, Page, buttonClass, inputClass } from '../components/ui'
import { saveSession } from '../session'

export default function Landing() {
  return (
    <Page>
      <header className="text-center">
        <h1 aria-label="This or That" className="font-arcade text-3xl leading-tight sm:text-5xl">
          <span className="arcade-glow text-p1">THIS</span>{' '}
          <span className="align-middle text-sm text-coin sm:text-base">OR</span>{' '}
          <span className="arcade-glow text-p2">THAT</span>
        </h1>
        <p className="mt-4 font-arcade text-[10px] leading-relaxed tracking-widest text-dim uppercase">Settle it with a tournament</p>
      </header>
      <CreateRoomForm />
      <JoinByCodeForm />
    </Page>
  )
}

function CreateRoomForm() {
  const navigate = useNavigate()
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [nickname, setNickname] = useState('')
  const [maxParticipants, setMaxParticipants] = useState(20)
  const [maxSubmissions, setMaxSubmissions] = useState(3)
  const [voteSeconds, setVoteSeconds] = useState(30)

  const create = useMutation({
    mutationFn: () =>
      api.createRoom({
        title,
        description,
        nickname,
        settings: {
          max_participants: maxParticipants,
          max_submissions: maxSubmissions,
          vote_seconds: voteSeconds,
        },
      }),
    onSuccess: (created) => {
      saveSession(created.code, { participantId: created.participant_id, token: created.token })
      navigate(`/r/${created.code}`, { state: { recoveryToken: created.host_recovery_token } })
    },
  })

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    create.mutate()
  }

  return (
    <Card>
      <h2 className="mb-3 font-arcade text-xs leading-relaxed tracking-wider text-coin uppercase">Create a room</h2>
      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm">
          Question
          <input
            className={inputClass}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={120}
            placeholder="Where should we eat tonight?"
            required
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Description (optional)
          <input
            className={inputClass}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={500}
          />
        </label>
        <label htmlFor="create-nickname" className="flex flex-col gap-1 text-sm">
          Your nickname
          <input
            id="create-nickname"
            className={inputClass}
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
            maxLength={20}
            required
          />
        </label>
        <div className="grid grid-cols-3 gap-3">
          <NumberField label="Max players" value={maxParticipants} min={2} max={50} onChange={setMaxParticipants} />
          <NumberField label="Options per person" value={maxSubmissions} min={1} max={10} onChange={setMaxSubmissions} />
          <NumberField label="Vote timer (seconds)" value={voteSeconds} min={10} max={120} onChange={setVoteSeconds} />
        </div>
        <ErrorMessage error={create.error} />
        <button type="submit" className={buttonClass} disabled={create.isPending}>
          Create room
        </button>
      </form>
    </Card>
  )
}

function JoinByCodeForm() {
  const navigate = useNavigate()
  const [code, setCode] = useState('')

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    const normalized = code.trim().toUpperCase()
    if (normalized) navigate(`/r/${normalized}`)
  }

  return (
    <Card>
      <h2 className="mb-3 font-arcade text-xs leading-relaxed tracking-wider text-coin uppercase">Join a room</h2>
      <form onSubmit={onSubmit} className="flex gap-3">
        <label className="flex flex-1 flex-col gap-1 text-sm">
          Room code
          <input
            className={`${inputClass} uppercase tracking-widest`}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            maxLength={6}
            required
          />
        </label>
        <button type="submit" className={`${buttonClass} self-end`}>
          Join
        </button>
      </form>
    </Card>
  )
}
