import { describe, it, expect } from 'vitest'
import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
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
    http.get('/api/pilots', () => HttpResponse.json([{ id: 5, full_name: 'Jane Doe', is_active: true }])),
    http.get('/api/vehicles', () => HttpResponse.json([{ id: 2, nickname: 'Falcon', model: 'Mavic 3' }])),
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
    server.use(http.get('/api/auth/me', () => HttpResponse.json({ id: 9, username: 'viewer', role: 'viewer' })))
    mockMount()
    renderWithProviders(<IncidentPage />, { role: 'viewer' })
    await screen.findByText('Hard Landing')
    expect(screen.queryByRole('button', { name: /New Report/ })).toBeNull()
  })
})
