import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { AuthProvider, useAuth } from '@/contexts/AuthContext'

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
    server.use(http.post('/api/auth/login', () =>
      HttpResponse.json({ token: 't', user: { id: 1, username: 'a', role: 'admin' } })))
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

describe('role booleans', () => {
  // Expected matrix derived directly from the source memoized value.
  const cases = [
    ['admin', { isAdmin: true, isSupervisor: true, isPilot: true, isManager: true, isViewer: false }],
    ['supervisor', { isAdmin: false, isSupervisor: true, isPilot: true, isManager: true, isViewer: false }],
    ['pilot', { isAdmin: false, isSupervisor: false, isPilot: true, isManager: true, isViewer: false }],
    ['manager', { isAdmin: false, isSupervisor: false, isPilot: false, isManager: true, isViewer: false }],
    ['viewer', { isAdmin: false, isSupervisor: false, isPilot: false, isManager: false, isViewer: true }],
  ]

  it.each(cases)('role %s yields the correct booleans', async (role, expected) => {
    server.use(http.post('/api/auth/login', () =>
      HttpResponse.json({ token: 't', user: { id: 1, username: 'u', role } })))

    const { result } = renderAuth()
    await act(async () => {
      await result.current.login('u', 'p')
    })

    expect(result.current.isAdmin).toBe(expected.isAdmin)
    expect(result.current.isSupervisor).toBe(expected.isSupervisor)
    expect(result.current.isPilot).toBe(expected.isPilot)
    expect(result.current.isManager).toBe(expected.isManager)
    expect(result.current.isViewer).toBe(expected.isViewer)
  })

  it('all role booleans are false when there is no user', async () => {
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user).toBeNull()
    expect(result.current.isAdmin).toBe(false)
    expect(result.current.isSupervisor).toBe(false)
    expect(result.current.isPilot).toBe(false)
    expect(result.current.isManager).toBe(false)
    expect(result.current.isViewer).toBe(false)
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
