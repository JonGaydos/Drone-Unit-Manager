import { describe, it, expect, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { Routes, Route } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import { Layout } from './Layout'

// Layout renders Sidebar (which fetches on mount) + TopBar + the routed
// Outlet. Mock every endpoint the chrome touches on mount.
beforeEach(() => {
  server.use(
    http.get('/api/settings', () => HttpResponse.json([])),
    http.get('/api/flights/count', () => HttpResponse.json({ count: 0 })),
    http.get('/api/flight-plans/pending/count', () => HttpResponse.json({ count: 0 })),
  )
})

describe('Layout', () => {
  it('renders the sidebar nav chrome and the routed child content', async () => {
    renderWithProviders(
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<div>Child page content</div>} />
        </Route>
      </Routes>,
      { role: 'admin' },
    )

    // Nav chrome: the sidebar exposes navigation links.
    expect(await screen.findByRole('link', { name: /Dashboard/ })).toBeInTheDocument()
    // Routed child rendered through the Outlet.
    expect(screen.getByText('Child page content')).toBeInTheDocument()
  })

  it('shows the page title from the route in the top bar', async () => {
    renderWithProviders(
      <Routes>
        <Route element={<Layout />}>
          <Route path="/pilots" element={<div>Pilots child</div>} />
        </Route>
      </Routes>,
      { route: '/pilots', role: 'admin' },
    )

    expect(await screen.findByRole('heading', { name: 'Pilots' })).toBeInTheDocument()
    expect(screen.getByText('Pilots child')).toBeInTheDocument()
  })
})
