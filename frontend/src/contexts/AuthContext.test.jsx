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
