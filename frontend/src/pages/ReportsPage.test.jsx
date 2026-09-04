import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import ReportsPage from './ReportsPage'

// Mount endpoints (Promise.all; whole chain .catch -> swallowed, /settings has
// its own .catch -> []):
//   GET /pilots    (array)
//   GET /vehicles  (array)
//   GET /settings  (array; checked for org_logo)
// Generate: POST /reports/generate -> renders preview. PDF: downloadPost
// /reports/generate/pdf. CSV: GET /export/:type/csv.

function mockMount(overrides = {}) {
  const base = {
    pilots: () => HttpResponse.json([{ id: 1, full_name: 'Jane Doe', is_active: true }]),
    vehicles: () => HttpResponse.json([{ id: 5, manufacturer: 'Skydio', model: 'X10', nickname: 'Alpha' }]),
    settings: () => HttpResponse.json([]),
    ...overrides,
  }
  server.use(
    http.get('/api/pilots', base.pilots),
    http.get('/api/vehicles', base.vehicles),
    http.get('/api/settings', base.settings),
  )
}

describe('ReportsPage', () => {
  it('renders without crashing', async () => {
    mockMount()
    renderWithProviders(<ReportsPage />, { role: 'admin' })
    expect(await screen.findByText('Report Builder')).toBeInTheDocument()
  })

  it('renders pilots and vehicles into the selectors from a populated payload', async () => {
    mockMount()
    renderWithProviders(<ReportsPage />, { role: 'admin' })
    expect(await screen.findByText('Jane Doe')).toBeInTheDocument()
    expect(screen.getByText(/Skydio X10/)).toBeInTheDocument()
    // Preview empty prompt before generating.
    expect(screen.getByText(/Configure your report settings and click Generate/)).toBeInTheDocument()
  })

  it('shows the empty selectors when there are no pilots or vehicles', async () => {
    mockMount({ pilots: () => HttpResponse.json([]), vehicles: () => HttpResponse.json([]) })
    renderWithProviders(<ReportsPage />, { role: 'admin' })
    expect(await screen.findByText('No pilots available')).toBeInTheDocument()
    expect(screen.getByText('No vehicles available')).toBeInTheDocument()
  })

  it('renders the builder when /pilots 500s (error swallowed, lists empty)', async () => {
    mockMount({ pilots: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }) })
    renderWithProviders(<ReportsPage />, { role: 'admin' })
    // Whole Promise.all .catch -> loading clears; builder renders.
    expect(await screen.findByText('Report Builder')).toBeInTheDocument()
    expect(screen.getByText('No pilots available')).toBeInTheDocument()
  })

  it('generates a report via POST /reports/generate and renders the preview', async () => {
    let body = null
    mockMount()
    server.use(
      http.post('/api/reports/generate', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({
          title: 'Flight Summary',
          summary: { total_flights: 12, total_hours: 8 },
          rows: [{ pilot: 'Jane Doe', flights: 12 }],
          columns: ['pilot', 'flights'],
        })
      }),
    )
    const { user } = renderWithProviders(<ReportsPage />, { role: 'admin' })
    await screen.findByText('Report Builder')

    await user.click(screen.getByRole('button', { name: /Generate/ }))

    // Anchor on preview-only content (the report-type <option> also reads
    // "Flight Summary", so match the summary card key, not the bare text).
    expect(await screen.findByText('total flights')).toBeInTheDocument()
    expect(screen.getByText('total hours')).toBeInTheDocument()
    expect(body).toMatchObject({ report_type: 'flight_summary' })
  })
  // --- Filter pickers per report type -------------------------------------
  //
  // The generators apply different filters, and the page used to offer both
  // pickers for every type. Selecting a pilot on a report that ignores it made
  // the preview header claim a narrowing that never happened.

  const selectReportType = async (user, value) => {
    const select = screen.getByRole('combobox', { name: /Report Type/i })
    await user.selectOptions(select, value)
  }

  // One case per report type, mirroring REPORT_FILTERS in the page. A table
  // rather than five near-identical tests: the map IS the thing under test, so
  // it reads better and there is one place to add a report type.
  const PICKER_CASES = [
    { type: 'pilot_hours', pilots: true, vehicles: true },
    { type: 'equipment_utilization', pilots: true, vehicles: true },
    { type: 'per_pilot_annual_review', pilots: true, vehicles: false },
    { type: 'pilot_certifications', pilots: true, vehicles: false },
    { type: 'battery_status', pilots: false, vehicles: false },
    { type: 'maintenance_history', pilots: false, vehicles: false },
    { type: 'annual_unit_report', pilots: false, vehicles: false },
  ]

  it.each(PICKER_CASES)(
    'shows pilots=$pilots vehicles=$vehicles on $type',
    async ({ type, pilots, vehicles }) => {
      mockMount()
      const { user } = renderWithProviders(<ReportsPage />, { role: 'admin' })
      await screen.findByText('Report Builder')

      await selectReportType(user, type)

      const expectPilots = expect(screen.queryByText('Pilots'))
      const expectVehicles = expect(screen.queryByText('Vehicles'))
      if (pilots) expectPilots.toBeInTheDocument()
      else expectPilots.not.toBeInTheDocument()
      if (vehicles) expectVehicles.toBeInTheDocument()
      else expectVehicles.not.toBeInTheDocument()
    },
  )

  /** Mount with a stubbed generate endpoint and capture the request body. */
  const mountCapturingRequest = async () => {
    const captured = {}
    mockMount()
    server.use(http.post('/api/reports/generate', async ({ request }) => {
      captured.body = await request.json()
      return HttpResponse.json({ title: 'Report', summary: {}, rows: [], columns: [] })
    }))
    const { user } = renderWithProviders(<ReportsPage />, { role: 'admin' })
    await screen.findByText('Report Builder')
    return { user, captured }
  }

  it('omits a filter the chosen report ignores instead of sending it', async () => {
    const { user, captured } = await mountCapturingRequest()

    // Choose a pilot while on a report that uses it...
    await user.click(await screen.findByLabelText(/Jane Doe/i))
    // ...then switch to one that does not.
    await selectReportType(user, 'battery_status')
    await user.click(screen.getByRole('button', { name: /Generate/ }))

    expect(captured.body.report_type).toBe('battery_status')
    expect(captured.body.pilot_ids).toBeUndefined()
    expect(captured.body.vehicle_ids).toBeUndefined()
  })

  it('keeps the selection so switching report types and back restores it', async () => {
    const { user, captured } = await mountCapturingRequest()

    await user.click(await screen.findByLabelText(/Jane Doe/i))
    await selectReportType(user, 'battery_status')
    await selectReportType(user, 'pilot_hours')
    await user.click(screen.getByRole('button', { name: /Generate/ }))

    expect(captured.body.pilot_ids).toEqual([1])
  })

  // Vendor and guest operators fly the unit's aircraft but are not the unit's
  // own activity. Reports leave them out unless asked, so the default has to be
  // off and the option has to actually reach the request.
  describe('non-unit flights', () => {
    it('does not ask for them by default', async () => {
      const { user, captured } = await mountCapturingRequest()

      await user.click(screen.getByRole('button', { name: /Generate/ }))

      expect(screen.getByLabelText(/Include non-unit flights/i)).not.toBeChecked()
      expect(captured.body.include_non_unit).toBeUndefined()
    })

    it('sends the flag once the option is ticked', async () => {
      const { user, captured } = await mountCapturingRequest()

      await user.click(screen.getByLabelText(/Include non-unit flights/i))
      await user.click(screen.getByRole('button', { name: /Generate/ }))

      expect(captured.body.include_non_unit).toBe(true)
    })
  })
})
