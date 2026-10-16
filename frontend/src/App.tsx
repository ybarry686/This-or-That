import { useEffect, useState } from 'react'
import { getHealth } from './api/client'

type ApiStatus = 'checking' | 'online' | 'offline'

function App() {
  const [apiStatus, setApiStatus] = useState<ApiStatus>('checking')

  useEffect(() => {
    getHealth()
      .then(() => setApiStatus('online'))
      .catch(() => setApiStatus('offline'))
  }, [])

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-zinc-950 p-4 text-zinc-100">
      <h1 className="text-5xl font-black tracking-widest">THIS OR THAT</h1>
      <p role="status" className="text-sm text-zinc-400">
        API: {apiStatus}
      </p>
    </main>
  )
}

export default App
