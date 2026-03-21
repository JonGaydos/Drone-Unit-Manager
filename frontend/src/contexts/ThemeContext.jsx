import { createContext, useContext, useState, useEffect } from 'react'
import { api } from '@/api/client'

const ThemeContext = createContext(null)

export const THEMES = [
  { id: 'dark', name: 'Dark' },
  { id: 'light', name: 'Light' },
  { id: 'glass', name: 'Glass' },
  { id: 'grafana', name: 'Grafana' },
  { id: 'blue', name: 'Blue' },
  { id: 'high-contrast', name: 'High Contrast' },
]

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(() => {
    return localStorage.getItem('theme') || 'dark'
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  const setTheme = async (newTheme) => {
    setThemeState(newTheme)
    try {
      await api.patch('/auth/me', { theme: newTheme })
    } catch {
      // User might not be logged in yet
    }
  }

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider')
  return ctx
}
