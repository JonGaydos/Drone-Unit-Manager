/**
 * Authentication context providing user state, login/logout, and role checks.
 * Persists auth token in localStorage and validates on mount via /auth/me.
 */
import { createContext, useContext, useState, useEffect, useMemo, useCallback } from 'react'
import { api, resetSessionExpired } from '@/api/client'

const AuthContext = createContext(null)

/** A signed-in browser locks after this long with no input. The server token
 *  lives 12 hours; this covers a screen left unattended. */
export const IDLE_LIMIT_MS = 30 * 60 * 1000
const IDLE_CHECK_MS = 60 * 1000
// Activity is stamped at most this often, so a moving mouse is not a stream of
// localStorage writes.
const ACTIVITY_WRITE_MS = 15 * 1000
// Shared through localStorage so activity in any open tab keeps every tab alive.
export const LAST_ACTIVITY_KEY = 'lastActivity'
/** Set when the idle lock signs someone out, so the login page can say why. */
export const IDLE_NOTICE_KEY = 'signedOutIdle'
const ACTIVITY_EVENTS = ['pointerdown', 'keydown', 'touchstart', 'wheel', 'scroll']

function markActivity() {
  localStorage.setItem(LAST_ACTIVITY_KEY, String(Date.now()))
}

function idleExpired() {
  const last = Number(localStorage.getItem(LAST_ACTIVITY_KEY))
  return last > 0 && Date.now() - last > IDLE_LIMIT_MS
}

function clearLocalSession() {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  localStorage.removeItem(LAST_ACTIVITY_KEY)
}

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
    if (token && idleExpired()) {
      // Reopened after sitting idle past the limit: lock before any request.
      sessionStorage.setItem(IDLE_NOTICE_KEY, '1')
      clearLocalSession()
      setLoading(false)
    } else if (token) {
      api.get('/auth/me')
        .then(setUser)
        .catch(clearLocalSession)
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [])

  // Idle lock. Runs while someone is signed in: input stamps activity, and a
  // periodic check (plus one whenever the tab is shown again) signs out after
  // IDLE_LIMIT_MS without any. The lock only drops this browser's token; it does
  // not revoke the user's other devices the way an explicit logout does.
  const signedIn = Boolean(user)
  useEffect(() => {
    if (!signedIn) return undefined
    markActivity()
    let lastWrite = Date.now()
    const onActivity = () => {
      const now = Date.now()
      if (now - lastWrite > ACTIVITY_WRITE_MS) {
        lastWrite = now
        markActivity()
      }
    }
    const check = () => {
      if (idleExpired()) {
        sessionStorage.setItem(IDLE_NOTICE_KEY, '1')
        clearLocalSession()
        setUser(null)
      }
    }
    ACTIVITY_EVENTS.forEach(e => globalThis.addEventListener(e, onActivity, { passive: true }))
    document.addEventListener('visibilitychange', check)
    const timer = setInterval(check, IDLE_CHECK_MS)
    return () => {
      ACTIVITY_EVENTS.forEach(e => globalThis.removeEventListener(e, onActivity))
      document.removeEventListener('visibilitychange', check)
      clearInterval(timer)
    }
  }, [signedIn])

  /**
   * Authenticate with username and password, store the token, and set user state.
   * @param {string} username
   * @param {string} password
   * @returns {Promise<Object>} The authenticated user object.
   */
  const login = useCallback(async (username, password) => {
    const data = await api.post('/auth/login', { username, password })
    localStorage.setItem('token', data.token)
    markActivity()
    sessionStorage.removeItem(IDLE_NOTICE_KEY)
    // Re-arm the once-per-session 401 logout guard so a later expiry redirects.
    resetSessionExpired()
    setUser(data.user)
    return data.user
  }, [])

  /** Sign out: revoke this user's tokens on the server (so a copied token stops
   *  working too), then clear local credentials. The revoke is best effort; the
   *  local sign-out happens even if the server cannot be reached. */
  const logout = useCallback(() => {
    // request() reads the token before its first await, so clearing it on the
    // next line does not strip the header from this call.
    api.post('/auth/logout').catch(() => {})
    clearLocalSession()
    setUser(null)
  }, [])

  /**
   * Merge partial updates into the current user state (client-side only).
   * @param {Object} updates - Fields to merge into the user object.
   */
  const updateUser = useCallback((updates) => {
    setUser(prev => ({ ...prev, ...updates }))
  }, [])

  // Memoize the context value so consumers don't re-render on every provider
  // render. Functions are stabilized with useCallback above; the value only
  // changes when user or loading change.
  const value = useMemo(() => ({
    user,
    loading,
    login,
    logout,
    updateUser,
    isAdmin: user?.role === 'admin',
    isSupervisor: user?.role === 'admin' || user?.role === 'supervisor',
    isPilot: user?.role === 'admin' || user?.role === 'supervisor' || user?.role === 'pilot',
    isManager: user?.role === 'admin' || user?.role === 'manager' || user?.role === 'supervisor' || user?.role === 'pilot',
    isViewer: user?.role === 'viewer',
  }), [user, loading, login, logout, updateUser])

  return (
    <AuthContext.Provider value={value}>
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
