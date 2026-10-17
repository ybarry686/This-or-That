import { useEffect } from 'react'
import { audio } from '../audio'
import { getSettings, setSetting, useReducedMotion, useSettings } from '../settings'

/** Sound, music, CRT and motion toggles, shown on every screen. */
export default function SettingsBar() {
  const settings = useSettings()
  const reduceMotion = useReducedMotion()

  useEffect(() => {
    document.documentElement.dataset.crt = settings.crt ? 'on' : 'off'
    document.documentElement.dataset.motion = reduceMotion ? 'reduced' : 'full'
  }, [settings.crt, reduceMotion])

  // Browsers only allow audio after a gesture: if sound or music was left on last visit,
  // the first tap anywhere unlocks it.
  useEffect(() => {
    const unlockOnce = () => {
      const { sound, music } = getSettings()
      if (!sound && !music) return
      audio.unlock()
      if (music) audio.startMusic()
    }
    window.addEventListener('pointerdown', unlockOnce, { once: true })
    return () => window.removeEventListener('pointerdown', unlockOnce)
  }, [])

  const toggleSound = () => {
    if (!settings.sound) audio.unlock()
    setSetting('sound', !settings.sound)
  }

  const toggleMusic = () => {
    if (settings.music) {
      setSetting('music', false)
      audio.stopMusic()
    } else {
      audio.unlock()
      setSetting('music', true)
      audio.startMusic()
    }
  }

  return (
    <nav aria-label="Settings" className="fixed top-2 right-2 z-40 flex gap-1">
      <Toggle label="Sound" icon={settings.sound ? '🔊' : '🔇'} pressed={settings.sound} onClick={toggleSound} />
      <Toggle label="Music" icon="♫" pressed={settings.music} onClick={toggleMusic} />
      <Toggle label="CRT effect" icon="▤" pressed={settings.crt} onClick={() => setSetting('crt', !settings.crt)} />
      <Toggle
        label="Reduce motion"
        icon="◐"
        pressed={reduceMotion}
        onClick={() => setSetting('reduceMotion', !reduceMotion)}
      />
    </nav>
  )
}

function Toggle({
  label,
  icon,
  pressed,
  onClick,
}: {
  label: string
  icon: string
  pressed: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      aria-label={label}
      aria-pressed={pressed}
      title={label}
      onClick={onClick}
      className={`grid h-9 w-9 place-items-center rounded border-2 text-sm transition-colors ${
        pressed ? 'border-coin bg-coin/15 text-coin' : 'border-line bg-panel text-dim hover:text-white'
      }`}
    >
      <span aria-hidden="true">{icon}</span>
    </button>
  )
}
