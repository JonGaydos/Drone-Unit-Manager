import { describe, it, expect } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import DigestPreferencesCard from './DigestPreferencesCard'

// G-1: Settings > General had no digest preferences screen although the
// manual described one. Endpoints: GET/PUT /api/notifications/preferences,
// GET /api/notifications/preview, POST /api/notifications/send-test,
// GET /api/notifications/log.

const ALL = [
  'pending_approvals', 'needs_review', 'expiring_certs', 'expiring_registrations',
  'overdue_maintenance', 'assigned_missions', 'overdue_checkouts', 'recent_incidents',
]

const PREFS = {
  enabled: true, frequency: 'daily', send_time: '07:00', send_day: null,
  categories: ALL, email_override: null,
}

const LOG = [
  { id: 2, sent_at: '2026-03-02T13:00:00+00:00', subject: 'Sample Unit — Daily Digest', status: 'test', error_message: null, item_count: 2 },
  { id: 1, sent_at: '2026-03-01T13:00:00+00:00', subject: 'Sample Unit — Daily Digest', status: 'sent', error_message: null, item_count: 1 },
]

function mockMount({ prefs = PREFS, log = LOG } = {}) {
  server.use(
    http.get('/api/notifications/preferences', () => HttpResponse.json(prefs)),
    http.get('/api/notifications/log', ({ request }) => {
      // The card asks for the signed-in user's own sends, even for an admin.
      if (new URL(request.url).searchParams.get('mine') !== 'true') return HttpResponse.json([])
      return HttpResponse.json(log)
    }),
  )
}

describe('DigestPreferencesCard', () => {
  it('shows the stored preferences and the send log', async () => {
    mockMount()
    renderWithProviders(<DigestPreferencesCard />, { role: 'pilot' })

    expect(await screen.findByLabelText('Send me email digests')).toBeChecked()
    expect(screen.getByLabelText('Frequency')).toHaveValue('daily')
    expect(screen.getByLabelText('Send at')).toHaveValue('07:00')
    expect(screen.getByLabelText('Expiring Certifications')).toBeChecked()
    // The day only matters for a weekly digest.
    expect(screen.queryByLabelText('Send on')).toBeNull()
    const log = await screen.findByRole('table', { name: 'Digest send log' })
    expect(within(log).getByText('Test')).toBeInTheDocument()
    expect(within(log).getByText('Sent')).toBeInTheDocument()
  })

  it('saves frequency, day, time and categories', async () => {
    let sent = null
    mockMount()
    server.use(http.put('/api/notifications/preferences', async ({ request }) => {
      sent = await request.json()
      return HttpResponse.json({ ok: true })
    }))
    const { user } = renderWithProviders(<DigestPreferencesCard />, { role: 'pilot' })
    await screen.findByLabelText('Send me email digests')

    await user.selectOptions(screen.getByLabelText('Frequency'), 'weekly')
    await user.selectOptions(screen.getByLabelText('Send on'), '4')
    await user.selectOptions(screen.getByLabelText('Send at'), '18:00')
    await user.click(screen.getByLabelText('Recent Incidents'))
    await user.click(screen.getByRole('button', { name: 'Save Preferences' }))

    await waitFor(() => expect(sent).not.toBeNull())
    expect(sent).toEqual({
      enabled: true, frequency: 'weekly', send_time: '18:00', send_day: 4,
      categories: ALL.filter(c => c !== 'recent_incidents'),
    })
    expect(await screen.findByText('Digest preferences saved')).toBeInTheDocument()
  })

  it('offers the email override only to roles that may redirect the digest', async () => {
    mockMount()
    renderWithProviders(<DigestPreferencesCard />, { role: 'pilot' })
    await screen.findByLabelText('Send me email digests')
    expect(screen.queryByLabelText('Send to another address')).toBeNull()
  })

  it('saves the email override for a supervisor', async () => {
    let sent = null
    mockMount()
    server.use(http.put('/api/notifications/preferences', async ({ request }) => {
      sent = await request.json()
      return HttpResponse.json({ ok: true })
    }))
    const { user } = renderWithProviders(<DigestPreferencesCard />, { role: 'supervisor' })
    const override = await screen.findByLabelText('Send to another address')
    await user.type(override, 'desk@example.test')
    await user.click(screen.getByRole('button', { name: 'Save Preferences' }))

    await waitFor(() => expect(sent).not.toBeNull())
    expect(sent.email_override).toBe('desk@example.test')
  })

  it('previews the digest by section', async () => {
    mockMount()
    server.use(http.get('/api/notifications/preview', () => HttpResponse.json({
      empty: false,
      sections: {
        expiring_certs: [{ id: 1, pilot: 'Robin Vale' }, { id: 2, pilot: 'Sam Reed' }],
        needs_review: [{ id: 0, count: 5 }],
      },
    })))
    const { user } = renderWithProviders(<DigestPreferencesCard />, { role: 'pilot' })
    await screen.findByLabelText('Send me email digests')
    await user.click(screen.getByRole('button', { name: 'Preview' }))

    expect(await screen.findByText('Expiring Certifications: 2')).toBeInTheDocument()
    expect(screen.getByText('Flights Needing Review: 5')).toBeInTheDocument()
  })

  it('says when the digest would be empty', async () => {
    mockMount()
    server.use(http.get('/api/notifications/preview', () =>
      HttpResponse.json({ empty: true, message: 'No actionable items to report', sections: {} })))
    const { user } = renderWithProviders(<DigestPreferencesCard />, { role: 'pilot' })
    await screen.findByLabelText('Send me email digests')
    await user.click(screen.getByRole('button', { name: 'Preview' }))
    expect(await screen.findByText('No actionable items to report')).toBeInTheDocument()
  })

  it('sends a test digest and reloads the log', async () => {
    let logLoads = 0
    mockMount()
    server.use(
      http.get('/api/notifications/log', () => { logLoads += 1; return HttpResponse.json(LOG) }),
      http.post('/api/notifications/send-test', () =>
        HttpResponse.json({ ok: true, message: 'Test digest sent to pilot@example.test' })),
    )
    const { user } = renderWithProviders(<DigestPreferencesCard />, { role: 'pilot' })
    await screen.findByLabelText('Send me email digests')
    await waitFor(() => expect(logLoads).toBe(1))
    await user.click(screen.getByRole('button', { name: 'Send Test' }))

    expect(await screen.findByText('Test digest sent to pilot@example.test')).toBeInTheDocument()
    await waitFor(() => expect(logLoads).toBe(2))
  })

  it('shows the reason when a test digest is not sent', async () => {
    mockMount()
    server.use(http.post('/api/notifications/send-test', () =>
      HttpResponse.json({ detail: 'Too many test emails. Try again in a few minutes.' }, { status: 429 })))
    const { user } = renderWithProviders(<DigestPreferencesCard />, { role: 'pilot' })
    await screen.findByLabelText('Send me email digests')
    await user.click(screen.getByRole('button', { name: 'Send Test' }))
    expect(await screen.findByText(/Too many test emails/)).toBeInTheDocument()
  })
})
