/**
 * Theme context for managing application color themes.
 * Persists the selected theme in localStorage and syncs with the user's backend profile.
 */
import { createContext, useContext, useState, useEffect } from 'react'
import { api } from '@/api/client'

const ThemeContext = createContext(null)

/** @type {Array<{id: string, name: string}>} Available application themes. */
export const THEMES = [
  { id: 'dark', name: 'Dark' },
  { id: 'light', name: 'Light' },
  { id: 'glass', name: 'Glass' },
  { id: 'grafana', name: 'Grafana' },
  { id: 'blue', name: 'Blue' },
  { id: 'high-contrast', name: 'High Contrast' },
]

/**
 * Provides theme state and setter to the component tree.
 * Applies the theme as a data attribute on the document root element.
 * @param {Object} props
 * @param {React.ReactNode} props.children - Child components.
 * @returns {JSX.Element}
 */
export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(() => {
    return localStorage.getItem('theme') || 'dark'
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  /**
   * Update the active theme locally and persist to the backend.
   * @param {string} newTheme - Theme ID to activate.
   */
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

/**
 * Hook to access the current theme and theme setter.
 * Must be used within a ThemeProvider.
 * @returns {{ theme: string, setTheme: Function }}
 */
export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider')
  return ctx
}
