import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MotionConfig } from 'motion/react'
import { BrowserRouter, Route, Routes } from 'react-router'
import SettingsBar from './components/SettingsBar'
import Landing from './pages/Landing'
import Recover from './pages/Recover'
import RoomPage from './pages/RoomPage'
import { useReducedMotion } from './settings'

export function AppRoutes() {
  const reduceMotion = useReducedMotion()
  return (
    // Reduced motion keeps fades but drops movement, scaling and shakes (SPEC §10).
    <MotionConfig reducedMotion={reduceMotion ? 'always' : 'never'}>
      <SettingsBar />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/r/:code" element={<RoomPage />} />
        <Route path="/r/:code/recover" element={<Recover />} />
      </Routes>
    </MotionConfig>
  )
}

const queryClient = new QueryClient()

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </QueryClientProvider>
  )
}
