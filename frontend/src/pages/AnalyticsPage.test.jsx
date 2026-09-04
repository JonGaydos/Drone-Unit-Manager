import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import AnalyticsPage from './AnalyticsPage'

// Mount endpoints (Promise.all; whole chain .catch -> swallowed):
//   GET /dashboard/analytics/flights-by-purpose
//   GET /dashboard/analytics/flights-by-year
//   GET /dashboard/analytics/flights-by-pilot
//   GET /dashboard/analytics/avg-duration-by-year
//   GET /dashboard/analytics/monthly-flights
//   GET /dashboard/analytics/vehicle-hours
//   GET /dashboard/analytics/pilot-hours
//   GET /flights?per_page=1000&page=1  (paginated envelope or array)
// recharts ResponsiveContainer is globally stubbed (data-testid="recharts-stub").
// Cross-filter is client-side: clicking a pilot row in the leaderboard sets a
// filter chip — no refetch.

function mockMount(overrides = {}) {
  const base = {
    purpose: () => HttpResponse.json([{ purpose: 'Patrol', count: 12 }]),
    year: () => HttpResponse.json([{ year: 2025, count: 12 }]),
    pilot: () => HttpResponse.json([{ pilot_id: 1, pilot_name: 'Jane Doe', count: 12, percentage: 100 }]),
    avg: () => HttpResponse.json([{ year: 2025, avg_seconds: 600 }]),
    monthly: () => HttpResponse.json([{ year: 2025, month: 6, count: 5 }]),
    vehicle: () => HttpResponse.json([{ vehicle_name: 'X10-A', hours: 8.5 }]),
    pilotHours: () => HttpResponse.json([{ pilot_id: 1, pilot_name: 'Jane Doe', hours: 8.5, flight_count: 12 }]),
    flights: () => HttpResponse.json({ flights: [{ id: 1, pilot_id: 1, pilot_name: 'Jane Doe', purpose: 'Patrol', date: '2025-06-01', duration_seconds: 600 }], total_pages: 1 }),
    ...overrides,
  }
  server.use(
    http.get('/api/dashboard/analytics/flights-by-purpose', base.purpose),
    http.get('/api/dashboard/analytics/flights-by-year', base.year),
    http.get('/api/dashboard/analytics/flights-by-pilot', base.pilot),
    http.get('/api/dashboard/analytics/avg-duration-by-year', base.avg),
    http.get('/api/dashboard/analytics/monthly-flights', base.monthly),
    http.get('/api/dashboard/analytics/vehicle-hours', base.vehicle),
    http.get('/api/dashboard/analytics/pilot-hours', base.pilotHours),
    http.get('/api/flights', base.flights),
  )
}

describe('AnalyticsPage', () => {
  it('renders without crashing under the recharts stub', async () => {
    mockMount()
    renderWithProviders(<AnalyticsPage />, { role: 'admin' })
    expect(await screen.findByText('All Time Flights by Purpose')).toBeInTheDocument()
    expect(screen.getAllByTestId('recharts-stub').length).toBeGreaterThan(0)
  })

  it('renders real content from a populated payload', async () => {
    mockMount()
    renderWithProviders(<AnalyticsPage />, { role: 'admin' })
    // Pilot leaderboard table (real DOM, not chart internals).
    expect(await screen.findByText('Pilot Hours Leaderboard')).toBeInTheDocument()
    expect(screen.getByText('Jane Doe')).toBeInTheDocument()
    expect(screen.getByText('8.5')).toBeInTheDocument()
  })

  it('shows the leaderboard empty state when there is no flight data', async () => {
    mockMount({
      purpose: () => HttpResponse.json([]),
      year: () => HttpResponse.json([]),
      pilot: () => HttpResponse.json([]),
      avg: () => HttpResponse.json([]),
      monthly: () => HttpResponse.json([]),
      vehicle: () => HttpResponse.json([]),
      pilotHours: () => HttpResponse.json([]),
      flights: () => HttpResponse.json({ flights: [], total_pages: 1 }),
    })
    renderWithProviders(<AnalyticsPage />, { role: 'admin' })
    expect(await screen.findByText('No flight data yet')).toBeInTheDocument()
  })

  it('renders chart chrome when a primary endpoint 500s (errors swallowed)', async () => {
    // The whole Promise.all is wrapped in .catch(()=>{}), so a 500 leaves the
    // page in its empty-but-rendered state rather than crashing.
    mockMount({ purpose: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }) })
    renderWithProviders(<AnalyticsPage />, { role: 'admin' })
    expect(await screen.findByText('Pilot Hours Leaderboard')).toBeInTheDocument()
    expect(screen.getByText('No flight data yet')).toBeInTheDocument()
  })

  it('applies a cross-filter chip when a leaderboard pilot row is clicked', async () => {
    mockMount()
    const { user } = renderWithProviders(<AnalyticsPage />, { role: 'admin' })
    await screen.findByText('Pilot Hours Leaderboard')

    await user.click(screen.getByText('Jane Doe'))
    // The active-filter bar shows a pilot chip.
    expect(await screen.findByText(/Pilot: Jane Doe/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Clear Filters' })).toBeInTheDocument()
  })
})
