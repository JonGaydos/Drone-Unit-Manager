import { describe, it, expect } from 'vitest'
import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { withPermissions } from '@/test/permissions'
import { fleetOptions, pilotOption, vehicleOption } from '@/test/options'
import { renderWithProviders } from '@/test/render'
import IncidentPage from './IncidentPage'

// Mount endpoints (Promise.all in load()):
//   GET /incidents?...          (array or { incidents })
//   GET /incidents/stats        -> { total, by_status: { open, ... } }
//   GET /pilots /vehicles
//   GET /flights?limit=100      (array or { flights })
// Create endpoint: POST /incidents { title, description, date, severity, category, report_type, ... }
const INCIDENTS = [
  { id: 1, date: '2026-05-01', title: 'Hard Landing', severity: 'moderate', category: 'crash', status: 'open', report_type: 'incident', description: 'Bumpy', pilot_id: 5, pilot_name: 'Jane Doe' },
]
const STATS = { total: 3, by_status: { open: 1, investigating: 1, resolved: 1 } }

function mockMount(overrides = {}) {
  const base = {
    incidents: () => HttpResponse.json(INCIDENTS),
    stats: () => HttpResponse.json(STATS),
    ...overrides,
  }
  server.use(
    http.get('/api/incidents/stats', base.stats),
    http.get('/api/incidents', base.incidents),
    http.get('/api/pilots/options', () => HttpResponse.json([pilotOption(5, 'Jane Doe')])),
    http.get('/api/fleet/options', () => HttpResponse.json(fleetOptions({ vehicles: [vehicleOption({ id: 2, nickname: 'Falcon', model: 'Mavic 3' })] }))),
    http.get('/api/flights', () => HttpResponse.json([])),
  )
}

describe('IncidentPage', () => {
  it('renders without crashing', async () => {
    mockMount()
    renderWithProviders(<IncidentPage />, { role: 'admin' })
    expect(await screen.findByText('Hard Landing')).toBeInTheDocument()
  })

  it('loads incident rows and stat cards from populated payloads', async () => {
    mockMount()
    renderWithProviders(<IncidentPage />, { role: 'admin' })
    expect(await screen.findByText('Hard Landing')).toBeInTheDocument()
    // Severity badge text is lowercase in the row; dropdown options are Title-cased.
    expect(screen.getByText('moderate')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()  // total stat
  })

  it('shows the empty state when there are no incidents', async () => {
    mockMount({ incidents: () => HttpResponse.json([]) })
    renderWithProviders(<IncidentPage />, { role: 'admin' })
    expect(await screen.findByText('No incidents found')).toBeInTheDocument()
  })

  it('falls back to the empty UI when the primary endpoint 500s', async () => {
    mockMount({ incidents: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }) })
    renderWithProviders(<IncidentPage />, { role: 'admin' })
    expect(await screen.findByText('No incidents found')).toBeInTheDocument()
  })

  it('creates an incident via POST /incidents with the filled fields', async () => {
    let createBody = null
    mockMount()
    server.use(http.post('/api/incidents', async ({ request }) => {
      createBody = await request.json()
      return HttpResponse.json({ id: 99, ...createBody })
    }))
    const { user } = renderWithProviders(<IncidentPage />, { role: 'admin' })

    await screen.findByText('Hard Landing')
    await user.click(screen.getByRole('button', { name: /New Report/ }))

    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('Title *'), 'Prop strike')
    await user.type(within(dialog).getByLabelText('Description *'), 'Hit a branch')
    await user.selectOptions(within(dialog).getByLabelText('Severity *'), 'major')
    await user.click(within(dialog).getByRole('button', { name: 'Report Incident' }))

    expect(createBody).not.toBeNull()
    expect(createBody.title).toBe('Prop strike')
    expect(createBody.description).toBe('Hit a branch')
    expect(createBody.severity).toBe('major')
    expect(createBody.report_type).toBe('incident')
  })

  it('hides the New Report button from a viewer', async () => {
    server.use(http.get('/api/auth/me', () => HttpResponse.json(withPermissions({ id: 9, username: 'viewer', role: 'viewer' }))))
    mockMount()
    renderWithProviders(<IncidentPage />, { role: 'viewer' })
    await screen.findByText('Hard Landing')
    expect(screen.queryByRole('button', { name: /New Report/ })).toBeNull()
  })

  it('keeps the page with flights.view off, and does not ask for flights', async () => {
    let asked = false
    mockMount()
    server.use(http.get('/api/flights', () => { asked = true; return HttpResponse.json({ flights: [] }) }))
    renderWithProviders(<IncidentPage />, { role: 'pilot', permissions: { 'flights.view': 'no' } })
    expect(await screen.findByRole('button', { name: /New Report/ })).toBeInTheDocument()
    expect(asked).toBe(false)
  })

  it('offers Resolve only where incidents.edit also covers the record', async () => {
    const rows = [{ ...INCIDENTS[0], id: 1, title: 'Mine', reported_by_id: 3 }, { ...INCIDENTS[0], id: 2, title: 'Theirs', reported_by_id: 4 }]
    mockMount({ incidents: () => HttpResponse.json(rows) })
    renderWithProviders(<IncidentPage />, {
      user: { id: 3, username: 'p', role: 'pilot' }, permissions: { 'incidents.resolve': 'yes' },
    })
    await screen.findByText('Mine')
    expect(screen.getAllByTitle('Resolve')).toHaveLength(1)
  })

  it('offers no Resolve without incidents.resolve', async () => {
    mockMount({ incidents: () => HttpResponse.json([{ ...INCIDENTS[0], reported_by_id: 3 }]) })
    renderWithProviders(<IncidentPage />, { user: { id: 3, username: 'p', role: 'pilot' } })
    await screen.findByText('Hard Landing')
    expect(screen.queryByTitle('Resolve')).toBeNull()
  })
})
