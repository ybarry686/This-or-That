import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router'
import SettingsBar from './components/SettingsBar'
import Landing from './pages/Landing'
import Recover from './pages/Recover'
import RoomPage from './pages/RoomPage'

export function AppRoutes() {
  return (
    <>
      <SettingsBar />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/r/:code" element={<RoomPage />} />
        <Route path="/r/:code/recover" element={<Recover />} />
      </Routes>
    </>
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
