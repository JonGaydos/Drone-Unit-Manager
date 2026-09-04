import { describe, it, expect, afterEach, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import LoginPage from './LoginPage'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('LoginPage', () => {
  it('renders the sign-in form without crashing', () => {
    renderWithProviders(<LoginPage />, { route: '/login' })
    expect(screen.getByRole('heading', { name: 'Drone Unit Manager' })).toBeInTheDocument()
    expect(screen.getByLabelText('Username')).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sign In' })).toBeInTheDocument()
  })

  it('submits credentials, stores the token on success', async () => {
    let body = null
    server.use(http.post('/api/auth/login', async ({ request }) => {
      body = await request.json()
      return HttpResponse.json({
        token: 'jwt-success',
        user: { id: 1, username: 'admin', role: 'admin' },
      })
    }))

    const { user } = renderWithProviders(<LoginPage />, { route: '/login' })
    await user.type(screen.getByLabelText('Username'), 'admin')
    await user.type(screen.getByLabelText('Password'), 'hunter2pass')
    await user.click(screen.getByRole('button', { name: 'Sign In' }))

    await waitFor(() => expect(localStorage.getItem('token')).toBe('jwt-success'))
    expect(body).toEqual({ username: 'admin', password: 'hunter2pass' })
  })

  it('shows an inline error on bad credentials and does not store a token', async () => {
    server.use(http.post('/api/auth/login', () =>
      HttpResponse.json({ detail: 'Invalid username or password' }, { status: 401 })))

    // A login 401 is exempt from the global handleUnauthorized redirect; stub a
    // writable location so the assertion can confirm we did NOT navigate away.
    vi.stubGlobal('location', { href: 'http://localhost/login', origin: 'http://localhost' })

    const { user } = renderWithProviders(<LoginPage />, { route: '/login' })
    await user.type(screen.getByLabelText('Username'), 'admin')
    await user.type(screen.getByLabelText('Password'), 'wrongpass')
    await user.click(screen.getByRole('button', { name: 'Sign In' }))

    // The real backend detail surfaces inline (not "Session expired"), and the
    // form is still shown (no redirect).
    expect(await screen.findByText('Invalid username or password')).toBeInTheDocument()
    expect(localStorage.getItem('token')).toBeNull()
    expect(screen.getByRole('button', { name: 'Sign In' })).toBeInTheDocument()
  })
})
