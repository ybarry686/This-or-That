import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { api, type RoomSnapshot } from '../api/client'
import { Card, ErrorMessage, NumberField, buttonClass, inputClass, subtleButtonClass } from './ui'

type Props = { snapshot: RoomSnapshot; token: string; onChanged: () => void }

export default function HostPanel(props: Props) {
  return (
    <>
      <AllOptions {...props} />
      <SettingsForm {...props} />
    </>
  )
}

function AllOptions({ snapshot, token, onChanged }: Props) {
  const contenders = snapshot.contenders ?? []
  const nicknames = new Map(snapshot.participants.map((p) => [p.id, p.nickname]))

  const merge = useMutation({
    mutationFn: ({ source, target }: { source: string; target: string }) =>
      api.mergeContenders(snapshot.code, token, source, target),
    onSuccess: onChanged,
  })
  const remove = useMutation({
    mutationFn: (key: string) => api.removeContender(snapshot.code, token, key),
    onSuccess: onChanged,
  })

  return (
    <Card>
      <h2 className="mb-1 font-bold">All options</h2>
      <p className="mb-3 text-sm text-zinc-400">
        Only you can see these. Merge near-duplicates or remove anything off-topic.
      </p>
      <ul aria-label="All options" className="flex flex-col gap-3">
        {contenders.map((c) => {
          const submitters = [...new Set(c.submissions.map((s) => nicknames.get(s.participant_id) ?? '?'))]
          return (
            <li key={c.key} className="flex flex-wrap items-center gap-2">
              <span className="font-semibold">{c.display_text}</span>
              <span className="text-xs text-zinc-500">by {submitters.join(', ')}</span>
              <span className="ml-auto flex items-center gap-2">
                {contenders.length > 1 && (
                  <select
                    className={`${inputClass} w-auto py-1 text-xs`}
                    aria-label={`Merge ${c.display_text} into`}
                    value=""
                    onChange={(e) => merge.mutate({ source: c.key, target: e.target.value })}
                  >
                    <option value="">Merge into…</option>
                    {contenders
                      .filter((other) => other.key !== c.key)
                      .map((other) => (
                        <option key={other.key} value={other.key}>
                          {other.display_text}
                        </option>
                      ))}
                  </select>
                )}
                <button
                  type="button"
                  className={subtleButtonClass}
                  aria-label={`Remove option ${c.display_text}`}
                  onClick={() => remove.mutate(c.key)}
                >
                  Remove
                </button>
              </span>
            </li>
          )
        })}
      </ul>
      {contenders.length === 0 && <p className="text-sm text-zinc-500">No options yet.</p>}
      <ErrorMessage error={merge.error ?? remove.error} />
    </Card>
  )
}

function SettingsForm({ snapshot, token, onChanged }: Props) {
  const [title, setTitle] = useState(snapshot.title)
  const [description, setDescription] = useState(snapshot.description)
  const [maxParticipants, setMaxParticipants] = useState(snapshot.settings.max_participants)
  const [maxSubmissions, setMaxSubmissions] = useState(snapshot.settings.max_submissions)
  const [voteSeconds, setVoteSeconds] = useState(snapshot.settings.vote_seconds)

  const save = useMutation({
    mutationFn: () =>
      api.updateRoom(snapshot.code, token, {
        title,
        description,
        max_participants: maxParticipants,
        max_submissions: maxSubmissions,
        vote_seconds: voteSeconds,
      }),
    onSuccess: onChanged,
  })

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    save.mutate()
  }

  return (
    <Card>
      <h2 className="mb-3 font-bold">Settings</h2>
      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm">
          Title
          <input className={inputClass} value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} required />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Description
          <input
            className={inputClass}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={500}
          />
        </label>
        <div className="grid grid-cols-3 gap-3">
          <NumberField label="Max players" value={maxParticipants} min={2} max={50} onChange={setMaxParticipants} />
          <NumberField label="Options per person" value={maxSubmissions} min={1} max={10} onChange={setMaxSubmissions} />
          <NumberField label="Vote timer (seconds)" value={voteSeconds} min={10} max={120} onChange={setVoteSeconds} />
        </div>
        <ErrorMessage error={save.error} />
        <button type="submit" className={buttonClass} disabled={save.isPending}>
          Save settings
        </button>
      </form>
    </Card>
  )
}
