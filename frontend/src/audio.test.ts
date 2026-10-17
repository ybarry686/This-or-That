import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { audio } from './audio'
import { resetSettingsForTests, setSetting } from './settings'

/** Records what the synth asks the Web Audio API to do. */
class FakeAudioContext {
  static instances: FakeAudioContext[] = []
  currentTime = 0
  state: 'suspended' | 'running' = 'suspended'
  destination = {}
  oscillators: { type: string; started: boolean; stopped: boolean }[] = []

  constructor() {
    FakeAudioContext.instances.push(this)
  }

  resume() {
    this.state = 'running'
    return Promise.resolve()
  }

  createOscillator() {
    const osc = {
      type: 'sine',
      started: false,
      stopped: false,
      frequency: { value: 0, setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn(), linearRampToValueAtTime: vi.fn() },
      connect: vi.fn(),
      start: () => {
        osc.started = true
      },
      stop: () => {
        osc.stopped = true
      },
    }
    this.oscillators.push(osc)
    return osc
  }

  createGain() {
    return {
      gain: { value: 1, setValueAtTime: vi.fn(), linearRampToValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() },
      connect: vi.fn(),
    }
  }

  createBuffer(_channels: number, length: number) {
    return { getChannelData: () => new Float32Array(length) }
  }

  createBufferSource() {
    return { buffer: null, connect: vi.fn(), start: vi.fn(), stop: vi.fn() }
  }
}

beforeEach(() => {
  localStorage.clear()
  resetSettingsForTests()
  FakeAudioContext.instances = []
  audio.resetForTests()
})

afterEach(() => {
  audio.stopMusic()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('without Web Audio support', () => {
  it('does nothing and never throws', () => {
    vi.stubGlobal('AudioContext', undefined)
    setSetting('sound', true)

    expect(() => audio.unlock()).not.toThrow()
    expect(audio.play('ko')).toBe(false)
    expect(() => audio.startMusic()).not.toThrow()
  })
})

describe('sound effects', () => {
  beforeEach(() => {
    vi.stubGlobal('AudioContext', FakeAudioContext)
  })

  it('stays silent while sound is off (the default)', () => {
    audio.unlock()

    expect(audio.play('round')).toBe(false)
    expect(FakeAudioContext.instances.flatMap((c) => c.oscillators)).toHaveLength(0)
  })

  it('stays silent until a user gesture has unlocked audio', () => {
    setSetting('sound', true)

    expect(audio.play('round')).toBe(false)
    expect(FakeAudioContext.instances).toHaveLength(0)
  })

  it.each(['round', 'ko', 'coin', 'revote', 'champion', 'vote', 'tick'] as const)(
    'plays the %s cue once sound is on and unlocked',
    (cue) => {
      setSetting('sound', true)
      audio.unlock()

      expect(audio.play(cue)).toBe(true)
      const oscillators = FakeAudioContext.instances[0].oscillators
      expect(oscillators.length).toBeGreaterThan(0)
      expect(oscillators.every((o) => o.started && o.stopped)).toBe(true)
    },
  )

  it('reuses a single audio context', () => {
    setSetting('sound', true)
    audio.unlock()
    audio.play('vote')
    audio.play('vote')

    expect(FakeAudioContext.instances).toHaveLength(1)
  })
})

describe('music', () => {
  beforeEach(() => {
    vi.stubGlobal('AudioContext', FakeAudioContext)
    vi.useFakeTimers()
  })

  it('schedules a looping tune while music is on', () => {
    setSetting('music', true)
    audio.unlock()

    audio.startMusic()
    vi.advanceTimersByTime(4000)

    expect(audio.isMusicPlaying()).toBe(true)
    expect(FakeAudioContext.instances[0].oscillators.length).toBeGreaterThan(8)
  })

  it('stops scheduling notes when stopped', () => {
    setSetting('music', true)
    audio.unlock()
    audio.startMusic()
    vi.advanceTimersByTime(1000)

    audio.stopMusic()
    const count = FakeAudioContext.instances[0].oscillators.length
    vi.advanceTimersByTime(4000)

    expect(audio.isMusicPlaying()).toBe(false)
    expect(FakeAudioContext.instances[0].oscillators).toHaveLength(count)
  })

  it('does not start while music is off', () => {
    audio.unlock()
    audio.startMusic()

    expect(audio.isMusicPlaying()).toBe(false)
  })
})
