import { describe, it, expect } from 'vitest'
import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import AlertsPage from './AlertsPage'

// Mount endpoints (Promise.all in load(), both .catch -> swallowed):
//   GET /alerts            (array; severity passed as ?severity= query string)
//   GET /alerts/count      ({ count } or number)
// Interactions: PATCH /alerts/:id/read, POST /alerts/dismiss-all.
const ALERTS = [
  { id: 1, title: 'Cert expiring', message: 'Part 107 expires soon', severity: 'warning', is_read: false, created_at: '2026-06-01' },
  { id: 2, title: 'Battery low', message: 'Cell A degraded', severity: 'critical', is_read: true, created_at: '2026-06-02' },
]

function mockMount(overrides = {}) {
  const base = {
    alerts: () => HttpResponse.json(ALERTS),
    count: () => HttpResponse.json({ count: 2 }),
    ...overrides,
  }
  server.use(
    http.get('/api/alerts', base.alerts),
    http.get('/api/alerts/count', base.count),
  )
}

describe('AlertsPage', () => {
  it('renders without crashing', async () => {
    mockMount()
    renderWithProviders(<AlertsPage />, { role: 'admin' })
    expect(await screen.findByText('Cert expiring')).toBeInTheDocument()
  })

  it('renders alert cards and the total count from a populated payload', async () => {
    mockMount()
    renderWithProviders(<AlertsPage />, { role: 'admin' })
    expect(await screen.findByText('Cert expiring')).toBeInTheDocument()
    expect(screen.getByText('Battery low')).toBeInTheDocument()
    expect(screen.getByText('2 total alerts')).toBeInTheDocument()
  })

  it('shows the empty state when there are no alerts', async () => {
    mockMount({ alerts: () => HttpResponse.json([]), count: () => HttpResponse.json({ count: 0 }) })
    renderWithProviders(<AlertsPage />, { role: 'admin' })
    expect(await screen.findByText('No alerts found')).toBeInTheDocument()
  })

  it('falls back to the empty UI when /alerts 500s', async () => {
    // load() .catch swallows the error; alerts stays [] so empty UI renders.
    mockMount({ alerts: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }) })
    renderWithProviders(<AlertsPage />, { role: 'admin' })
    expect(await screen.findByText('No alerts found')).toBeInTheDocument()
  })

  it('refetches with the severity query when the filter changes', async () => {
    let lastSeverity = null
    server.use(
      http.get('/api/alerts', ({ request }) => {
        lastSeverity = new URL(request.url).searchParams.get('severity')
        const filtered = lastSeverity ? ALERTS.filter(a => a.severity === lastSeverity) : ALERTS
        return HttpResponse.json(filtered)
      }),
      http.get('/api/alerts/count', () => HttpResponse.json({ count: 2 })),
    )
    const { user } = renderWithProviders(<AlertsPage />, { role: 'admin' })
    await screen.findByText('Cert expiring')

    await user.selectOptions(screen.getByRole('combobox'), 'critical')
    expect(await screen.findByText('Battery low')).toBeInTheDocument()
    expect(screen.queryByText('Cert expiring')).toBeNull()
    expect(lastSeverity).toBe('critical')
  })

  it('marks an alert read and fires PATCH /alerts/:id/read', async () => {
    let patchedId = null
    mockMount()
    server.use(
      http.patch('/api/alerts/:id/read', ({ params }) => {
        patchedId = params.id
        return HttpResponse.json({ ok: true })
      }),
    )
    const { user } = renderWithProviders(<AlertsPage />, { role: 'admin' })
    await screen.findByText('Cert expiring')

    // Only the unread alert (#1) shows the "Mark as read" control.
    await user.click(screen.getByRole('button', { name: 'Mark as read' }))
    await screen.findByText('Cert expiring')
    expect(patchedId).toBe('1')
  })

  it('dismisses all alerts via POST /alerts/dismiss-all after confirmation', async () => {
    let dismissAllCalled = false
    mockMount()
    server.use(
      http.post('/api/alerts/dismiss-all', () => {
        dismissAllCalled = true
        return HttpResponse.json({ ok: true })
      }),
    )
    const { user } = renderWithProviders(<AlertsPage />, { role: 'admin' })
    await screen.findByText('Cert expiring')

    await user.click(screen.getByRole('button', { name: /Dismiss All/ }))
    const dialog = await screen.findByRole('dialog')
    // ConfirmDialog uses the default confirm label here.
    await user.click(within(dialog).getByRole('button', { name: 'Confirm' }))

    await screen.findByText('Cert expiring')
    expect(dismissAllCalled).toBe(true)
  })
})
