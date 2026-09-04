import { describe, it, expect, afterEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { AuthProvider } from '@/contexts/AuthContext'
import { ThemeProvider } from '@/contexts/ThemeContext'
import { ToastProvider } from '@/contexts/ToastContext'
import { getDisplayTimezone, setDisplayTimezone } from '@/lib/utils'
import App from '@/App'

afterEach(() => setDisplayTimezone(null))

describe('timezone bootstrap', () => {
  it('sets the display timezone from the settings endpoint after login', async () => {
    localStorage.setItem('token', 'test-token')
    localStorage.setItem('user', JSON.stringify({ id: 1, username: 'admin', role: 'admin' }))
    server.use(
      http.get('/api/auth/setup-required', () => HttpResponse.json({ setup_required: false })),
      http.get('/api/auth/me', () => HttpResponse.json({ id: 1, username: 'admin', role: 'admin' })),
      http.get('/api/settings/display_timezone', () => HttpResponse.json({ key: 'display_timezone', value: 'America/Denver' })),
    )
    render(<App />)
    await waitFor(() => expect(getDisplayTimezone()).toBe('America/Denver'))
  })
})
