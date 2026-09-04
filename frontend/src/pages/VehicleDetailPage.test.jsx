import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderRoute } from '@/test/render'
import VehicleDetailPage from './VehicleDetailPage'

// Route param: :id. Mount endpoints (see useEffect Promise.all + folders effect
// + DocumentUpload):
//   GET /folders
//   GET /vehicles/:id            (primary; failure -> "Vehicle not found")
//   GET /vehicles/:id/stats
//   GET /flights?vehicle_id=:id&per_page=50
//   GET /batteries /controllers /sensors /attachments
//   GET /maintenance?entity_type=vehicle&entity_id=:id
//   GET /vehicles/:id/registrations
//   GET /components?vehicle_id=:id
//   GET /documents?entity_type=vehicle&entity_id=:id   (DocumentUpload)
const VEHICLE = {
  id: 7, nickname: 'Falcon', manufacturer: 'DJI', model: 'Mavic 3',
  serial_number: 'SN-007', faa_registration: 'FA-123', status: 'active',
}

function mockMount(overrides = {}) {
  const base = {
    folders: () => HttpResponse.json([]),
    vehicle: () => HttpResponse.json(VEHICLE),
    stats: () => HttpResponse.json({ total_flights: 12, total_flight_hours: 4, last_flight_date: '2026-06-01' }),
    flights: () => HttpResponse.json({ flights: [] }),
    batteries: () => HttpResponse.json([]),
    controllers: () => HttpResponse.json([]),
    sensors: () => HttpResponse.json([]),
    attachments: () => HttpResponse.json([]),
    maintenance: () => HttpResponse.json([]),
    registrations: () => HttpResponse.json([]),
    components: () => HttpResponse.json([]),
    documents: () => HttpResponse.json([]),
    ...overrides,
  }
  server.use(
    http.get('/api/folders', base.folders),
    http.get('/api/vehicles/:id/stats', base.stats),
    http.get('/api/vehicles/:id/registrations', base.registrations),
    http.get('/api/vehicles/:id', base.vehicle),
    http.get('/api/flights', base.flights),
    http.get('/api/batteries', base.batteries),
    http.get('/api/controllers', base.controllers),
    http.get('/api/sensors', base.sensors),
    http.get('/api/attachments', base.attachments),
    http.get('/api/maintenance', base.maintenance),
    http.get('/api/components', base.components),
    http.get('/api/documents', base.documents),
  )
}

const render = () => renderRoute(<VehicleDetailPage />, { path: '/fleet/vehicles/:id', route: '/fleet/vehicles/7', role: 'admin' })

describe('VehicleDetailPage', () => {
  it('renders without crashing', async () => {
    mockMount()
    render()
    expect(await screen.findByRole('heading', { name: /DJI Mavic 3 \(Falcon\)/ })).toBeInTheDocument()
  })

  it('renders key entity fields and stats from a populated payload', async () => {
    mockMount({
      flights: () => HttpResponse.json({ flights: [
        { id: 1, date: '2026-06-01', pilot_id: 3, pilot_name: 'Jane', duration_seconds: 600, battery_serial: 'B-1' },
      ] }),
    })
    render()

    expect(await screen.findByText('S/N: SN-007')).toBeInTheDocument()
    expect(screen.getByText('FAA: FA-123')).toBeInTheDocument()
    // Stats row.
    expect(screen.getByText('12')).toBeInTheDocument()
    // Flight history row.
    expect(screen.getByRole('link', { name: '2026-06-01' })).toBeInTheDocument()
  })

  it('shows empty-state messages when collections are empty', async () => {
    mockMount()
    render()
    expect(await screen.findByText('No flights recorded')).toBeInTheDocument()
    expect(screen.getByText('No maintenance records')).toBeInTheDocument()
    expect(screen.getByText('No FAA registrations recorded')).toBeInTheDocument()
  })

  it('shows the not-found fallback when the vehicle 500s', async () => {
    mockMount({ vehicle: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }) })
    render()
    expect(await screen.findByText('Vehicle not found')).toBeInTheDocument()
  })

  it('hides the edit control for a non-admin (supervisor)', async () => {
    server.use(http.get('/api/auth/me', () => HttpResponse.json({ id: 2, username: 'sup', role: 'supervisor' })))
    mockMount()
    renderRoute(<VehicleDetailPage />, { path: '/fleet/vehicles/:id', route: '/fleet/vehicles/7', role: 'supervisor' })
    await screen.findByRole('heading', { name: /DJI Mavic 3 \(Falcon\)/ })
    expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull()
  })
})
