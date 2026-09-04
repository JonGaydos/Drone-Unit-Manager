/**
 * Theme context for managing application color themes.
 * Persists the selected theme in localStorage and syncs with the user's backend profile.
 */
import { createContext, useContext, useState, useEffect, useMemo, useCallback } from 'react'
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
  { id: 'midnight-slate', name: 'Midnight Slate' },
  { id: 'ranger-green', name: 'Ranger Green' },
  { id: 'navy-brass', name: 'Navy Brass' },
  { id: 'arctic', name: 'Arctic' },
  { id: 'carbon-amber', name: 'Carbon Amber' },
  { id: 'night-vision', name: 'Night Vision' },
  { id: 'sandstone', name: 'Sandstone' },
  { id: 'field-sage', name: 'Field Sage' },
]

/**
 * Provides theme state and setter to the component tree.
 * Applies the theme as a data attribute on the document root element.
 * @param {Object} props
 * @param {React.ReactNode} props.children - Child components.
 * @returns {JSX.Element}
 */
export function ThemeProvider({ children }) {
  const [currentTheme, setCurrentTheme] = useState(() => {
    return localStorage.getItem('theme') || 'dark'
  })

  useEffect(() => {
    document.documentElement.dataset.theme = currentTheme
    localStorage.setItem('theme', currentTheme)
  }, [currentTheme])

  /**
   * Update the active theme locally and persist to the backend.
   * @param {string} newTheme - Theme ID to activate.
   */
  const setTheme = useCallback(async (newTheme) => {
    setCurrentTheme(newTheme)
    try {
      await api.patch('/auth/me', { theme: newTheme })
    } catch {
      // User might not be logged in yet
    }
  }, [])

  const contextValue = useMemo(() => ({ theme: currentTheme, setTheme }), [currentTheme, setTheme])

  return (
    <ThemeContext.Provider value={contextValue}>
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
