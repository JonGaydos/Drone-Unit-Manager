/**
 * Authentication context providing user state, login/logout, and permission checks.
 * Persists auth token in localStorage and validates on mount via /auth/me.
 */
import { createContext, useContext, useState, useEffect, useMemo, useCallback } from 'react'
import { api, resetSessionExpired } from '@/api/client'
import { IDLE_LOCK_MINUTES } from '@/lib/idleLock'

const AuthContext = createContext(null)

// The server token lives 12 hours whatever limit is chosen; the lock covers a
// screen left unattended.
const DEFAULT_IDLE_MINUTES = 30
/** The limit used when none has been read, or the read failed. */
export const IDLE_LIMIT_MS = DEFAULT_IDLE_MINUTES * 60 * 1000
// Last limit read from the server, kept so a reopened page applies it before
// any request. Shared across tabs like the activity stamp.
const IDLE_MINUTES_KEY = 'idleLockMinutes'
const IDLE_CHECK_MS = 60 * 1000
// Activity is stamped at most this often, so a moving mouse is not a stream of
// localStorage writes.
const ACTIVITY_WRITE_MS = 15 * 1000
// Shared through localStorage so activity in any open tab keeps every tab alive.
export const LAST_ACTIVITY_KEY = 'lastActivity'
/** Set when the idle lock signs someone out, so the login page can say why. */
export const IDLE_NOTICE_KEY = 'signedOutIdle'
/** Shared across tabs: the last sign-out was the idle lock, so every tab shows
 *  the notice, not only the one that locked. Cleared by a sign-in or a logout. */
export const IDLE_LOCKED_KEY = 'idleLocked'
const ACTIVITY_EVENTS = ['pointerdown', 'keydown', 'touchstart', 'wheel', 'scroll']
// Values of a permission that hold it at any level above the lowest.
const GRANTED = new Set(['yes', 'own', 'all'])
const LEVELS = new Set(['own', 'all'])
// Permissions can change while someone is signed in, so they are fetched again
// when the window regains focus, at most this often.
const USER_REFRESH_MS = 60 * 1000

/** A listed number of minutes, or the default for anything else. */
function parseIdleMinutes(value) {
  const text = String(value ?? '')
  const minutes = /^\d+$/.test(text) ? Number(text) : 0
  return IDLE_LOCK_MINUTES.includes(minutes) ? minutes : DEFAULT_IDLE_MINUTES
}

function idleLimitMs() {
  return parseIdleMinutes(localStorage.getItem(IDLE_MINUTES_KEY)) * 60 * 1000
}

/** Read the limit from the server and keep it. Never throws, and any failure or
 *  unusable value means the default, so there is no state without a lock. */
function loadIdleLimit() {
  return api.get('/settings/idle_lock_minutes')
    .then(row => parseIdleMinutes(row?.value))
    .catch(() => DEFAULT_IDLE_MINUTES)
    .then(minutes => { localStorage.setItem(IDLE_MINUTES_KEY, String(minutes)) })
}

// Once another tab signs out or locks, the token is gone and input here must
// not stamp activity, or it would revive the session for the other tabs.
function markActivity() {
  if (!localStorage.getItem('token')) return
  localStorage.setItem(LAST_ACTIVITY_KEY, String(Date.now()))
}

function idleExpired() {
  const last = Number(localStorage.getItem(LAST_ACTIVITY_KEY))
  return last > 0 && Date.now() - last > idleLimitMs()
}

function clearLocalSession() {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  localStorage.removeItem(LAST_ACTIVITY_KEY)
}

// Written before the token is removed, so the other tabs read it when they
// hear the removal.
function lockForInactivity() {
  sessionStorage.setItem(IDLE_NOTICE_KEY, '1')
  localStorage.setItem(IDLE_LOCKED_KEY, '1')
  clearLocalSession()
}

/** Keep the same object when nothing changed, so a focus does not reload pages
 *  whose effects depend on the permission checks. */
const replaceIfChanged = (next) => (current) => (
  JSON.stringify(current) === JSON.stringify(next) ? current : next
)

/** Fetch the signed-in user again. A failed or empty answer keeps the current
 *  user unless the session itself has ended. An answer is dropped once the
 *  stored token has changed, so an older reload cannot overwrite a newer one. */
function reloadUser(isActive, setUser) {
  const token = localStorage.getItem('token')
  return api.get('/auth/me')
    .then(next => {
      if (isActive() && localStorage.getItem('token') === token && next?.id) setUser(replaceIfChanged(next))
    })
    .catch(err => {
      // The api client drops the token on a 401 itself, so a missing one still counts.
      const stored = localStorage.getItem('token') ?? token
      if (isActive() && stored === token && err.status === 401) {
        clearLocalSession()
        setUser(null)
      }
    })
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
      lockForInactivity()
      setLoading(false)
    } else if (token) {
      api.get('/auth/me')
        .then(me => { setUser(me); loadIdleLimit() })
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
    let active = true
    // The token this tab signed in with. Another one means a sign-in elsewhere,
    // possibly as someone else, that this tab may have missed.
    let knownToken = localStorage.getItem('token')
    let lastWrite = Date.now()
    const onActivity = () => {
      const now = Date.now()
      if (now - lastWrite > ACTIVITY_WRITE_MS) {
        lastWrite = now
        markActivity()
      }
    }
    const check = () => {
      const token = localStorage.getItem('token')
      if (!token) {
        // Signed out or locked in another tab, whose storage event may not have arrived.
        if (localStorage.getItem(IDLE_LOCKED_KEY)) sessionStorage.setItem(IDLE_NOTICE_KEY, '1')
        setUser(null)
      } else if (idleExpired()) {
        lockForInactivity()
        setUser(null)
      } else if (token !== knownToken) {
        knownToken = token
        reloadUser(() => active, setUser)
      }
    }
    ACTIVITY_EVENTS.forEach(e => globalThis.addEventListener(e, onActivity, { passive: true }))
    // Another tab signing out or locking removes the shared token, and signing
    // in replaces it.
    const onStorage = (e) => {
      if (e.key === 'token' || e.key === null) check()
    }
    globalThis.addEventListener('storage', onStorage)
    document.addEventListener('visibilitychange', check)
    const timer = setInterval(check, IDLE_CHECK_MS)
    return () => {
      active = false
      ACTIVITY_EVENTS.forEach(e => globalThis.removeEventListener(e, onActivity))
      globalThis.removeEventListener('storage', onStorage)
      document.removeEventListener('visibilitychange', check)
      clearInterval(timer)
    }
  }, [signedIn])

  useEffect(() => {
    if (!signedIn) return undefined
    let active = true
    let lastRefresh = Date.now()
    const refresh = () => {
      const now = Date.now()
      if (now - lastRefresh < USER_REFRESH_MS || idleExpired()) return
      lastRefresh = now
      loadIdleLimit()
      reloadUser(() => active, setUser)
    }
    globalThis.addEventListener('focus', refresh)
    return () => {
      active = false
      globalThis.removeEventListener('focus', refresh)
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
    localStorage.removeItem(IDLE_LOCKED_KEY)
    // Re-arm the once-per-session 401 logout guard so a later expiry redirects.
    resetSessionExpired()
    setUser(data.user)
    loadIdleLimit()
    return data.user
  }, [])

  /** Sign out: revoke this user's tokens on the server (so a copied token stops
   *  working too), then clear local credentials. The revoke is best effort; the
   *  local sign-out happens even if the server cannot be reached. */
  const logout = useCallback(() => {
    // request() reads the token before its first await, so clearing it on the
    // next line does not strip the header from this call.
    api.post('/auth/logout').catch(() => {})
    localStorage.removeItem(IDLE_LOCKED_KEY)
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

  // The checks fail closed: no user, no map or an unknown key denies. The map
  // comes from the server on login and /auth/me.
  const permissions = user?.permissions
  const can = useCallback((key) => GRANTED.has(permissions?.[key]), [permissions])
  const level = useCallback((key) => {
    const value = permissions?.[key]
    return LEVELS.has(value) ? value : 'none'
  }, [permissions])
  const canRecord = useCallback((key, owned) => {
    const held = level(key)
    return held === 'all' || (held === 'own' && owned === true)
  }, [level])

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
    can,
    level,
    canRecord,
  }), [user, loading, login, logout, updateUser, can, level, canRecord])

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}

/**
 * Hook to access authentication context values.
 * Must be used within an AuthProvider.
 * @returns {{ user: Object|null, loading: boolean, login: Function, logout: Function, updateUser: Function, isAdmin: boolean, can: (key: string) => boolean, level: (key: string) => 'none'|'own'|'all', canRecord: (key: string, owned: boolean) => boolean }}
 */
export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
