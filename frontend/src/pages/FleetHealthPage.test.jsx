import { describe, it, expect } from 'vitest'
import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import FleetHealthPage from './FleetHealthPage'

// Single mount endpoint: GET /dashboard/analytics/fleet-health.
const PRIMARY = '/api/dashboard/analytics/fleet-health'

const POPULATED = {
  summary: {
    total_vehicles: 4, total_batteries: 12, avg_battery_health: 87,
    total_overdue_maintenance: 1, total_flight_hours: 156,
  },
  vehicles: [
    { id: 1, name: 'Skydio X10', serial: 'SX10-001', flights: 40, hours: 22, last_flight: '2026-06-01', overdue_maintenance: 0 },
    { id: 2, name: 'Mavic 3', serial: 'MAV3-002', flights: 12, hours: 8, last_flight: '2026-05-20', overdue_maintenance: 2 },
  ],
  batteries: [
    { id: 1, nickname: 'Batt A', serial: 'B-001', health_pct: 91 },
    { id: 2, nickname: 'Batt B', serial: 'B-002', health_pct: 44 },
  ],
}

describe('FleetHealthPage', () => {
  it('renders without crashing', async () => {
    server.use(http.get(PRIMARY, () => HttpResponse.json({ summary: { total_vehicles: 0, total_batteries: 0, avg_battery_health: 0, total_overdue_maintenance: 0, total_flight_hours: 0 }, vehicles: [], batteries: [] })))
    renderWithProviders(<FleetHealthPage />, { role: 'admin' })
    expect(await screen.findByRole('heading', { name: 'Fleet Health' })).toBeInTheDocument()
  })

  it('renders summary cards and the vehicle table from a populated payload', async () => {
    server.use(http.get(PRIMARY, () => HttpResponse.json(POPULATED)))
    renderWithProviders(<FleetHealthPage />, { role: 'admin' })

    expect(await screen.findByText('Skydio X10')).toBeInTheDocument()
    expect(screen.getByText('Mavic 3')).toBeInTheDocument()
    // Summary card values.
    expect(screen.getByText('87%')).toBeInTheDocument()
    expect(screen.getByText('156h')).toBeInTheDocument()
    // Overdue badge for the second vehicle.
    expect(screen.getByText('2 overdue')).toBeInTheDocument()
    // Battery chart section header (batteries present).
    expect(screen.getByText('Battery Health')).toBeInTheDocument()
  })

  it('shows the empty vehicle-table state when there are no vehicles', async () => {
    server.use(http.get(PRIMARY, () => HttpResponse.json({
      summary: { total_vehicles: 0, total_batteries: 0, avg_battery_health: 0, total_overdue_maintenance: 0, total_flight_hours: 0 },
      vehicles: [], batteries: [],
    })))
    renderWithProviders(<FleetHealthPage />, { role: 'admin' })

    expect(await screen.findByText('No active vehicles')).toBeInTheDocument()
    // No battery chart when there are no batteries.
    expect(screen.queryByText('Battery Health')).toBeNull()
  })

  it('shows the failure fallback when the primary endpoint 500s', async () => {
    server.use(http.get(PRIMARY, () => HttpResponse.json({ detail: 'boom' }, { status: 500 })))
    renderWithProviders(<FleetHealthPage />, { role: 'admin' })

    expect(await screen.findByText('Failed to load fleet health data')).toBeInTheDocument()
  })

  it('sorts the vehicle table when a column header is clicked', async () => {
    server.use(http.get(PRIMARY, () => HttpResponse.json(POPULATED)))
    const { user } = renderWithProviders(<FleetHealthPage />, { role: 'admin' })

    await screen.findByText('Skydio X10')
    // Default sort is by name asc: Mavic 3 before Skydio X10.
    let rows = within(screen.getByRole('table')).getAllByRole('row')
    expect(within(rows[1]).getByText('Mavic 3')).toBeInTheDocument()

    // Sort by flights asc: Mavic 3 (12) still before Skydio X10 (40); toggle desc.
    await user.click(screen.getByText(/^Flights/))
    await user.click(screen.getByText(/^Flights/))
    rows = within(screen.getByRole('table')).getAllByRole('row')
    expect(within(rows[1]).getByText('Skydio X10')).toBeInTheDocument()
  })
})
