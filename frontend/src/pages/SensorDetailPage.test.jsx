import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderRoute } from '@/test/render'
import SensorDetailPage from './SensorDetailPage'

// Route param: :id. Mount endpoints:
//   GET /sensors/:id              (primary; failure -> "Sensor not found")
//   GET /sensors/:id/stats
//   GET /sensors/:id/flights
//   GET /maintenance?entity_type=sensor&entity_id=:id
//   GET /documents?...            (DocumentUpload)
const SENSOR = {
  id: 6, name: 'Thermal Cam', serial_number: 'S-006', type: 'thermal',
  manufacturer: 'FLIR', model: 'Vue', status: 'active',
}

function mockMount(overrides = {}) {
  const base = {
    sensor: () => HttpResponse.json(SENSOR),
    stats: () => HttpResponse.json({ total_flights: 5, total_hours: 3, unique_pilots: 2 }),
    flights: () => HttpResponse.json([]),
    maintenance: () => HttpResponse.json([]),
    documents: () => HttpResponse.json([]),
    ...overrides,
  }
  server.use(
    http.get('/api/sensors/:id/stats', base.stats),
    http.get('/api/sensors/:id/flights', base.flights),
    http.get('/api/sensors/:id', base.sensor),
    http.get('/api/maintenance', base.maintenance),
    http.get('/api/documents', base.documents),
  )
}

const render = () => renderRoute(<SensorDetailPage />, { path: '/fleet/sensors/:id', route: '/fleet/sensors/6', role: 'admin' })

describe('SensorDetailPage', () => {
  it('renders without crashing', async () => {
    mockMount()
    render()
    expect(await screen.findByRole('heading', { name: 'Thermal Cam' })).toBeInTheDocument()
  })

  it('renders key entity fields and stats from a populated payload', async () => {
    mockMount()
    render()
    expect(await screen.findByText('S/N: S-006')).toBeInTheDocument()
    expect(screen.getByText('Type: thermal')).toBeInTheDocument()
    expect(screen.getByText('FLIR')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()  // total flights stat
  })

  it('shows empty states when collections are empty', async () => {
    mockMount()
    render()
    expect(await screen.findByText('No flights recorded for this sensor')).toBeInTheDocument()
    expect(screen.getByText('No maintenance records')).toBeInTheDocument()
  })

  it('shows the not-found fallback when the sensor 500s', async () => {
    mockMount({ sensor: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }) })
    render()
    expect(await screen.findByText('Sensor not found')).toBeInTheDocument()
  })

  it('hides the edit control for a non-admin (supervisor)', async () => {
    server.use(http.get('/api/auth/me', () => HttpResponse.json({ id: 2, username: 'sup', role: 'supervisor' })))
    mockMount()
    renderRoute(<SensorDetailPage />, { path: '/fleet/sensors/:id', route: '/fleet/sensors/6', role: 'supervisor' })
    await screen.findByRole('heading', { name: 'Thermal Cam' })
    // Documents upload is intentionally visible for pilot+ roles; the page's
    // own (unnamed icon) edit control must not render for a supervisor.
    const buttons = screen.getAllByRole('button')
    expect(buttons).toHaveLength(1)
    expect(buttons[0]).toHaveAccessibleName(/Upload/)
  })
})
