import type { ReactNode } from 'react'

/** Shared building blocks in the retro arcade style. */

export function Page({ children }: { children: ReactNode }) {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-6 px-4 pt-14 pb-10">
      {children}
    </main>
  )
}

export function Card({ children }: { children: ReactNode }) {
  return (
    <section className="rounded-md border-2 border-line bg-panel/90 p-4 shadow-[4px_4px_0_0_rgb(0_0_0/0.5)]">
      {children}
    </section>
  )
}

/** Section heading in the pixel font. */
export function ArcadeHeading({ children, as: Tag = 'h2' }: { children: ReactNode; as?: 'h1' | 'h2' | 'h3' }) {
  return <Tag className="mb-3 font-arcade text-xs leading-relaxed tracking-wider text-coin uppercase">{children}</Tag>
}

export function ErrorMessage({ error }: { error: unknown }) {
  if (!error) return null
  return (
    <p role="alert" className="mt-2 text-sm font-semibold text-p1">
      {error instanceof Error ? error.message : String(error)}
    </p>
  )
}

export const inputClass =
  'w-full rounded border-2 border-line bg-ink px-3 py-2 text-white placeholder:text-dim/60 focus:border-p2 focus:outline-none'

export const buttonClass =
  'rounded border-2 border-b-4 border-coin bg-coin px-4 py-2 font-arcade text-[11px] uppercase tracking-wider text-ink transition-transform hover:brightness-110 active:translate-y-0.5 active:border-b-2 disabled:cursor-not-allowed disabled:opacity-40'

export const subtleButtonClass =
  'rounded border-2 border-line px-2 py-1 text-xs font-semibold text-dim hover:border-dim hover:text-white'

export function NumberField({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string
  value: number
  min: number
  max: number
  onChange: (value: number) => void
}) {
  return (
    <label className="flex flex-col gap-1 text-sm text-dim">
      {label}
      <input
        type="number"
        className={inputClass}
        value={Number.isNaN(value) ? '' : value}
        min={min}
        max={max}
        onChange={(e) => onChange(e.target.valueAsNumber)}
        required
      />
    </label>
  )
}
