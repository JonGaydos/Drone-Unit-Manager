/**
 * Authentication context providing user state, login/logout, and role checks.
 * Persists auth token in localStorage and validates on mount via /auth/me.
 */
import { createContext, useContext, useState, useEffect } from 'react'
import { api } from '@/api/client'

const AuthContext = createContext(null)

/**
 * Provides authentication state and actions to the component tree.
 * On mount, validates the stored token against the backend.
 * @param {Object} props
 * @param {React.ReactNode} props.children - Child components.
 * @returns {JSX.Element}
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (token) {
      api.get('/auth/me')
        .then(setUser)
        .catch(() => {
          localStorage.removeItem('token')
          localStorage.removeItem('user')
        })
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [])

  /**
   * Authenticate with username and password, store the token, and set user state.
   * @param {string} username
   * @param {string} password
   * @returns {Promise<Object>} The authenticated user object.
   */
  const login = async (username, password) => {
    const data = await api.post('/auth/login', { username, password })
    localStorage.setItem('token', data.token)
    setUser(data.user)
    return data.user
  }

  /** Clear stored credentials and reset user state. */
  const logout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    setUser(null)
  }

  /**
   * Merge partial updates into the current user state (client-side only).
   * @param {Object} updates - Fields to merge into the user object.
   */
  const updateUser = (updates) => {
    setUser(prev => ({ ...prev, ...updates }))
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, updateUser, isAdmin: user?.role === 'admin', isSupervisor: user?.role === 'admin' || user?.role === 'supervisor', isPilot: user?.role === 'admin' || user?.role === 'supervisor' || user?.role === 'pilot', isManager: user?.role === 'admin' || user?.role === 'manager' || user?.role === 'supervisor' || user?.role === 'pilot', isViewer: user?.role === 'viewer' }}>
      {children}
    </AuthContext.Provider>
  )
}

/**
 * Hook to access authentication context values.
 * Must be used within an AuthProvider.
 * @returns {{ user: Object|null, loading: boolean, login: Function, logout: Function, updateUser: Function, isAdmin: boolean, isSupervisor: boolean, isPilot: boolean, isManager: boolean, isViewer: boolean }}
 */
export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
