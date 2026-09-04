import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderRoute } from '@/test/render'
import BatteryDetailPage from './BatteryDetailPage'

// Route param: :id. Mount endpoints:
//   GET /batteries/:id            (primary; failure -> "Battery not found")
//   GET /batteries/:id/stats
//   GET /batteries/:id/flights
//   GET /maintenance?entity_type=battery&entity_id=:id
//   GET /vehicles
//   GET /batteries/:id/health-history
//   GET /batteries/:id/pilots
//   GET /documents?...           (DocumentUpload)
const BATTERY = {
  id: 4, nickname: 'Cell A', serial_number: 'B-004', manufacturer: 'DJI',
  model: 'TB30', vehicle_model: 'Mavic 3', cycle_count: 33, health_pct: 88, status: 'active',
}

function mockMount(overrides = {}) {
  const base = {
    battery: () => HttpResponse.json(BATTERY),
    stats: () => HttpResponse.json({ total_flights: 9, total_hours: 6 }),
    flights: () => HttpResponse.json([]),
    maintenance: () => HttpResponse.json([]),
    vehicles: () => HttpResponse.json([]),
    health: () => HttpResponse.json([]),
    pilots: () => HttpResponse.json([]),
    documents: () => HttpResponse.json([]),
    ...overrides,
  }
  server.use(
    http.get('/api/batteries/:id/stats', base.stats),
    http.get('/api/batteries/:id/flights', base.flights),
    http.get('/api/batteries/:id/health-history', base.health),
    http.get('/api/batteries/:id/pilots', base.pilots),
    http.get('/api/batteries/:id', base.battery),
    http.get('/api/maintenance', base.maintenance),
    http.get('/api/vehicles', base.vehicles),
    http.get('/api/documents', base.documents),
  )
}

const render = () => renderRoute(<BatteryDetailPage />, { path: '/fleet/batteries/:id', route: '/fleet/batteries/4', role: 'admin' })

describe('BatteryDetailPage', () => {
  it('renders without crashing', async () => {
    mockMount()
    render()
    expect(await screen.findByRole('heading', { name: 'Cell A' })).toBeInTheDocument()
  })

  it('renders key entity fields and stats from a populated payload', async () => {
    mockMount()
    render()
    expect(await screen.findByText('S/N: B-004')).toBeInTheDocument()
    expect(screen.getByText('33')).toBeInTheDocument()   // cycle count stat
    expect(screen.getByText('88%')).toBeInTheDocument()   // health stat
    expect(screen.getByText('Mavic 3')).toBeInTheDocument()  // linked vehicle model
  })

  it('shows empty states when collections are empty', async () => {
    mockMount()
    render()
    expect(await screen.findByText('No flights recorded for this battery')).toBeInTheDocument()
    expect(screen.getByText(/No health readings recorded yet/)).toBeInTheDocument()
  })

  it('shows the not-found fallback when the battery 500s', async () => {
    mockMount({ battery: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }) })
    render()
    expect(await screen.findByText('Battery not found')).toBeInTheDocument()
  })

  it('hides the edit control for a non-admin (supervisor)', async () => {
    server.use(http.get('/api/auth/me', () => HttpResponse.json({ id: 2, username: 'sup', role: 'supervisor' })))
    mockMount()
    renderRoute(<BatteryDetailPage />, { path: '/fleet/batteries/:id', route: '/fleet/batteries/4', role: 'supervisor' })
    await screen.findByRole('heading', { name: 'Cell A' })
    expect(screen.queryByText('Record Reading')).toBeNull()
  })
})
