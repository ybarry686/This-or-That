import { act, render, renderHook, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import SettingsBar from './components/SettingsBar'
import { resetSettingsForTests, setSetting, useReducedMotion, useSettings } from './settings'

function mockReducedMotionQuery(matches: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({
      matches: query.includes('prefers-reduced-motion') ? matches : false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  )
}

beforeEach(() => {
  localStorage.clear()
  mockReducedMotionQuery(false)
  resetSettingsForTests()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  document.documentElement.removeAttribute('data-crt')
})

describe('settings', () => {
  it('starts muted, with the CRT effect on and motion following the system', () => {
    const { result } = renderHook(() => useSettings())

    expect(result.current).toEqual({ sound: false, music: false, crt: true, reduceMotion: null })
  })

  it('remembers changes on this device', () => {
    act(() => setSetting('sound', true))

    resetSettingsForTests()
    const { result } = renderHook(() => useSettings())
    expect(result.current.sound).toBe(true)
  })

  it('keeps working when storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    resetSettingsForTests()

    const { result } = renderHook(() => useSettings())
    act(() => setSetting('music', true))
    expect(result.current.music).toBe(true)
  })

  it('ignores corrupt stored settings', () => {
    localStorage.setItem('tot:settings', '{"sound": "loud"')
    resetSettingsForTests()

    const { result } = renderHook(() => useSettings())
    expect(result.current.sound).toBe(false)
  })
})

describe('reduced motion', () => {
  it('follows the system preference by default', () => {
    mockReducedMotionQuery(true)

    const { result } = renderHook(() => useReducedMotion())
    expect(result.current).toBe(true)
  })

  it('can be overridden either way', () => {
    mockReducedMotionQuery(true)
    const { result } = renderHook(() => useReducedMotion())

    act(() => setSetting('reduceMotion', false))
    expect(result.current).toBe(false)

    act(() => setSetting('reduceMotion', true))
    expect(result.current).toBe(true)
  })
})

describe('SettingsBar', () => {
  it('shows each toggle with its current state', () => {
    render(<SettingsBar />)

    expect(screen.getByRole('button', { name: /sound/i })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: /music/i })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: /crt/i })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: /reduce motion/i })).toHaveAttribute('aria-pressed', 'false')
  })

  it('toggles sound', async () => {
    const user = userEvent.setup()
    render(<SettingsBar />)

    await user.click(screen.getByRole('button', { name: /sound/i }))

    expect(screen.getByRole('button', { name: /sound/i })).toHaveAttribute('aria-pressed', 'true')
  })

  it('switches the CRT effect on the page', async () => {
    const user = userEvent.setup()
    render(<SettingsBar />)
    expect(document.documentElement).toHaveAttribute('data-crt', 'on')

    await user.click(screen.getByRole('button', { name: /crt/i }))

    expect(document.documentElement).toHaveAttribute('data-crt', 'off')
  })

  it('turns reduced motion on even when the system does not ask for it', async () => {
    const user = userEvent.setup()
    render(<SettingsBar />)

    await user.click(screen.getByRole('button', { name: /reduce motion/i }))

    expect(screen.getByRole('button', { name: /reduce motion/i })).toHaveAttribute('aria-pressed', 'true')
  })
})
