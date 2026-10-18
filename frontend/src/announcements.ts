import { useEffect, useState } from 'react'
import type { RoomSnapshot } from './api/client'

type Tournament = NonNullable<RoomSnapshot['tournament']>

export type AnnouncementKind = 'round' | 'revote' | 'ko' | 'coin' | 'champion'

export type Announcement = {
  id: number
  kind: AnnouncementKind
  /** Accessible summary, e.g. "K.O.! Pizza wins 2–1". */
  label: string
  title: string
  subtitle: string
  durationMs: number
}

const DURATIONS: Record<AnnouncementKind, number> = {
  ko: 2200,
  coin: 2200,
  revote: 1800,
  round: 1600,
  champion: 5000,
}

let nextId = 1

function make(kind: AnnouncementKind, title: string, subtitle: string, label: string): Announcement {
  return { id: nextId++, kind, title, subtitle, label, durationMs: DURATIONS[kind] }
}

function lastDecided(t: Tournament | null) {
  return t?.rounds.flat().filter((m) => m.status === 'decided' && !m.is_bye).at(-1) ?? null
}

function currentKey(t: Tournament | null) {
  return t?.current ? `${t.current.matchup_id}:${t.current.phase}` : null
}

/**
 * What should be announced when the room moves from `prev` to `next` (SPEC §10). Derived from
 * authoritative state rather than individual events, so a missed event can't desync the show.
 */
export function announcementsFor(prev: Tournament | null, next: Tournament | null): Announcement[] {
  if (!next) return []
  const names = new Map(next.contenders.map((c) => [c.id, c.display_text]))
  const name = (id: string | null | undefined) => (id ? (names.get(id) ?? '?') : '?')

  if (next.champion_id && next.champion_id !== prev?.champion_id) {
    const champion = name(next.champion_id)
    return [make('champion', 'Champion', champion, `Champion: ${champion}`)]
  }

  const out: Announcement[] = []
  const decided = lastDecided(next)
  if (decided && decided.id !== lastDecided(prev)?.id) {
    const winnerIsA = decided.winner_id === decided.contender_a_id
    const [won, lost] = winnerIsA ? [decided.votes_a, decided.votes_b] : [decided.votes_b, decided.votes_a]
    out.push(
      decided.outcome === 'coin_flip'
        ? make('coin', 'Coin flip!', `${name(decided.winner_id)} wins`, `Coin flip! ${name(decided.winner_id)} wins`)
        : make('ko', 'K.O.!', `${name(decided.winner_id)} wins ${won}–${lost}`, `K.O.! ${name(decided.winner_id)} wins ${won}–${lost}`),
    )
  }

  if (next.current && currentKey(next) !== currentKey(prev)) {
    const matchup = next.rounds.flat().find((m) => m.id === next.current!.matchup_id)
    if (next.current.phase === 'revote') {
      const tied = matchup ? `Tied ${matchup.votes_a}–${matchup.votes_b}` : ''
      out.push(make('revote', 'Sudden death!', tied, `Sudden death! ${tied}`.trim()))
    } else if (matchup) {
      const final = matchup.round === next.rounds.length - 1
      const title = final ? 'Final' : `Round ${matchup.round + 1}`
      out.push(make('round', title, 'Fight!', `${title} — Fight!`))
    }
  }
  return out
}

/** Queue of announcements for the room, played one at a time. Nothing replays on first load. */
export function useAnnouncements(tournament: Tournament | null) {
  const [seen, setSeen] = useState(tournament)
  const [queue, setQueue] = useState<Announcement[]>([])

  if (tournament !== seen) {
    // Adjusting state while rendering, React's pattern for reacting to a changed prop.
    const fresh = announcementsFor(seen, tournament)
    setSeen(tournament)
    if (fresh.length) setQueue((q) => [...q, ...fresh])
  }

  const head = queue[0]
  useEffect(() => {
    if (!head) return
    const timer = setTimeout(() => setQueue((q) => q.slice(1)), head.durationMs)
    return () => clearTimeout(timer)
  }, [head])

  return head ?? null
}
