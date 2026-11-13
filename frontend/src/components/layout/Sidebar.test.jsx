import { describe, it, expect, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { withPermissions } from '@/test/permissions'
import { renderWithProviders } from '@/test/render'
import { Sidebar } from './Sidebar'

// The Sidebar reads its role from the authenticated user, which AuthProvider
// loads from GET /api/auth/me on mount — so role gating is driven by that
// handler, not by the localStorage seed alone.
function authAs(role, permissions) {
  server.use(http.get('/api/auth/me', () =>
    HttpResponse.json(withPermissions({ id: 1, username: role, display_name: `User ${role}`, role }, permissions))))
}

beforeEach(() => {
  server.use(
    http.get('/api/settings', () => HttpResponse.json([])),
    http.get('/api/flights/count', () => HttpResponse.json({ count: 0 })),
    http.get('/api/flight-plans/pending/count', () => HttpResponse.json({ count: 0 })),
  )
})

describe('Sidebar role gating', () => {
  it('shows the admin-only Audit Log link for an admin', async () => {
    authAs('admin')
    renderWithProviders(<Sidebar mobileOpen={false} onMobileClose={() => {}} />, { role: 'admin' })

    // Wait for auth to resolve so the role-gated render settles.
    await screen.findByRole('link', { name: /Dashboard/ })
    expect(screen.getByRole('link', { name: /Audit Log/ })).toBeInTheDocument()
  })

  it('hides the admin-only Audit Log link from a pilot', async () => {
    authAs('pilot')
    renderWithProviders(<Sidebar mobileOpen={false} onMobileClose={() => {}} />, { role: 'pilot' })

    await screen.findByRole('link', { name: /Dashboard/ })
    // Confirm auth resolved to pilot (role label rendered in the user block).
    expect(await screen.findByText('pilot')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Audit Log/ })).not.toBeInTheDocument()
  })

  it('hides the admin-only Audit Log link from a viewer', async () => {
    authAs('viewer')
    renderWithProviders(<Sidebar mobileOpen={false} onMobileClose={() => {}} />, { role: 'viewer' })

    await screen.findByRole('link', { name: /Dashboard/ })
    expect(await screen.findByText('viewer')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Audit Log/ })).not.toBeInTheDocument()
  })
})

describe('Sidebar view permissions', () => {
  it('hides an entry with its view off and keeps the others', async () => {
    authAs('pilot', { 'pilots.view': 'no' })
    renderWithProviders(<Sidebar mobileOpen={false} onMobileClose={() => {}} />, { role: 'pilot' })

    await screen.findByText('pilot')
    expect(screen.queryByRole('link', { name: /Pilots/ })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /^Fleet$/ })).toBeInTheDocument()
  })

  it('shows the Audit Log to a role granted audit.view', async () => {
    authAs('supervisor', { 'audit.view': 'yes' })
    renderWithProviders(<Sidebar mobileOpen={false} onMobileClose={() => {}} />, { role: 'supervisor' })

    expect(await screen.findByRole('link', { name: /Audit Log/ })).toBeInTheDocument()
  })

  it('does not ask for the review count with flights.view off', async () => {
    let asked = false
    authAs('pilot', { 'flights.view': 'no' })
    server.use(http.get('/api/flights/count', () => { asked = true; return HttpResponse.json({ count: 3 }) }))
    renderWithProviders(<Sidebar mobileOpen={false} onMobileClose={() => {}} />, { role: 'pilot' })

    await screen.findByText('pilot')
    expect(asked).toBe(false)
  })
})

describe('Sidebar Fleet Health link', () => {
  it('lists Fleet Health right after Fleet for a role that can view the fleet', async () => {
    authAs('pilot')
    renderWithProviders(<Sidebar mobileOpen={false} onMobileClose={() => {}} />, { role: 'pilot' })

    await screen.findByRole('link', { name: /^Fleet$/ })
    const names = screen.getAllByRole('link').map(l => l.textContent)
    expect(names.indexOf('Fleet Health')).toBe(names.indexOf('Fleet') + 1)
    expect(screen.getByRole('link', { name: /Fleet Health/ })).toHaveAttribute('href', '/fleet-health')
  })

  it('hides Fleet Health from a role without fleet.view', async () => {
    authAs('pilot', { 'fleet.view': 'no' })
    renderWithProviders(<Sidebar mobileOpen={false} onMobileClose={() => {}} />, { role: 'pilot' })

    await screen.findByText('pilot')
    expect(screen.queryByRole('link', { name: /Fleet Health/ })).not.toBeInTheDocument()
  })

  it('still shows Fleet Health when a saved sidebar config predates it', async () => {
    authAs('admin')
    server.use(http.get('/api/settings', () => HttpResponse.json([
      { key: 'sidebar_config', value: JSON.stringify([
        { to: '/', visible: true, order: 0 },
        { to: '/fleet', visible: true, order: 1 },
        { to: '/pilots', visible: true, order: 2 },
      ]) },
    ])))
    renderWithProviders(<Sidebar mobileOpen={false} onMobileClose={() => {}} />, { role: 'admin' })

    expect(await screen.findByRole('link', { name: /Fleet Health/ })).toBeInTheDocument()
  })
})

describe('Sidebar active route', () => {
  it('marks the link for the current route active', async () => {
    authAs('admin')
    renderWithProviders(<Sidebar mobileOpen={false} onMobileClose={() => {}} />, { route: '/pilots', role: 'admin' })

    const pilots = await screen.findByRole('link', { name: /Pilots/ })
    // NavLink applies the active classes when its route matches.
    expect(pilots.className).toMatch(/border-primary/)
    expect(pilots).toHaveClass('text-primary')

    // A non-active link does not carry the active treatment.
    const dashboard = screen.getByRole('link', { name: /Dashboard/ })
    expect(dashboard).not.toHaveClass('text-primary')
  })
})

describe('Sidebar logout', () => {
  it('logs the user out when the log-out button is clicked', async () => {
    authAs('admin')
    const { user } = renderWithProviders(
      <Sidebar mobileOpen={false} onMobileClose={() => {}} />, { role: 'admin' })

    await screen.findByRole('link', { name: /Dashboard/ })
    expect(localStorage.getItem('token')).toBe('test-token')

    await user.click(screen.getByRole('button', { name: 'Log out' }))
    // logout() clears the stored credentials.
    expect(localStorage.getItem('token')).toBeNull()
    expect(localStorage.getItem('user')).toBeNull()
  })
})
