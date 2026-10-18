import { useMutation } from '@tanstack/react-query'
import { motion } from 'motion/react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { api, type RoomSnapshot } from '../api/client'
import { audio } from '../audio'
import { saveSession } from '../session'
import { Card, ErrorMessage, buttonClass, subtleButtonClass } from './ui'

type Tournament = NonNullable<RoomSnapshot['tournament']>
type MatchupOut = Tournament['rounds'][number][number]
type Props = { snapshot: RoomSnapshot; token: string; onChanged: () => void }

export default function Tournament({ snapshot, token, onChanged }: Props) {
  const tournament = snapshot.tournament!
  const names = useMemo(
    () => new Map(tournament.contenders.map((c) => [c.id, c.display_text])),
    [tournament.contenders],
  )

  return (
    <>
      {tournament.champion_id && (
        <Card>
          <h2 className="text-center font-arcade text-lg leading-relaxed text-coin sm:text-2xl">
            <span className="block text-[10px] tracking-widest text-dim">Champion:</span>{' '}
            <span className="arcade-glow">{names.get(tournament.champion_id)}</span>
          </h2>
        </Card>
      )}
      {tournament.current && (
        <CurrentMatchup snapshot={snapshot} names={names} token={token} onChanged={onChanged} />
      )}
      {tournament.champion_id && <PostGame snapshot={snapshot} token={token} />}
      <LastResult tournament={tournament} names={names} />
      <Bracket tournament={tournament} names={names} />
    </>
  )
}

/** Share the results and line up a rematch (SPEC §4). */
function PostGame({ snapshot, token }: { snapshot: RoomSnapshot; token: string }) {
  const navigate = useNavigate()
  const resultsPath = `/r/${snapshot.code}/results`
  const rematch = snapshot.rematch_code

  const playAgain = useMutation({
    mutationFn: () => api.createRematch(snapshot.code, token),
    onSuccess: (created) => {
      saveSession(created.code, { participantId: created.participant_id, token: created.token })
      navigate(`/r/${created.code}`, { state: { recoveryToken: created.host_recovery_token } })
    },
  })
  const joinRematch = useMutation({
    mutationFn: () => api.joinRoom(rematch!, snapshot.me.nickname),
    onSuccess: (joined) => {
      saveSession(joined.code, { participantId: joined.participant_id, token: joined.token })
      navigate(`/r/${joined.code}`)
    },
  })

  return (
    <Card>
      <div className="flex flex-wrap items-center justify-center gap-3">
        <Link to={resultsPath} className={subtleButtonClass}>
          View results page
        </Link>
        <button
          type="button"
          className={subtleButtonClass}
          onClick={() =>
            navigator.clipboard?.writeText(`${window.location.origin}${resultsPath}`).catch(() => {})
          }
        >
          Copy results link
        </button>
      </div>
      <div className="mt-4 text-center">
        {snapshot.me.is_host && !rematch && (
          <button
            type="button"
            className={buttonClass}
            disabled={playAgain.isPending}
            onClick={() => playAgain.mutate()}
          >
            Play again
          </button>
        )}
        {rematch && (
          <button
            type="button"
            className={buttonClass}
            disabled={joinRematch.isPending}
            onClick={() => joinRematch.mutate()}
          >
            Join the rematch
          </button>
        )}
        {!snapshot.me.is_host && !rematch && (
          <p className="text-sm text-dim">Waiting for the host to start a rematch…</p>
        )}
      </div>
      <ErrorMessage error={playAgain.error ?? joinRematch.error} />
    </Card>
  )
}

/**
 * "Now" on the server's clock, ticking a few times a second. The offset is measured when a new
 * snapshot arrives, so countdowns stay right even if the device clock is off.
 */
function useServerNow(serverTime: string) {
  const [now, setNow] = useState<number | null>(null)
  useEffect(() => {
    const offset = Date.parse(serverTime) - Date.now()
    const tick = () => setNow(Date.now() + offset)
    const first = setTimeout(tick, 0)
    const timer = setInterval(tick, 250)
    return () => {
      clearTimeout(first)
      clearInterval(timer)
    }
  }, [serverTime])
  return now ?? Date.parse(serverTime)
}

function roundLabel(round: number, roundCount: number) {
  return round === roundCount - 1 ? 'Final' : `Round ${round + 1} of ${roundCount}`
}

function CurrentMatchup({
  snapshot,
  names,
  token,
  onChanged,
}: {
  snapshot: RoomSnapshot
  names: Map<string, string>
  token: string
  onChanged: () => void
}) {
  const tournament = snapshot.tournament!
  const current = tournament.current!
  const matchup = tournament.rounds.flat().find((m) => m.id === current.matchup_id)!
  const now = useServerNow(snapshot.server_time)
  const startsIn = Math.ceil((Date.parse(current.starts_at) - now) / 1000)
  const endsIn = Math.max(0, Math.ceil((Date.parse(current.ends_at) - now) / 1000))
  const open = startsIn <= 0 && endsIn > 0
  const canVote = open && current.can_vote

  const vote = useMutation({
    mutationFn: (contenderId: string) => api.castVote(snapshot.code, token, matchup.id, contenderId),
    onMutate: () => {
      audio.play('vote')
    },
    onSuccess: onChanged,
  })

  // Tick through the last three seconds of voting.
  useEffect(() => {
    if (open && endsIn <= 3) audio.play('tick')
  }, [open, endsIn])
  const close = useMutation({
    mutationFn: () => api.closeMatchup(snapshot.code, token, matchup.id),
    onSuccess: onChanged,
  })

  const sides = [matchup.contender_a_id!, matchup.contender_b_id!]
  useEffect(() => {
    if (!canVote) return
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return
      if (event.key === 'ArrowLeft' || event.key === '1') vote.mutate(sides[0])
      if (event.key === 'ArrowRight' || event.key === '2') vote.mutate(sides[1])
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const voted = new Set(current.voted_participant_ids)
  return (
    <section aria-label="Current matchup" className="rounded-md border-2 border-line bg-panel/90 p-4 shadow-[4px_4px_0_0_rgb(0_0_0/0.5)]">
      <p className="text-center font-arcade text-[10px] tracking-widest text-dim uppercase">
        {roundLabel(matchup.round, tournament.rounds.length)}
      </p>
      {current.phase === 'revote' && (
        <p className="mt-2 text-center font-arcade text-[10px] leading-relaxed text-coin uppercase">
          Tie {matchup.votes_a}–{matchup.votes_b}! Sudden-death revote
        </p>
      )}
      {/* Keyed by matchup and phase so each new fight slams in. */}
      <div
        key={`${matchup.id}:${current.phase}`}
        className="mt-4 grid grid-cols-1 items-center gap-3 sm:grid-cols-[1fr_auto_1fr]"
      >
        {sides.map((id, i) => (
          <VoteButton
            key={id}
            name={names.get(id) ?? '?'}
            selected={current.my_vote === id}
            disabled={!canVote || vote.isPending}
            onClick={() => vote.mutate(id)}
            side={i === 0 ? 'p1' : 'p2'}
          />
        ))}
        <motion.span
          className="arcade-glow order-2 text-center font-arcade text-xl text-coin"
          initial={{ scale: 3.5, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: 'spring', stiffness: 500, damping: 14, delay: 0.25 }}
        >
          VS
        </motion.span>
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 text-sm text-dim">
        <span className={`font-arcade text-[11px] ${open && endsIn <= 5 ? 'text-p1' : 'text-white'}`}>
          {startsIn > 0 ? `Voting opens in ${startsIn}s` : `${endsIn}s left`}
        </span>
        <span>
          {voted.size}/{current.eligible_count} voted
        </span>
      </div>
      <ul aria-label="Votes cast" className="mt-2 flex flex-wrap gap-2">
        {snapshot.participants.map((p) => (
          <li
            key={p.id}
            className={`rounded px-2 py-0.5 text-xs ${voted.has(p.id) ? 'bg-go text-ink' : 'bg-panel-hi text-dim/80'}`}
          >
            {p.nickname}
          </li>
        ))}
      </ul>
      {!current.can_vote && (
        <p className="mt-3 text-sm text-dim">You joined after this matchup opened. You can vote in the next one.</p>
      )}
      {snapshot.me.is_host && (
        <button type="button" className={`${subtleButtonClass} mt-3`} onClick={() => close.mutate()}>
          End voting now
        </button>
      )}
      <ErrorMessage error={vote.error ?? close.error} />
    </section>
  )
}

function VoteButton({
  name,
  selected,
  disabled,
  onClick,
  side,
}: {
  name: string
  selected: boolean
  disabled: boolean
  onClick: () => void
  side: 'p1' | 'p2'
}) {
  const colors =
    side === 'p1'
      ? 'order-1 border-p1 bg-p1/15 hover:bg-p1/25'
      : 'order-3 border-p2 bg-p2/15 hover:bg-p2/25'

  return (
    <motion.button
      type="button"
      initial={{ x: side === 'p1' ? -80 : 80, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ type: 'spring', stiffness: 380, damping: 24 }}
      aria-label={`Vote for ${name}`}
      aria-pressed={selected}
      disabled={disabled}
      onClick={onClick}
      className={`${colors} min-h-28 rounded-md border-2 border-b-4 px-3 py-4 text-xl font-black break-words text-white transition-transform active:translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-50 ${selected ? 'ring-4 ring-go ring-offset-2 ring-offset-ink' : ''}`}
    >
      {name}
    </motion.button>
  )
}

function LastResult({ tournament, names }: { tournament: Tournament; names: Map<string, string> }) {
  const last = tournament.rounds
    .flat()
    .filter((m) => m.status === 'decided' && !m.is_bye)
    .at(-1)
  if (!last) return null

  const winnerIsA = last.winner_id === last.contender_a_id
  const winner = names.get(last.winner_id!)
  const loser = names.get((winnerIsA ? last.contender_b_id : last.contender_a_id)!)
  const [won, lost] = winnerIsA ? [last.votes_a, last.votes_b] : [last.votes_b, last.votes_a]
  return (
    <p className="text-center text-white/85">
      {last.outcome === 'coin_flip'
        ? `${winner} beat ${loser} on a coin flip`
        : `${winner} beat ${loser} ${won}–${lost}`}
    </p>
  )
}

export function Bracket({ tournament, names }: { tournament: Tournament; names: Map<string, string> }) {
  const roundCount = tournament.rounds.length
  return (
    <section aria-label="Bracket" className="overflow-x-auto">
      <div className="flex gap-4">
        {tournament.rounds.map((matchups, round) => (
          <div key={round} className="flex min-w-40 flex-1 flex-col justify-around gap-3">
            <h3 className="text-xs uppercase tracking-widest text-dim/80">
              {round === roundCount - 1 ? 'Final' : `Round ${round + 1}`}
            </h3>
            {matchups.map((m) => (
              <BracketMatchup key={m.id} matchup={m} names={names} />
            ))}
          </div>
        ))}
      </div>
    </section>
  )
}

function BracketMatchup({ matchup, names }: { matchup: MatchupOut; names: Map<string, string> }) {
  const side = (id: string | null, votes: number) => {
    if (!id) return <span className="text-dim/60">{matchup.is_bye ? 'bye' : 'TBD'}</span>
    const won = matchup.winner_id === id
    return (
      <motion.span
        // Re-keyed when the winner is decided, so the advancing name flashes gold.
        key={`${id}:${won}`}
        initial={won ? { color: 'var(--color-coin)' } : false}
        animate={won ? { color: '#ffffff' } : undefined}
        transition={{ duration: 1.2 }}
        className={`flex justify-between gap-2 ${won ? 'font-bold text-white' : 'text-dim'}`}
      >
        <span>{names.get(id)}</span>
        {matchup.outcome === 'votes' && <span>{votes}</span>}
      </motion.span>
    )
  }
  return (
    <div
      className={`rounded border px-2 py-1 text-sm ${
        matchup.status === 'voting' || matchup.status === 'revote' ? 'border-coin' : 'border-line'
      }`}
    >
      {side(matchup.contender_a_id, matchup.votes_a)}
      {side(matchup.contender_b_id, matchup.votes_b)}
      {matchup.outcome === 'coin_flip' && <span className="text-xs text-dim/80">coin flip</span>}
    </div>
  )
}
