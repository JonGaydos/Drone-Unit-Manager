import { describe, it, expect, afterEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { withPermissions } from '@/test/permissions'
import App from '@/App'

afterEach(() => {
  localStorage.clear()
  window.history.pushState({}, '', '/')
})

describe('App routes', () => {
  it.each(['/currency', '/currency/anything'])('sends %s to the Flight Requirements tab', async (path) => {
    localStorage.setItem('token', 'test-token')
    localStorage.setItem('user', JSON.stringify({ id: 1, username: 'admin', role: 'admin' }))
    server.use(
      http.get('/api/auth/setup-required', () => HttpResponse.json({ setup_required: false })),
      http.get('/api/auth/me', () => HttpResponse.json(withPermissions({ id: 1, username: 'admin', role: 'admin' }))),
    )
    window.history.pushState({}, '', path)
    render(<App />)
    await waitFor(() => expect(window.location.pathname + window.location.search).toBe('/compliance?tab=requirements'))
  })
})
