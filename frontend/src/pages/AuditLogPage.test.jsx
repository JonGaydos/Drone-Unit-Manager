import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import AuditLogPage from './AuditLogPage'

// Mount endpoint (admin only): GET /audit?page=&per_page=&[entity_type]&[action].
// The page reads data.logs and data.total. Non-admins short-circuit before any
// fetch, so the access-required guard renders with no network call.
const POPULATED = {
  total: 2,
  logs: [
    {
      id: 1, created_at: '2026-06-10T12:00:00Z', user_name: 'admin',
      action: 'create', entity_type: 'flight', entity_id: 101, entity_name: 'FLT-101',
      details: 'Created flight', changes: { status: { old: 'draft', new: 'final' } },
    },
    {
      id: 2, created_at: '2026-06-09T09:30:00Z', user_name: 'admin',
      action: 'login', entity_type: 'auth', entity_id: null, entity_name: null,
      details: 'User logged in', changes: null,
    },
  ],
}

describe('AuditLogPage', () => {
  it('renders without crashing for an admin', async () => {
    server.use(http.get('/api/audit', () => HttpResponse.json({ total: 0, logs: [] })))
    renderWithProviders(<AuditLogPage />, { role: 'admin' })
    expect(await screen.findByRole('heading', { name: 'Activity Audit Log' })).toBeInTheDocument()
  })

  it('renders log rows from a populated payload', async () => {
    server.use(http.get('/api/audit', () => HttpResponse.json(POPULATED)))
    renderWithProviders(<AuditLogPage />, { role: 'admin' })

    expect(await screen.findByText('FLT-101')).toBeInTheDocument()
    expect(screen.getByText('Created flight')).toBeInTheDocument()
    expect(screen.getByText('2 total entries')).toBeInTheDocument()
    expect(screen.getByText('create')).toBeInTheDocument()
    expect(screen.getByText('login')).toBeInTheDocument()
  })

  it('shows the empty state when there are no log entries', async () => {
    server.use(http.get('/api/audit', () => HttpResponse.json({ total: 0, logs: [] })))
    renderWithProviders(<AuditLogPage />, { role: 'admin' })

    expect(await screen.findByText('No audit log entries found.')).toBeInTheDocument()
  })

  it('shows the empty state (no rows) when the audit endpoint 500s', async () => {
    server.use(http.get('/api/audit', () => HttpResponse.json({ detail: 'boom' }, { status: 500 })))
    renderWithProviders(<AuditLogPage />, { role: 'admin' })

    // The page swallows the error; logs stays [] so the empty UI appears, not a crash.
    expect(await screen.findByText('No audit log entries found.')).toBeInTheDocument()
  })

  it('shows the access-required guard for a non-admin user', async () => {
    // Override /auth/me so the resolved role is viewer, not the default admin.
    server.use(http.get('/api/auth/me', () =>
      HttpResponse.json({ id: 2, username: 'view', role: 'viewer' })))
    renderWithProviders(<AuditLogPage />, { role: 'viewer' })

    expect(await screen.findByText('Admin access required to view audit logs.')).toBeInTheDocument()
  })

  it('expands a row to reveal field-level changes', async () => {
    server.use(http.get('/api/audit', () => HttpResponse.json(POPULATED)))
    const { user } = renderWithProviders(<AuditLogPage />, { role: 'admin' })

    await screen.findByText('FLT-101')
    await user.click(screen.getByTitle('View changes'))
    expect(await screen.findByText('Changes:')).toBeInTheDocument()
    expect(screen.getByText('status:')).toBeInTheDocument()
  })

  // The detail row used to be built by a second pass over the whole list after
  // the main rows, so it rendered at the bottom of the table rather than under
  // the row that was clicked. On a full page of 50 entries the changes appeared
  // off screen and the chevron looked like it did nothing.
  it('puts the expanded changes directly under the row they belong to', async () => {
    server.use(http.get('/api/audit', () => HttpResponse.json(POPULATED)))
    const { user } = renderWithProviders(<AuditLogPage />, { role: 'admin' })

    await screen.findByText('FLT-101')
    await user.click(screen.getByTitle('View changes'))

    const changesCell = (await screen.findByText('Changes:')).closest('tr')
    const clickedRow = screen.getByTitle('View changes').closest('tr')

    expect(changesCell).toBe(clickedRow.nextElementSibling)
  })

  // The details column is fixed width, so anything longer than it reads as
  // "checked out sensor #1 to Kristina Carro...". The row has no changes to
  // show, so before this it had no expander either and the rest of the sentence
  // was unreachable.
  describe('truncated details', () => {
    const withDetails = (details) => ({
      total: 1,
      logs: [{
        id: 9, created_at: '2026-06-10T12:00:00Z', user_name: 'admin',
        action: 'checkout', entity_type: 'equipment', entity_id: 1,
        entity_name: 'sensor #1', details, changes: null,
      }],
    })

    const LONG = 'checked out sensor #1 to Kristina Carroll until 2026-06-20'

    it('offers an expander on a row whose details are cut off', async () => {
      server.use(http.get('/api/audit', () => HttpResponse.json(withDetails(LONG))))
      const { user } = renderWithProviders(<AuditLogPage />, { role: 'admin' })

      await screen.findByText('sensor #1')
      await user.click(screen.getByTitle('View full details'))

      // The full sentence, in a row of its own directly beneath.
      const full = await screen.findByText(LONG, { selector: 'p' })
      expect(full.closest('tr')).toBe(screen.getByTitle('View full details').closest('tr').nextElementSibling)
    })

    it('leaves short details alone', async () => {
      server.use(http.get('/api/audit', () => HttpResponse.json(withDetails('Successful login'))))
      renderWithProviders(<AuditLogPage />, { role: 'admin' })

      await screen.findByText('sensor #1')
      expect(screen.queryByTitle('View full details')).toBeNull()
      expect(screen.queryByTitle('View changes')).toBeNull()
    })

    it('still says "View changes" when there are changes to see', async () => {
      server.use(http.get('/api/audit', () => HttpResponse.json(POPULATED)))
      renderWithProviders(<AuditLogPage />, { role: 'admin' })

      await screen.findByText('FLT-101')
      expect(screen.getByTitle('View changes')).toBeInTheDocument()
    })

    it('shows the full details and the changes together when a row has both', async () => {
      server.use(http.get('/api/audit', () => HttpResponse.json({
        total: 1,
        logs: [{
          id: 7, created_at: '2026-06-10T12:00:00Z', user_name: 'admin',
          action: 'bulk_update', entity_type: 'flight', entity_id: null,
          entity_name: null, details: 'Updated 4 flights (ids 1389, 1391-1393)',
          changes: { purpose: { old: 'Search Warrant (4)', new: 'Other Agency Assist' } },
        }],
      })))
      const { user } = renderWithProviders(<AuditLogPage />, { role: 'admin' })

      await screen.findByText('bulk update')
      await user.click(screen.getByTitle('View changes'))

      expect(await screen.findByText('Updated 4 flights (ids 1389, 1391-1393)', { selector: 'p' })).toBeInTheDocument()
      expect(screen.getByText('purpose:')).toBeInTheDocument()
      expect(screen.getByText('Search Warrant (4)')).toBeInTheDocument()
      expect(screen.getByText('Other Agency Assist')).toBeInTheDocument()
    })
  })
})
