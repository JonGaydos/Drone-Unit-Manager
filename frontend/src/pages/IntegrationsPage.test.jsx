import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import { api } from '@/api/client'
import IntegrationsPage from './IntegrationsPage'

// Mount endpoints:
//   GET /settings      (array of {key, value}; setSettings, .catch swallowed)
//   GET /sync/status   (per ProviderCard useEffect; .catch swallowed)
// Secrets (skydio_api_token / smtp_password) arrive redacted as "********".
// Crucially the page NEVER seeds those values into inputs — token/password
// fields stay empty and only show a "saved" placeholder, so the marker is
// never shown as cleartext. Save: PUT /settings/bulk with the changed keys.
// Test connection: POST /sync/test.

const REDACTED = '********'

const SETTINGS = [
  { key: 'skydio_api_token', value: REDACTED },
  { key: 'skydio_token_id', value: 'tok-123' },
  { key: 'smtp_host', value: 'smtp.example.gov' },
  { key: 'smtp_password', value: REDACTED },
  { key: 'smtp_from_address', value: 'drones@example.gov' },
]

function mockMount(overrides = {}) {
  const base = {
    settings: () => HttpResponse.json(SETTINGS),
    syncStatus: () => HttpResponse.json({ provider: 'skydio', last_sync: null, sync_interval: 0 }),
    ...overrides,
  }
  server.use(
    http.get('/api/settings', base.settings),
    http.get('/api/sync/status', base.syncStatus),
  )
}

describe('IntegrationsPage', () => {
  it('renders without crashing', async () => {
    mockMount()
    renderWithProviders(<IntegrationsPage />, { role: 'admin' })
    expect(await screen.findByRole('heading', { name: 'Integrations' })).toBeInTheDocument()
  })

  it('renders provider, SMTP, and import sections from a populated payload', async () => {
    mockMount()
    renderWithProviders(<IntegrationsPage />, { role: 'admin' })
    expect(await screen.findByText('Skydio')).toBeInTheDocument()
    expect(screen.getByText('Email (SMTP)')).toBeInTheDocument()
    expect(screen.getByText('Flight Log Import')).toBeInTheDocument()
    // A stored token marks the provider Connected (value is truthy). The badge
    // shows once sync status has resolved its useEffect.
    expect(await screen.findByText(/Connected/)).toBeInTheDocument()
  })

  it('handles an empty settings payload (provider Not configured)', async () => {
    mockMount({ settings: () => HttpResponse.json([]) })
    renderWithProviders(<IntegrationsPage />, { role: 'admin' })
    expect(await screen.findByText('Skydio')).toBeInTheDocument()
    // With no stored token, the provider (and SMTP) show "Not configured" and
    // nothing shows "Connected".
    expect(screen.getAllByText('Not configured').length).toBeGreaterThan(0)
    expect(screen.queryByText(/Connected/)).toBeNull()
  })

  it('renders the page when /settings 500s (error swallowed, loading clears)', async () => {
    mockMount({ settings: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }) })
    renderWithProviders(<IntegrationsPage />, { role: 'admin' })
    // loading state clears in finally(); the chrome renders with empty settings.
    expect(await screen.findByRole('heading', { name: 'Integrations' })).toBeInTheDocument()
    expect(screen.getByText('Skydio')).toBeInTheDocument()
  })

  it('does not leak the redacted secret marker as cleartext in any field', async () => {
    mockMount()
    const { user } = renderWithProviders(<IntegrationsPage />, { role: 'admin' })
    await screen.findByText('Skydio')

    // Expand the Skydio provider card to reveal the API Token field.
    await user.click(screen.getByText('Skydio'))
    const tokenInput = await screen.findByLabelText('API Token')
    // The secret is NOT seeded into the input; it stays empty and shows the
    // "saved" placeholder instead of the marker.
    expect(tokenInput).toHaveValue('')
    expect(tokenInput).toHaveAttribute('placeholder', expect.stringContaining('saved'))

    // No input or rendered text anywhere exposes the literal "********".
    expect(screen.queryByDisplayValue(REDACTED)).toBeNull()
    expect(screen.queryByText(REDACTED)).toBeNull()
  })

  it('saves provider credentials via PUT /settings/bulk carrying only the typed token', async () => {
    let body = null
    mockMount()
    server.use(
      http.put('/api/settings/bulk', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ ok: true })
      }),
    )
    const { user } = renderWithProviders(<IntegrationsPage />, { role: 'admin' })
    await screen.findByText('Skydio')
    await user.click(screen.getByText('Skydio'))

    const tokenInput = await screen.findByLabelText('API Token')
    await user.type(tokenInput, 'new-secret-token')
    await user.click(screen.getByRole('button', { name: 'Save Credentials' }))

    await screen.findByText('Skydio')
    expect(Array.isArray(body)).toBe(true)
    const tok = body.find(i => i.key === 'skydio_api_token')
    expect(tok).toEqual({ key: 'skydio_api_token', value: 'new-secret-token' })
    // The marker is never written back.
    expect(body.every(i => i.value !== REDACTED)).toBe(true)
  })

  it('saves the telemetry auto-sync interval via PUT /settings/bulk', async () => {
    let body = null
    mockMount()
    server.use(
      http.put('/api/settings/bulk', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ ok: true })
      }),
    )
    const { user } = renderWithProviders(<IntegrationsPage />, { role: 'admin' })
    await screen.findByText('Skydio')
    await user.click(screen.getByText('Skydio'))

    const select = await screen.findByLabelText('Telemetry Auto-Sync')
    await user.selectOptions(select, '30')

    await screen.findByText('Skydio')
    expect(Array.isArray(body)).toBe(true)
    expect(body).toEqual([{ key: 'telemetry_sync_interval', value: '30' }])
  })

  it('shows the auto-sync description and a telemetry status block with remaining count', async () => {
    mockMount({
      syncStatus: () => HttpResponse.json({
        provider: 'skydio', last_sync: '2026-07-11T20:00:00Z', sync_interval: '1440',
        last_telemetry_sync: '2026-07-11T20:30:00Z', telemetry_sync_interval: '30',
        last_telemetry_sync_result: { synced: 7 }, telemetry_remaining: 42,
      }),
    })
    const { user } = renderWithProviders(<IntegrationsPage />, { role: 'admin' })
    await screen.findByText('Skydio')
    await user.click(screen.getByText('Skydio'))

    // Auto-Sync Interval description present.
    expect(await screen.findByText(/pulls new flights, vehicles, batteries/i)).toBeInTheDocument()
    // Telemetry status block: its own "Last telemetry" label and the remaining count.
    expect(screen.getByText('Last telemetry')).toBeInTheDocument()
    expect(screen.getByText('42 flights')).toBeInTheDocument()
  })

  it('fires POST /sync/test when Test Connection is clicked', async () => {
    let tested = false
    mockMount()
    server.use(
      http.post('/api/sync/test', () => { tested = true; return HttpResponse.json({ ok: true }) }),
    )
    const { user } = renderWithProviders(<IntegrationsPage />, { role: 'admin' })
    await screen.findByText('Skydio')
    await user.click(screen.getByText('Skydio'))

    await user.click(await screen.findByRole('button', { name: /Test Connection/ }))
    await screen.findByText('Skydio')
    expect(tested).toBe(true)
  })

  // What an import chose NOT to do is the part that goes wrong quietly. A BRINC
  // export whose drone is missing from the fleet skips every row belonging to
  // it, and the success line alone would report only the rows that worked.
  describe('import result notices', () => {
    async function importFile(result) {
      mockMount()
      server.use(http.post('/api/export/flights/import/log', () => HttpResponse.json(result)))
      const { user } = renderWithProviders(<IntegrationsPage />, { role: 'admin' })
      await screen.findByText('Flight Log Import')

      const input = document.querySelector('input[type="file"]')
      await user.upload(input, new File(['Flight Id\n'], 'brinc.csv', { type: 'text/csv' }))
      await user.click(screen.getByRole('button', { name: 'Import' }))
      return user
    }

    it('reports drones that were not in the fleet, not just the flights that landed', async () => {
      await importFile({
        format_detected: 'brinc_csv',
        flights_imported: 62,
        flights_skipped: 156,
        unmatched_drones: { 'l2d-0003-00011': 152 },
      })

      // The panel and the toast both say it, hence findAllByText.
      expect(await screen.findAllByText(/Imported 62 flights/)).not.toHaveLength(0)
      expect(screen.getByText(/l2d-0003-00011 \(152 flights\)/)).toBeInTheDocument()
    })

    it('shows the timezone warning', async () => {
      await importFile({
        format_detected: 'brinc_csv',
        flights_imported: 3,
        warnings: ['Export heading claims UTC-5, but this instance is UTC-4.'],
      })

      expect(await screen.findByText(/claims UTC-5/)).toBeInTheDocument()
    })

    it('names the pilots it created and the rows it dropped', async () => {
      await importFile({
        format_detected: 'brinc_csv',
        flights_imported: 5,
        pilots_created: 1,
        pilots_created_names: ['Pat (Vendor) Quinn'],
        flights_skipped_zero_duration: 69,
      })

      expect(await screen.findByText(/confirm these are unit pilots: Pat \(Vendor\) Quinn/)).toBeInTheDocument()
      expect(screen.getByText(/69 row\(s\) had no flight time/)).toBeInTheDocument()
    })

    it('caps a long error list instead of flooding the panel', async () => {
      await importFile({
        format_detected: 'brinc_csv',
        flights_imported: 1,
        errors: Array.from({ length: 9 }, (_, i) => `Row ${i + 2}: no Flight Id`),
      })

      expect(await screen.findByText('Row 2: no Flight Id')).toBeInTheDocument()
      expect(screen.queryByText('Row 8: no Flight Id')).not.toBeInTheDocument()
      expect(screen.getByText('and 4 more')).toBeInTheDocument()
    })

    // One upload lands in one of three shapes, and each reports different
    // numbers. Reading a skipped duplicate as a success is the one that
    // matters: it tells the operator a flight was added when nothing was.
    it('says a duplicate was skipped rather than imported', async () => {
      await importFile({ skipped: true, flight_id: 42, format_detected: 'dji' })

      expect(await screen.findByText(/Flight #42 already exists \(skipped\)/)).toBeInTheDocument()
      expect(screen.queryByText(/imported successfully/)).not.toBeInTheDocument()
    })

    it('reports a single flight with its telemetry count and format', async () => {
      await importFile({ flight_id: 7, points_imported: 1200, format_detected: 'dji', date: '2026-05-01' })

      // The panel and the toast both carry the line, hence findAllByText.
      expect(await screen.findAllByText(/Flight #7 imported successfully/)).not.toHaveLength(0)
      expect(screen.getAllByText(/1200 telemetry points/)).not.toHaveLength(0)
      expect(screen.getAllByText(/2026-05-01/)).not.toHaveLength(0)
    })

    it('reports a batch with what it created alongside it', async () => {
      await importFile({
        format_detected: 'brinc_csv', flights_imported: 4,
        pilots_created: 2, vehicles_created: 1, flights_skipped: 3,
      })

      expect(await screen.findAllByText(/Imported 4 flights/)).not.toHaveLength(0)
      expect(screen.getByText(/2 pilot\(s\) and 1 vehicle\(s\) created/)).toBeInTheDocument()
      expect(screen.getByText(/3 duplicate\(s\) skipped/)).toBeInTheDocument()
    })

    it('writes one imported flight in the singular', async () => {
      await importFile({ format_detected: 'litchi', flights_imported: 1 })

      expect(await screen.findAllByText(/Imported 1 flight(?!s)/)).not.toHaveLength(0)
    })

    it('adds nothing when an import had no notices', async () => {
      await importFile({ format_detected: 'litchi', flights_imported: 1 })

      expect(await screen.findAllByText(/Imported 1 flight/)).not.toHaveLength(0)
      expect(screen.queryByText(/Not in the fleet/)).not.toBeInTheDocument()
    })
  })

  // A full provider export is hundreds of megabytes and over a thousand
  // flights; the one measured took four minutes end to end. With the default
  // thirty-second timeout the browser aborts while the server is still
  // importing, and the operator is told it failed.
  it('does not time out an import in the browser', async () => {
    let options = null
    const realUpload = api.upload
    api.upload = (path, body, headers, opts) => { options = opts; return Promise.resolve({ imported: 1 }) }
    try {
      mockMount()
      const { user } = renderWithProviders(<IntegrationsPage />, { role: 'admin' })
      await screen.findByText('Flight Log Import')

      const input = document.querySelector('input[type="file"]')
      await user.upload(input, new File(['{}'], 'export.zip', { type: 'application/zip' }))
      await user.click(screen.getByRole('button', { name: 'Import' }))

      expect(options).toMatchObject({ timeout: 0 })
    } finally {
      api.upload = realUpload
    }
  })
})
