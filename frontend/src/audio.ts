import { getSettings } from './settings'

/**
 * 8-bit sound effects and a looping chiptune, synthesized with the Web Audio API (SPEC §10).
 * Nothing plays until the player turns sound or music on, and an AudioContext is only created
 * from a user gesture (`unlock`). Every call is a silent no-op if Web Audio is unavailable or
 * fails, so audio can never break the game.
 */

export type Cue = 'round' | 'ko' | 'coin' | 'revote' | 'champion' | 'vote' | 'tick'

type Wave = OscillatorType
type Note = {
  freq: number
  at: number
  length: number
  wave?: Wave
  volume?: number
  /** Pitch to slide to by the end of the note. */
  slideTo?: number
}

const midi = (n: number) => 440 * 2 ** ((n - 69) / 12)
const seq = (notes: number[], step: number, wave: Wave = 'square', volume = 0.1): Note[] =>
  notes.map((n, i) => ({ freq: midi(n), at: i * step, length: step * 0.9, wave, volume }))

const CUES: Record<Cue, Note[]> = {
  vote: [{ freq: 880, at: 0, length: 0.06, volume: 0.12 }],
  tick: [{ freq: 1250, at: 0, length: 0.03, volume: 0.07 }],
  round: [...seq([72, 76, 79], 0.09), { freq: midi(84), at: 0.27, length: 0.3, volume: 0.12 }],
  revote: seq([76, 69, 76, 69], 0.17, 'square', 0.1),
  coin: [
    { freq: midi(83), at: 0, length: 0.08, volume: 0.1 },
    { freq: midi(88), at: 0.08, length: 0.4, volume: 0.1 },
  ],
  ko: [
    { freq: 520, at: 0, length: 0.55, wave: 'sawtooth', volume: 0.14, slideTo: 55 },
    { freq: 130, at: 0.05, length: 0.4, wave: 'square', volume: 0.08, slideTo: 40 },
  ],
  champion: [
    ...seq([72, 76, 79], 0.12),
    { freq: midi(84), at: 0.36, length: 0.3, volume: 0.12 },
    { freq: midi(79), at: 0.7, length: 0.12, volume: 0.1 },
    { freq: midi(84), at: 0.84, length: 0.7, volume: 0.12 },
    { freq: midi(48), at: 0, length: 0.36, wave: 'triangle', volume: 0.15 },
    { freq: midi(43), at: 0.36, length: 0.34, wave: 'triangle', volume: 0.15 },
    { freq: midi(48), at: 0.7, length: 0.84, wave: 'triangle', volume: 0.15 },
  ],
}

// A short, original A-minor loop: 16 eighth-note melody steps over a 4-note bass line.
const TEMPO_STEP = 60 / 140 / 2
const MELODY = [69, 72, 76, 81, 79, 76, 72, 76, 65, 69, 72, 77, 76, 72, 71, 67]
const BASS = [45, 43, 41, 40]
const BAR_SECONDS = MELODY.length * TEMPO_STEP

type AudioContextConstructor = new () => AudioContext

function audioContextClass(): AudioContextConstructor | null {
  const w = window as unknown as {
    AudioContext?: AudioContextConstructor
    webkitAudioContext?: AudioContextConstructor
  }
  return w.AudioContext ?? w.webkitAudioContext ?? null
}

class ArcadeAudio {
  private ctx: AudioContext | null = null
  private musicGain: GainNode | null = null
  private musicTimer: ReturnType<typeof setTimeout> | undefined

  /** Create/resume the audio context. Call from a user gesture (e.g. a toggle click). */
  unlock() {
    try {
      if (!this.ctx) {
        const Ctor = audioContextClass()
        if (!Ctor) return
        this.ctx = new Ctor()
      }
      void this.ctx.resume?.()
    } catch {
      this.ctx = null
    }
  }

  play(cue: Cue): boolean {
    if (!getSettings().sound || !this.ctx) return false
    try {
      const start = this.ctx.currentTime + 0.01
      for (const note of CUES[cue]) this.schedule(note, start, this.ctx.destination)
      return true
    } catch {
      return false
    }
  }

  startMusic() {
    if (!getSettings().music || !this.ctx || this.musicTimer !== undefined) return
    try {
      this.musicGain = this.ctx.createGain()
      this.musicGain.gain.setValueAtTime(0.5, this.ctx.currentTime)
      this.musicGain.connect(this.ctx.destination)
      this.scheduleBar(this.ctx.currentTime + 0.05)
    } catch {
      this.stopMusic()
    }
  }

  stopMusic() {
    clearTimeout(this.musicTimer)
    this.musicTimer = undefined
    try {
      if (this.ctx && this.musicGain) this.musicGain.gain.setValueAtTime(0, this.ctx.currentTime)
    } catch {
      // Already silent.
    }
    this.musicGain = null
  }

  isMusicPlaying() {
    return this.musicTimer !== undefined
  }

  resetForTests() {
    this.stopMusic()
    this.ctx = null
  }

  /** Queue one bar of music starting at `start`, then queue the next bar shortly before it. */
  private scheduleBar(start: number) {
    if (!this.ctx || !this.musicGain) return
    const gain = this.musicGain
    for (const note of seq(MELODY, TEMPO_STEP, 'square', 0.05)) this.schedule(note, start, gain)
    for (const note of seq(BASS, BAR_SECONDS / BASS.length, 'triangle', 0.09)) this.schedule(note, start, gain)
    this.musicTimer = setTimeout(
      () => this.scheduleBar(start + BAR_SECONDS),
      Math.max(0, (BAR_SECONDS - 0.15) * 1000),
    )
  }

  private schedule(note: Note, start: number, output: AudioNode) {
    const ctx = this.ctx!
    const at = start + note.at
    const end = at + note.length
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = note.wave ?? 'square'
    osc.frequency.setValueAtTime(note.freq, at)
    if (note.slideTo) osc.frequency.exponentialRampToValueAtTime(note.slideTo, end)
    // Short attack and release so notes don't click.
    gain.gain.setValueAtTime(0, at)
    gain.gain.linearRampToValueAtTime(note.volume ?? 0.1, at + 0.005)
    gain.gain.linearRampToValueAtTime(0, end)
    osc.connect(gain)
    gain.connect(output)
    osc.start(at)
    osc.stop(end + 0.02)
  }
}

export const audio = new ArcadeAudio()
