import { createContext, useContext, useEffect, useMemo, useState } from 'react'

import { type Theme, updateUserPreferences } from '@/api'
import { useAuth } from '@/contexts/AuthContext'

type ThemeProviderProps = {
  children: React.ReactNode
  storageKey?: string
}

type ThemeProviderState = {
  theme: Theme
  resolvedTheme: 'dark' | 'light'
  setTheme: (theme: Theme) => void
}

const initialState: ThemeProviderState = {
  theme: 'system',
  resolvedTheme: 'dark',
  setTheme: () => null,
}

const ThemeProviderContext = createContext<ThemeProviderState>(initialState)

function getSystemTheme(): 'dark' | 'light' {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function ThemeProvider({
  children,
  storageKey = 'vite-ui-theme',
  ...props
}: ThemeProviderProps) {
  const { user } = useAuth()

  const [theme, setThemeState] = useState<Theme>(
    () => (localStorage.getItem(storageKey) as Theme) || 'dark'
  )
  const [systemTheme, setSystemTheme] = useState<'dark' | 'light'>(getSystemTheme)
  const [syncedUserId, setSyncedUserId] = useState<string | null>(null)

  // Sync theme from user on login (adjust-state-from-props pattern)
  if (user?.id && syncedUserId !== user.id) {
    setSyncedUserId(user.id)
    if (user.theme && theme !== user.theme) {
      setThemeState(user.theme)
      localStorage.setItem(storageKey, user.theme)
    }
  }
  if (!user && syncedUserId !== null) {
    setSyncedUserId(null)
  }

  const resolvedTheme = useMemo(() => {
    return theme === 'system' ? systemTheme : theme
  }, [theme, systemTheme])

  useEffect(() => {
    const root = window.document.documentElement
    root.classList.remove('light', 'dark')
    root.classList.add(resolvedTheme)
  }, [resolvedTheme])

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e: MediaQueryListEvent) => {
      setSystemTheme(e.matches ? 'dark' : 'light')
    }
    mediaQuery.addEventListener('change', handler)
    return () => mediaQuery.removeEventListener('change', handler)
  }, [])

  const value = {
    theme,
    resolvedTheme,
    setTheme: (newTheme: Theme) => {
      localStorage.setItem(storageKey, newTheme)
      setThemeState(newTheme)

      // Persist to server if logged in
      if (user) {
        updateUserPreferences({ theme: newTheme }).catch(err => {
          console.error('Failed to save theme preference:', err)
        })
      }
    },
  }

  return (
    <ThemeProviderContext.Provider {...props} value={value}>
      {children}
    </ThemeProviderContext.Provider>
  )
}

export const useTheme = () => {
  const context = useContext(ThemeProviderContext)

  if (context === undefined) throw new Error('useTheme must be used within a ThemeProvider')

  return context
}
