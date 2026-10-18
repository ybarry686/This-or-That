import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router'
import { ApiError, api } from '../api/client'
import { Bracket } from '../components/Tournament'
import { Card, Page, subtleButtonClass } from '../components/ui'

/** Read-only results of a finished game, for anyone with the room code (SPEC §4). */
export default function Results() {
  const code = (useParams().code ?? '').toUpperCase()
  const results = useQuery({ queryKey: ['results', code], queryFn: () => api.getResults(code) })

  if (results.isPending) {
    return (
      <Page>
        <p className="text-dim">Loading results…</p>
      </Page>
    )
  }
  if (results.isError) {
    const notFinished = results.error instanceof ApiError && results.error.status === 409
    return (
      <Page>
        <Card>
          <p role="alert" className="text-center">
            {notFinished
              ? results.error.message
              : 'No results for this room. Finished games are kept for 30 days.'}
          </p>
          {notFinished && (
            <p className="mt-3 text-center">
              <Link to={`/r/${code}`} className={subtleButtonClass}>
                Go to the room
              </Link>
            </p>
          )}
        </Card>
      </Page>
    )
  }

  const { title, description, finished_at, participants, tournament, rematch_code } = results.data
  const names = new Map(tournament.contenders.map((c) => [c.id, c.display_text]))
  return (
    <Page>
      <header className="flex flex-col gap-2">
        <p className="font-arcade text-[10px] tracking-widest text-dim uppercase">Results</p>
        <h1 className="text-2xl font-black sm:text-3xl">{title}</h1>
        {description && <p className="text-dim">{description}</p>}
        <p className="text-sm text-dim">
          Finished {new Date(finished_at).toLocaleString()} · Played by{' '}
          {participants.map((p) => p.nickname).join(', ')}
        </p>
      </header>
      <Card>
        <h2 className="text-center font-arcade text-lg leading-relaxed text-coin sm:text-2xl">
          <span className="block text-[10px] tracking-widest text-dim">Champion:</span>{' '}
          <span className="arcade-glow">{names.get(tournament.champion_id ?? '')}</span>
        </h2>
      </Card>
      <Bracket tournament={tournament} names={names} />
      {rematch_code && (
        <p className="text-center">
          <Link to={`/r/${rematch_code}`} className={subtleButtonClass}>
            Go to the rematch ({rematch_code})
          </Link>
        </p>
      )}
    </Page>
  )
}
