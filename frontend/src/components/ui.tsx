import type { ReactNode } from 'react'

/** Shared building blocks for the functional (pre-arcade) lobby UI. */

export function Page({ children }: { children: ReactNode }) {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-6 px-4 py-8 text-zinc-100">
      {children}
    </main>
  )
}

export function Card({ children }: { children: ReactNode }) {
  return <section className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">{children}</section>
}

export function ErrorMessage({ error }: { error: unknown }) {
  if (!error) return null
  return (
    <p role="alert" className="text-sm text-red-400">
      {error instanceof Error ? error.message : String(error)}
    </p>
  )
}

export const inputClass =
  'w-full rounded border border-zinc-700 bg-zinc-950 px-3 py-2 text-zinc-100 focus:border-zinc-400 focus:outline-none'

export const buttonClass =
  'rounded bg-zinc-100 px-4 py-2 font-semibold text-zinc-900 hover:bg-white disabled:cursor-not-allowed disabled:opacity-40'

export const subtleButtonClass =
  'rounded border border-zinc-700 px-2 py-1 text-xs text-zinc-300 hover:border-zinc-400'

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
    <label className="flex flex-col gap-1 text-sm">
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
