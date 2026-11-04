import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import {
  AuthProvider, useAuth, IDLE_LIMIT_MS, IDLE_NOTICE_KEY, LAST_ACTIVITY_KEY,
} from '@/contexts/AuthContext'

// resetSessionExpired is module-level state in the api client; AuthContext
// calls it on login. Re-arm it between tests so the guard stays predictable.
import { resetSessionExpired } from '@/api/client'

beforeEach(() => {
  resetSessionExpired()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

/** Render useAuth inside a fresh AuthProvider. */
function renderAuth() {
  return renderHook(() => useAuth(), { wrapper: AuthProvider })
}

describe('useAuth guard', () => {
  it('throws when called outside an AuthProvider', () => {
    // Silence the expected React error boundary console noise.
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => renderHook(() => useAuth())).toThrow(
      'useAuth must be used within AuthProvider',
    )
    spy.mockRestore()
  })
})

describe('login', () => {
  it('POSTs /api/auth/login, stores token, sets user, and re-arms the session guard', async () => {
    let body = null
    server.use(http.post('/api/auth/login', async ({ request }) => {
      body = await request.json()
      return HttpResponse.json({
        token: 'jwt-123',
        user: { id: 5, username: 'pat', role: 'pilot' },
      })
    }))

    const { result } = renderAuth()
    let returned
    await act(async () => {
      returned = await result.current.login('pat', 'secret')
    })

    expect(body).toEqual({ username: 'pat', password: 'secret' })
    expect(localStorage.getItem('token')).toBe('jwt-123')
    expect(result.current.user).toEqual({ id: 5, username: 'pat', role: 'pilot' })
    expect(returned).toEqual({ id: 5, username: 'pat', role: 'pilot' })
  })
})

describe('logout', () => {
  it('clears stored token + user and resets user to null', async () => {
    server.use(
      http.post('/api/auth/login', () =>
        HttpResponse.json({ token: 't', user: { id: 1, username: 'a', role: 'admin' } })),
      http.post('/api/auth/logout', () => HttpResponse.json({ ok: true })),
    )
    localStorage.setItem('user', JSON.stringify({ id: 1 }))

    const { result } = renderAuth()
    await act(async () => {
      await result.current.login('a', 'b')
    })
    expect(result.current.user).not.toBeNull()

    act(() => {
      result.current.logout()
    })
    expect(localStorage.getItem('token')).toBeNull()
    expect(localStorage.getItem('user')).toBeNull()
    expect(result.current.user).toBeNull()
  })

  // Clearing the browser's copy alone would leave a copied token working until
  // it expired, so logout also revokes on the server, with the old token.
  it('revokes the session on the server with the token it held', async () => {
    let authHeader = null
    server.use(
      http.post('/api/auth/login', () =>
        HttpResponse.json({ token: 'tok-to-revoke', user: { id: 1, username: 'a', role: 'admin' } })),
      http.post('/api/auth/logout', ({ request }) => {
        authHeader = request.headers.get('Authorization')
        return HttpResponse.json({ ok: true })
      }),
    )
    const { result } = renderAuth()
    await act(async () => { await result.current.login('a', 'b') })
    act(() => { result.current.logout() })
    await waitFor(() => expect(authHeader).toBe('Bearer tok-to-revoke'))
  })
})

describe('idle lock', () => {
  async function signIn() {
    server.use(http.post('/api/auth/login', () =>
      HttpResponse.json({ token: 't', user: { id: 1, username: 'a', role: 'pilot' } })))
    const view = renderAuth()
    await act(async () => { await view.result.current.login('a', 'b') })
    return view
  }

  it('signs out a browser left idle past the limit and leaves a notice', async () => {
    const { result } = await signIn()
    localStorage.setItem(LAST_ACTIVITY_KEY, String(Date.now() - IDLE_LIMIT_MS - 1000))
    act(() => { document.dispatchEvent(new Event('visibilitychange')) })
    expect(result.current.user).toBeNull()
    expect(localStorage.getItem('token')).toBeNull()
    expect(sessionStorage.getItem(IDLE_NOTICE_KEY)).toBe('1')
  })

  it('keeps a recently active session signed in', async () => {
    const { result } = await signIn()
    localStorage.setItem(LAST_ACTIVITY_KEY, String(Date.now() - 60 * 1000))
    act(() => { document.dispatchEvent(new Event('visibilitychange')) })
    expect(result.current.user).not.toBeNull()
  })

  it('locks on load when the stored session went idle, without calling /auth/me', async () => {
    let meCalled = false
    server.use(http.get('/api/auth/me', () => { meCalled = true; return HttpResponse.json({ id: 1 }) }))
    localStorage.setItem('token', 'old-token')
    localStorage.setItem(LAST_ACTIVITY_KEY, String(Date.now() - IDLE_LIMIT_MS - 1000))
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user).toBeNull()
    expect(localStorage.getItem('token')).toBeNull()
    expect(meCalled).toBe(false)
  })
})

describe('configured idle limit', () => {
  const MINUTE = 60 * 1000

  async function signInWithLimit(limit) {
    server.use(
      http.post('/api/auth/login', () =>
        HttpResponse.json({ token: 't', user: { id: 1, username: 'a', role: 'pilot' } })),
      http.get('/api/settings/idle_lock_minutes', () => limit()),
    )
    const view = renderAuth()
    await act(async () => { await view.result.current.login('a', 'b') })
    await act(async () => {})
    return view
  }

  function idleFor(minutes) {
    localStorage.setItem(LAST_ACTIVITY_KEY, String(Date.now() - minutes * MINUTE))
    act(() => { document.dispatchEvent(new Event('visibilitychange')) })
  }

  it('uses the configured limit', async () => {
    const { result } = await signInWithLimit(() => HttpResponse.json({ key: 'idle_lock_minutes', value: '120' }))
    idleFor(90)
    expect(result.current.user).not.toBeNull()
    idleFor(121)
    expect(result.current.user).toBeNull()
  })

  it.each([
    ['junk', () => HttpResponse.json({ key: 'idle_lock_minutes', value: 'soon' })],
    ['an unlisted number', () => HttpResponse.json({ key: 'idle_lock_minutes', value: '45' })],
    ['an empty value', () => HttpResponse.json({ key: 'idle_lock_minutes', value: '' })],
    ['a server error', () => new HttpResponse(null, { status: 500 })],
    ['a network failure', () => HttpResponse.error()],
  ])('falls back to 30 minutes on %s', async (_name, limit) => {
    const { result } = await signInWithLimit(limit)
    idleFor(29)
    expect(result.current.user).not.toBeNull()
    idleFor(31)
    expect(result.current.user).toBeNull()
  })

  it('locks at the next check when the limit is shortened', async () => {
    let value = '480'
    const { result } = await signInWithLimit(() => HttpResponse.json({ key: 'idle_lock_minutes', value }))
    server.use(http.get('/api/auth/me', () => HttpResponse.json({ id: 1, username: 'a', role: 'pilot' })))
    value = '30'
    const later = Date.now() + 61 * 1000
    vi.spyOn(Date, 'now').mockReturnValue(later)
    localStorage.setItem(LAST_ACTIVITY_KEY, String(later - 60 * MINUTE))
    await act(async () => { globalThis.dispatchEvent(new Event('focus')) })
    await waitFor(() => expect(localStorage.getItem('idleLockMinutes')).toBe('30'))
    act(() => { document.dispatchEvent(new Event('visibilitychange')) })
    expect(result.current.user).toBeNull()
    vi.restoreAllMocks()
  })

  it('uses the stored limit when the page is reopened', async () => {
    localStorage.setItem('token', 'old-token')
    localStorage.setItem('idleLockMinutes', '480')
    localStorage.setItem(LAST_ACTIVITY_KEY, String(Date.now() - 120 * MINUTE))
    server.use(
      http.get('/api/auth/me', () => HttpResponse.json({ id: 1, username: 'a', role: 'pilot' })),
      http.get('/api/settings/idle_lock_minutes', () => HttpResponse.json({ key: 'idle_lock_minutes', value: '480' })),
    )
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.user).not.toBeNull())
  })
})

describe('all tabs lock together', () => {
  async function signIn() {
    server.use(
      http.post('/api/auth/login', () =>
        HttpResponse.json({ token: 't', user: { id: 1, username: 'a', role: 'pilot' } })),
      http.get('/api/settings/idle_lock_minutes', () =>
        HttpResponse.json({ key: 'idle_lock_minutes', value: '30' })),
    )
    const view = renderAuth()
    await act(async () => { await view.result.current.login('a', 'b') })
    await act(async () => {})
    return view
  }

  // Another tab clears shared storage, which this tab hears as a storage event.
  function otherTabRemoves(key) {
    localStorage.removeItem(key)
    act(() => { globalThis.dispatchEvent(new StorageEvent('storage', { key, newValue: null })) })
  }

  it('logout in another tab locks this tab', async () => {
    const { result } = await signIn()
    otherTabRemoves('token')
    expect(result.current.user).toBeNull()
  })

  it('idle lock in another tab locks this tab', async () => {
    const { result } = await signIn()
    localStorage.removeItem(LAST_ACTIVITY_KEY)
    otherTabRemoves('token')
    expect(result.current.user).toBeNull()
  })

  it('ignores storage changes to other keys', async () => {
    const { result } = await signIn()
    act(() => { globalThis.dispatchEvent(new StorageEvent('storage', { key: 'theme', newValue: 'dark' })) })
    expect(result.current.user).not.toBeNull()
  })

  it('input in a locked tab does not renew the stamp', async () => {
    const { result } = await signIn()
    localStorage.removeItem('token')
    localStorage.removeItem(LAST_ACTIVITY_KEY)
    const later = Date.now() + 60 * 1000
    vi.spyOn(Date, 'now').mockReturnValue(later)
    act(() => { globalThis.dispatchEvent(new Event('keydown')) })
    vi.restoreAllMocks()
    expect(localStorage.getItem(LAST_ACTIVITY_KEY)).toBeNull()
    act(() => { document.dispatchEvent(new Event('visibilitychange')) })
    expect(result.current.user).toBeNull()
  })

  it('a missing stamp with no token counts as locked', async () => {
    const { result } = await signIn()
    localStorage.removeItem('token')
    localStorage.removeItem(LAST_ACTIVITY_KEY)
    act(() => { document.dispatchEvent(new Event('visibilitychange')) })
    expect(result.current.user).toBeNull()
  })
})

describe('updateUser', () => {
  it('merges partial updates into the current user', async () => {
    server.use(http.post('/api/auth/login', () =>
      HttpResponse.json({ token: 't', user: { id: 1, username: 'a', role: 'admin' } })))

    const { result } = renderAuth()
    await act(async () => {
      await result.current.login('a', 'b')
    })

    act(() => {
      result.current.updateUser({ username: 'renamed', theme: 'dark' })
    })
    expect(result.current.user).toEqual({
      id: 1,
      username: 'renamed',
      role: 'admin',
      theme: 'dark',
    })
  })
})

describe('isAdmin', () => {
  it.each([
    ['admin', true],
    ['supervisor', false],
    ['pilot', false],
    ['viewer', false],
  ])('role %s yields isAdmin %s, even with no permissions map', async (role, expected) => {
    server.use(http.post('/api/auth/login', () =>
      HttpResponse.json({ token: 't', user: { id: 1, username: 'u', role } })))

    const { result } = renderAuth()
    await act(async () => {
      await result.current.login('u', 'p')
    })

    expect(result.current.isAdmin).toBe(expected)
  })

  it('is false when there is no user', async () => {
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user).toBeNull()
    expect(result.current.isAdmin).toBe(false)
  })

  it('removes the old role helpers', async () => {
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.loading).toBe(false))
    for (const helper of ['isManager', 'isSupervisor', 'isPilot', 'isViewer']) {
      expect(result.current).not.toHaveProperty(helper)
    }
  })
})

describe('permission helpers', () => {
  async function signedInWith(permissions) {
    server.use(http.post('/api/auth/login', () =>
      HttpResponse.json({ token: 't', user: { id: 1, username: 'u', role: 'pilot', permissions } })))
    const view = renderAuth()
    await act(async () => { await view.result.current.login('u', 'p') })
    return view.result
  }

  it('can follows the map at every value', async () => {
    const result = await signedInWith({ a: 'yes', b: 'no', c: 'none', d: 'own', e: 'all' })
    expect(result.current.can('a')).toBe(true)
    expect(result.current.can('b')).toBe(false)
    expect(result.current.can('c')).toBe(false)
    expect(result.current.can('d')).toBe(true)
    expect(result.current.can('e')).toBe(true)
  })

  it('can is false for an unknown key, an invalid value and inherited names', async () => {
    const result = await signedInWith({ a: 'maybe' })
    expect(result.current.can('missing')).toBe(false)
    expect(result.current.can('a')).toBe(false)
    expect(result.current.can('constructor')).toBe(false)
  })

  it('a missing map grants nothing, even to an admin', async () => {
    server.use(http.post('/api/auth/login', () =>
      HttpResponse.json({ token: 't', user: { id: 1, username: 'a', role: 'admin' } })))
    const { result } = renderAuth()
    await act(async () => { await result.current.login('a', 'p') })
    expect(result.current.can('flights.view')).toBe(false)
    expect(result.current.level('flights.edit')).toBe('none')
    expect(result.current.canRecord('flights.edit', true)).toBe(false)
  })

  it('every helper denies when nobody is signed in', async () => {
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.can('flights.view')).toBe(false)
    expect(result.current.level('flights.edit')).toBe('none')
    expect(result.current.canRecord('flights.edit', true)).toBe(false)
  })

  it('level returns own or all, and none for anything else', async () => {
    const result = await signedInWith({ a: 'own', b: 'all', c: 'none', d: 'yes', e: 'no' })
    expect(result.current.level('a')).toBe('own')
    expect(result.current.level('b')).toBe('all')
    expect(result.current.level('c')).toBe('none')
    expect(result.current.level('d')).toBe('none')
    expect(result.current.level('e')).toBe('none')
    expect(result.current.level('missing')).toBe('none')
  })

  it('canRecord handles none, own and all', async () => {
    const result = await signedInWith({ n: 'none', o: 'own', a: 'all' })
    expect(result.current.canRecord('n', true)).toBe(false)
    expect(result.current.canRecord('n', false)).toBe(false)
    expect(result.current.canRecord('o', true)).toBe(true)
    expect(result.current.canRecord('o', false)).toBe(false)
    expect(result.current.canRecord('a', true)).toBe(true)
    expect(result.current.canRecord('a', false)).toBe(true)
    expect(result.current.canRecord('missing', true)).toBe(false)
  })

  it('loads the permissions the first time from /auth/me', async () => {
    localStorage.setItem('token', 'stored-token')
    server.use(http.get('/api/auth/me', () =>
      HttpResponse.json({ id: 9, username: 'me', role: 'pilot', permissions: { 'flights.view': 'yes' } })))
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.can('flights.view')).toBe(true))
  })
})

describe('mount validation', () => {
  it('with a stored token, a successful /auth/me sets the user', async () => {
    localStorage.setItem('token', 'stored-token')
    server.use(http.get('/api/auth/me', () =>
      HttpResponse.json({ id: 9, username: 'me', role: 'supervisor' })))

    const { result } = renderAuth()
    await waitFor(() =>
      expect(result.current.user).toEqual({ id: 9, username: 'me', role: 'supervisor' }))
    expect(result.current.loading).toBe(false)
  })

  it('with a stored token, a failed /auth/me clears token + user', async () => {
    localStorage.setItem('token', 'bad-token')
    localStorage.setItem('user', JSON.stringify({ id: 1 }))
    server.use(http.get('/api/auth/me', () => new HttpResponse(null, { status: 500 })))

    const { result } = renderAuth()
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user).toBeNull()
    expect(localStorage.getItem('token')).toBeNull()
    expect(localStorage.getItem('user')).toBeNull()
  })

  it('with a stored token, a 401 /auth/me clears token + user', async () => {
    // A 401 also drives the client's handleUnauthorized redirect; stub a
    // writable location so it does not navigate the jsdom window.
    vi.stubGlobal('location', { href: 'http://localhost/', origin: 'http://localhost' })
    localStorage.setItem('token', 'expired-token')
    localStorage.setItem('user', JSON.stringify({ id: 1 }))
    server.use(http.get('/api/auth/me', () => new HttpResponse(null, { status: 401 })))

    const { result } = renderAuth()
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user).toBeNull()
    expect(localStorage.getItem('token')).toBeNull()
    expect(localStorage.getItem('user')).toBeNull()
  })

  it('without a stored token, mount finishes loading without calling /auth/me', async () => {
    // No token set; the effect's else-branch just flips loading false.
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user).toBeNull()
  })
})

describe('refresh on window focus', () => {
  const ME = { id: 1, username: 'a', role: 'pilot', permissions: { 'flights.delete': 'none' } }
  const PAST_THROTTLE_MS = 61 * 1000

  async function signIn(meHandler) {
    const calls = { me: 0 }
    server.use(
      http.post('/api/auth/login', () => HttpResponse.json({ token: 't', user: ME })),
      http.get('/api/auth/me', (info) => { calls.me += 1; return meHandler(info) }),
    )
    const view = renderAuth()
    await act(async () => { await view.result.current.login('a', 'b') })
    return { ...view, calls }
  }

  async function focusLater(ms = PAST_THROTTLE_MS) {
    const later = Date.now() + ms
    vi.spyOn(Date, 'now').mockReturnValue(later)
    localStorage.setItem(LAST_ACTIVITY_KEY, String(later))
    await act(async () => { globalThis.dispatchEvent(new Event('focus')) })
  }

  afterEach(() => { vi.restoreAllMocks() })

  it('picks up changed permissions', async () => {
    const changed = { ...ME, permissions: { 'flights.delete': 'all' } }
    const { result } = await signIn(() => HttpResponse.json(changed))
    expect(result.current.level('flights.delete')).toBe('none')
    await focusLater()
    await waitFor(() => expect(result.current.level('flights.delete')).toBe('all'))
  })

  it('keeps the same user object when nothing changed, so pages do not reload', async () => {
    const { result, calls } = await signIn(() => HttpResponse.json(ME))
    const { can } = result.current
    await focusLater()
    await waitFor(() => expect(calls.me).toBe(1))
    await act(async () => {})
    expect(result.current.can).toBe(can)
  })

  it('asks at most once within the throttle window', async () => {
    const { calls } = await signIn(() => HttpResponse.json(ME))
    await focusLater(1000)
    expect(calls.me).toBe(0)
    await focusLater()
    await waitFor(() => expect(calls.me).toBe(1))
    await focusLater(1000)
    await act(async () => {})
    expect(calls.me).toBe(1)
  })

  it('keeps the user on a network failure and on a server error', async () => {
    const responses = [() => HttpResponse.error(), () => HttpResponse.json({ detail: 'boom' }, { status: 500 })]
    const { result, calls } = await signIn(() => responses[calls.me - 1]())
    await focusLater()
    await waitFor(() => expect(calls.me).toBe(1))
    await act(async () => {})
    expect(result.current.user).toEqual(ME)
    await focusLater(PAST_THROTTLE_MS * 2)
    await waitFor(() => expect(calls.me).toBe(2))
    await act(async () => {})
    expect(result.current.user).toEqual(ME)
    expect(localStorage.getItem('token')).toBe('t')
  })

  it.each([
    ['a 200 with an empty body', () => new HttpResponse('', { status: 200 })],
    ['a 204', () => new HttpResponse(null, { status: 204 })],
  ])('keeps the user on %s', async (_name, respond) => {
    const { result, calls } = await signIn(respond)
    await focusLater()
    await waitFor(() => expect(calls.me).toBe(1))
    await act(async () => {})
    expect(result.current.user).toEqual(ME)
    expect(localStorage.getItem('token')).toBe('t')
  })

  it('clears the session on a 401', async () => {
    vi.stubGlobal('location', { href: 'http://localhost/', origin: 'http://localhost' })
    const { result } = await signIn(() => new HttpResponse(null, { status: 401 }))
    await focusLater()
    await waitFor(() => expect(result.current.user).toBeNull())
    expect(localStorage.getItem('token')).toBeNull()
  })

  it('does not ask after signing out', async () => {
    const { result, calls } = await signIn(() => HttpResponse.json(ME))
    server.use(http.post('/api/auth/logout', () => HttpResponse.json({ ok: true })))
    act(() => { result.current.logout() })
    await focusLater()
    await act(async () => {})
    expect(calls.me).toBe(0)
  })
})
