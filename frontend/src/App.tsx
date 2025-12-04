import { Route, Routes } from 'react-router-dom'

import SidebarLayout from '@/components/layouts/SidebarLayout'
import { ThemeProvider } from '@/components/theme-provider'
import About from '@/pages/About'
import Dashboard from '@/pages/Dashboard'
import DiscordCallback from '@/pages/DiscordCallback'
import LoginPage from '@/pages/login'
import NotFound from '@/pages/NotFound'

function App() {
  return (
    <ThemeProvider defaultTheme="dark" storageKey="vite-ui-theme">
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/auth/discord/callback" element={<DiscordCallback />} />
        <Route element={<SidebarLayout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/about" element={<About />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </ThemeProvider>
  )
}

export default App
