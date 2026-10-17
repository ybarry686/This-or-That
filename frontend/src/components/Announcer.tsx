import { AnimatePresence, motion } from 'motion/react'
import type { RoomSnapshot } from '../api/client'
import { useAnnouncements, type Announcement } from '../announcements'
import { useReducedMotion } from '../settings'

const COLORS: Record<Announcement['kind'], string> = {
  round: 'text-coin',
  revote: 'text-p1',
  ko: 'text-p1',
  coin: 'text-coin',
  champion: 'text-coin',
}

/** Full-screen arcade call-outs: ROUND 1 — FIGHT!, K.O.!, SUDDEN DEATH!, CHAMPION. */
export default function Announcer({ tournament }: { tournament: RoomSnapshot['tournament'] }) {
  const announcement = useAnnouncements(tournament)
  const reduceMotion = useReducedMotion()

  return (
    <AnimatePresence>
      {announcement && (
        <motion.div
          key={announcement.id}
          role="status"
          aria-label={announcement.label}
          className="pointer-events-none fixed inset-0 z-30 grid place-items-center bg-ink/70 px-4 text-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          <motion.div
            initial={{ scale: 2.6, rotate: -4 }}
            animate={
              announcement.kind === 'ko'
                ? { scale: 1, rotate: 0, x: [0, -10, 10, -6, 6, 0] }
                : { scale: 1, rotate: 0 }
            }
            transition={{ type: 'spring', stiffness: 420, damping: 18 }}
          >
            {announcement.kind === 'champion' ? (
              <>
                <p className="font-arcade text-sm tracking-widest text-dim sm:text-lg">{announcement.title}</p>
                <p className="arcade-glow mt-4 font-arcade text-3xl leading-tight break-words text-coin sm:text-6xl">
                  {announcement.subtitle}
                </p>
              </>
            ) : (
              <>
                <p className={`arcade-glow font-arcade text-3xl leading-tight uppercase sm:text-6xl ${COLORS[announcement.kind]}`}>
                  {announcement.title}
                </p>
                {announcement.subtitle && (
                  <p className="arcade-glow mt-4 font-arcade text-base leading-relaxed text-white uppercase sm:text-2xl">
                    {announcement.subtitle}
                  </p>
                )}
              </>
            )}
          </motion.div>
          {announcement.kind === 'champion' && !reduceMotion && <Confetti />}
        </motion.div>
      )}
    </AnimatePresence>
  )
}

const CONFETTI_COLORS = ['var(--color-p1)', 'var(--color-p2)', 'var(--color-coin)', 'var(--color-go)']

/** Deterministic pseudo-random in [0, 1) so pieces are stable across renders. */
function seeded(n: number) {
  const x = Math.sin(n * 9301 + 49297) * 233280
  return x - Math.floor(x)
}

const PIECES = Array.from({ length: 60 }, (_, i) => ({
  left: seeded(i) * 100,
  drift: (seeded(i + 100) - 0.5) * 160,
  spin: (seeded(i + 200) - 0.5) * 720,
  delay: seeded(i + 300) * 0.8,
  duration: 2.4 + seeded(i + 400) * 1.6,
  color: CONFETTI_COLORS[i % CONFETTI_COLORS.length],
}))

function Confetti() {
  return (
    <div data-testid="confetti" aria-hidden="true" className="absolute inset-0 overflow-hidden">
      {PIECES.map((p, i) => (
        <motion.span
          key={i}
          className="absolute top-0 block h-3 w-2"
          style={{ left: `${p.left}%`, backgroundColor: p.color }}
          initial={{ y: '-10vh', x: 0, rotate: 0 }}
          animate={{ y: '110vh', x: p.drift, rotate: p.spin }}
          transition={{ duration: p.duration, delay: p.delay, ease: 'easeIn' }}
        />
      ))}
    </div>
  )
}
