import { describe, it, expect, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import SettingsPage from './SettingsPage'

// Mount endpoints (useEffect):
//   GET /settings           (array of {key, value}; .catch(console.error))
//   admin-only:
//   GET /auth/users         (array)
//   GET /pilots             (array)
//   GET /currency/rules     (array)
//   GET /backup/status      ({ enabled, retention, hour, count, last_backup_at })
// Save: PUT /settings/bulk with [{key, value}, ...] (handleSave gathers refs).
// Secret keys (skydio_api_token / smtp_password) come back redacted as
// "********"; the General-tab fields() never seed a password value into an
// input, and the Integrations tab seeds nothing either, so cleartext never
// renders. Admin-gated: viewer sees only the General tab and no Save button.

const REDACTED = '********'

const SETTINGS = [
  { key: 'org_name', value: 'Metro PD Drone Unit' },
  { key: 'org_default_lat', value: '38.9' },
  { key: 'org_default_lon', value: '-77.0' },
  { key: 'org_location_name', value: 'HQ Rooftop' },
  // Secrets returned redacted by the backend.
  { key: 'skydio_api_token', value: REDACTED },
  { key: 'smtp_password', value: REDACTED },
]

const USERS = [
  { id: 1, username: 'admin', display_name: 'Admin User', role: 'admin', is_active: true },
  { id: 2, username: 'jpilot', display_name: 'Jamie Pilot', role: 'pilot', is_active: true },
]

const PILOTS = [
  { id: 10, full_name: 'Jamie Pilot', badge_number: 'B-10', is_active: true },
]

const RULES = [
  { id: 5, name: 'Quarterly currency', required_hours: 5, period_days: 90, required_flights: null, is_active: true, vehicle_model: null, description: null },
]

function mockMount(overrides = {}) {
  const base = {
    settings: () => HttpResponse.json(SETTINGS),
    users: () => HttpResponse.json(USERS),
    pilots: () => HttpResponse.json(PILOTS),
    rules: () => HttpResponse.json(RULES),
    backup: () => HttpResponse.json({ enabled: true, retention: 7, hour: 3, count: 4, last_backup_at: null }),
    ...overrides,
  }
  server.use(
    http.get('/api/settings', base.settings),
    http.get('/api/auth/users', base.users),
    http.get('/api/pilots', base.pilots),
    http.get('/api/currency/rules', base.rules),
    http.get('/api/backup/status', base.backup),
  )
}

describe('SettingsPage', () => {
  it('renders without crashing', async () => {
    mockMount()
    renderWithProviders(<SettingsPage />, { role: 'admin' })
    expect(await screen.findByText('Organization')).toBeInTheDocument()
  })

  it('loads settings into the organization field', async () => {
    mockMount()
    renderWithProviders(<SettingsPage />, { role: 'admin' })
    // Currency rule (admin section) proves isAdmin settled + /settings loaded.
    expect(await screen.findByText('Quarterly currency')).toBeInTheDocument()
    expect(await screen.findByDisplayValue('Metro PD Drone Unit')).toBeInTheDocument()
  })

  it('handles empty payloads without crashing (no currency rules)', async () => {
    mockMount({
      settings: () => HttpResponse.json([]),
      users: () => HttpResponse.json([]),
      rules: () => HttpResponse.json([]),
    })
    renderWithProviders(<SettingsPage />, { role: 'admin' })
    expect(await screen.findByText('Organization')).toBeInTheDocument()
    // Empty currency-rules UI.
    expect(screen.getByText(/No rules defined yet/)).toBeInTheDocument()
  })

  it('renders the page when /settings 500s (error swallowed by .catch)', async () => {
    mockMount({ settings: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }) })
    renderWithProviders(<SettingsPage />, { role: 'admin' })
    // Page chrome still renders; org field is empty.
    expect(await screen.findByText('Organization')).toBeInTheDocument()
    expect(screen.getByLabelText('Organization Name')).toHaveValue('')
  })

  it('admin-gates the page: viewers see no Save button and no admin sections', async () => {
    mockMount()
    server.use(http.get('/api/auth/me', () => HttpResponse.json({ id: 9, username: 'v', role: 'viewer' })))
    renderWithProviders(<SettingsPage />, { role: 'viewer' })
    expect(await screen.findByText('Organization')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Save Settings/ })).toBeNull()
    // Admin-only sections are absent.
    expect(screen.queryByText('Currency Rules')).toBeNull()
    expect(screen.queryByText('Users')).toBeNull()
  })

  it('does not leak the redacted secret marker as a field value (General tab)', async () => {
    mockMount()
    renderWithProviders(<SettingsPage />, { role: 'admin' })
    await screen.findByText('Organization')
    // The org field shows real cleartext; no input anywhere carries "********".
    const allInputs = screen.getAllByRole('textbox')
    for (const el of allInputs) {
      expect(el).not.toHaveValue(REDACTED)
    }
  })

  it('save flow fires PUT /settings/bulk with a {key,value} array carrying the edited value', async () => {
    let body = null
    mockMount()
    server.use(
      http.put('/api/settings/bulk', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ ok: true })
      }),
    )
    const { user } = renderWithProviders(<SettingsPage />, { role: 'admin' })
    // Wait for isAdmin to settle so the field is enabled and seeded.
    await screen.findByText('Quarterly currency')
    const orgInput = await screen.findByDisplayValue('Metro PD Drone Unit')

    await user.clear(orgInput)
    await user.type(orgInput, 'New Org Name')
    await user.click(screen.getByRole('button', { name: /Save Settings/ }))

    await screen.findByText('Organization')
    expect(Array.isArray(body)).toBe(true)
    const org = body.find(i => i.key === 'org_name')
    expect(org).toEqual({ key: 'org_name', value: 'New Org Name' })
  })

  // Defense-in-depth: handleSave() -> gatherInputs() seeds from `{ ...settings }`,
  // which includes secrets returned by GET /settings as the redaction marker
  // ("********"). The General tab renders no input for skydio_api_token /
  // smtp_password to override them, so gatherInputs() must DROP any key whose
  // current value is the marker before the bulk PUT. The marker must never be
  // echoed back to the server, while real edited non-secret values still ride
  // along.
  it('General-tab save drops redacted secret markers from the bulk payload (never echoes "********")', async () => {
    let body = null
    mockMount()
    server.use(
      http.put('/api/settings/bulk', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ ok: true })
      }),
    )
    const { user } = renderWithProviders(<SettingsPage />, { role: 'admin' })
    await screen.findByText('Quarterly currency')
    const orgInput = await screen.findByDisplayValue('Metro PD Drone Unit')

    await user.clear(orgInput)
    await user.type(orgInput, 'New Org Name')
    await user.click(screen.getByRole('button', { name: /Save Settings/ }))
    await screen.findByText('Organization')

    // No key carries the redaction marker.
    expect(body.every(i => i.value !== REDACTED)).toBe(true)
    // Redacted secrets are dropped entirely.
    expect(body.find(i => i.key === 'skydio_api_token')).toBeUndefined()
    expect(body.find(i => i.key === 'smtp_password')).toBeUndefined()
    // A real edited non-secret value is still present.
    const org = body.find(i => i.key === 'org_name')
    expect(org).toEqual({ key: 'org_name', value: 'New Org Name' })
  })

  it('saves the selected display timezone in the bulk payload', async () => {
    let bulkBody = null
    mockMount({
      settings: () => HttpResponse.json([{ key: 'display_timezone', value: 'America/Chicago' }]),
    })
    server.use(
      http.put('/api/settings/bulk', async ({ request }) => { bulkBody = await request.json(); return HttpResponse.json({ ok: true }) }),
    )
    const { user } = renderWithProviders(<SettingsPage />, { role: 'admin' })

    // Wait for isAdmin to settle so the select is enabled.
    await screen.findByText('Quarterly currency')
    const select = await screen.findByLabelText('Time Zone')
    await user.selectOptions(select, 'America/Denver')
    await user.click(screen.getByRole('button', { name: 'Save Settings' }))

    await waitFor(() => expect(bulkBody).not.toBeNull())
    expect(bulkBody).toEqual(expect.arrayContaining([{ key: 'display_timezone', value: 'America/Denver' }]))
  })
  // --- Flight purposes ------------------------------------------------------
  //
  // Editing here wrote a mission_purposes setting while the flight pages read
  // the flight_purposes table, so removing an option changed nothing on the
  // flight pages. Settings now manages the table directly.

  const PURPOSE_ROWS = [
    { id: 1, name: 'Patrol', sort_order: 1, flight_count: 12, mission_count: 3 },
    { id: 2, name: 'Mapping', sort_order: 2, flight_count: 0, mission_count: 0 },
  ]

  const mockPurposes = (rows = PURPOSE_ROWS) =>
    server.use(http.get('/api/flights/purposes/usage', () => HttpResponse.json(rows)))

  it('lists purposes from the table with their usage counts', async () => {
    mockMount()
    mockPurposes()
    renderWithProviders(<SettingsPage />, { role: 'admin' })

    expect(await screen.findByText('Patrol')).toBeInTheDocument()
    expect(screen.getByText('(15 in use)')).toBeInTheDocument()   // 12 flights + 3 missions
    expect(screen.getByText('Mapping')).toBeInTheDocument()
  })

  it('warns what deleting will do before doing it', async () => {
    mockMount()
    mockPurposes()
    const { user } = renderWithProviders(<SettingsPage />, { role: 'admin' })
    await screen.findByText('Patrol')

    await user.click(screen.getByRole('button', { name: 'Delete purpose Patrol' }))

    expect(await screen.findByText(/Delete "Patrol"\?/)).toBeInTheDocument()
    expect(screen.getByText(/12 flights will have their purpose cleared/)).toBeInTheDocument()
    expect(screen.getByText(/3 mission logs will keep "Patrol"/)).toBeInTheDocument()
  })

  it('says nothing will change when a purpose is unused', async () => {
    mockMount()
    mockPurposes()
    const { user } = renderWithProviders(<SettingsPage />, { role: 'admin' })
    await screen.findByText('Mapping')

    await user.click(screen.getByRole('button', { name: 'Delete purpose Mapping' }))

    expect(await screen.findByText(/no records will change/)).toBeInTheDocument()
  })

  it('deletes against the table only after confirmation', async () => {
    let deleted = null
    mockMount()
    mockPurposes()
    server.use(http.delete('/api/flights/purposes/:id', ({ params }) => {
      deleted = params.id
      return HttpResponse.json({ ok: true, flights_cleared: 12, missions_untouched: 3 })
    }))
    const { user } = renderWithProviders(<SettingsPage />, { role: 'admin' })
    await screen.findByText('Patrol')

    await user.click(screen.getByRole('button', { name: 'Delete purpose Patrol' }))
    expect(deleted).toBeNull()      // nothing happens on opening the dialog

    await user.click(await screen.findByRole('button', { name: /Delete purpose$/i }))
    expect(deleted).toBe('1')
  })

  it('adds a purpose against the table', async () => {
    let posted = null
    mockMount()
    mockPurposes()
    server.use(http.post('/api/flights/purposes', async ({ request }) => {
      posted = await request.json()
      return HttpResponse.json({ id: 9, name: 'Night Ops' })
    }))
    const { user } = renderWithProviders(<SettingsPage />, { role: 'admin' })
    await screen.findByText('Patrol')

    await user.type(screen.getByPlaceholderText('Add a purpose...'), 'Night Ops')
    await user.click(screen.getByRole('button', { name: 'Add' }))

    expect(posted).toEqual({ name: 'Night Ops' })
  })

  // The manual backup failed with a timeout while the 3am scheduled one worked,
  // because the scheduled job calls the archive builder in-process and never
  // crosses HTTP. build_backup_archive assembles every table and every uploaded
  // file before the first byte is sent, so the client's 30s default aborted it.
  //
  // Spied rather than driven through MSW: the default timeout is 30 seconds, so
  // no test can wait long enough to observe the abort. What matters is that the
  // call site opts out, and that is only visible in the arguments.
  it('takes a backup without the default request timeout', async () => {
    const { api } = await import('@/api/client')
    const spy = vi.spyOn(api, 'download').mockResolvedValue(undefined)
    try {
      mockMount()
      const { user } = renderWithProviders(<SettingsPage />, { role: 'admin' })
      await screen.findByText('Settings')

      await user.click(await screen.findByRole('button', { name: /Download Backup|Export Backup/i }))

      expect(spy).toHaveBeenCalledTimes(1)
      const [path, options] = spy.mock.calls[0]
      expect(path).toMatch(/^\/backup\/export/)
      expect(options).toMatchObject({ timeout: 0 })
    } finally {
      spy.mockRestore()
    }
  })
})
