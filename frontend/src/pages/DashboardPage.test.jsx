import { describe, it, expect } from 'vitest'
import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import DashboardPage from './DashboardPage'

// All endpoints DashboardPage fetches on mount. The weather briefing is fired
// AFTER the first Promise.all batch (its URL depends on resolved org location);
// with empty settings that resolves to the White House fallback, so we match
// /weather/briefing with a wildcard query.
function mockDashboard({
  stats, trends, flights, maintenance, compliance,
  topPilots, topVehicles, activity, locations, pilots, settings, weather,
} = {}) {
  server.use(
    http.get('/api/dashboard/stats', () => HttpResponse.json(stats ?? null)),
    http.get('/api/dashboard/trends', () => HttpResponse.json(trends ?? null)),
    http.get('/api/flights', () => HttpResponse.json(flights ?? [])),
    http.get('/api/maintenance', () => HttpResponse.json(maintenance ?? [])),
    http.get('/api/dashboard/compliance', () => HttpResponse.json(compliance ?? null)),
    http.get('/api/dashboard/top-pilots-30d', () => HttpResponse.json(topPilots ?? [])),
    http.get('/api/dashboard/top-vehicles-30d', () => HttpResponse.json(topVehicles ?? [])),
    http.get('/api/dashboard/activity-by-month', () => HttpResponse.json(activity ?? [])),
    http.get('/api/vehicles/locations', () => HttpResponse.json(locations ?? [])),
    http.get('/api/pilots', () => HttpResponse.json(pilots ?? [])),
    http.get('/api/settings', () => HttpResponse.json(settings ?? [])),
    http.get('/api/weather/briefing', () => HttpResponse.json(weather ?? null)),
  )
}

// A fully-populated payload set. Crucially includes OBJECT-VALUED nested fields
// (weather.station, weather.coordinates, weather.advisory, compliance object)
// to exercise the React #31 production crash where an object was rendered raw.
const POPULATED = {
  stats: {
    total_flights: 412, total_flight_hours: 88.5, active_pilots: 7,
    fleet_size: 9, flights_needing_review: 3,
  },
  trends: {
    current: { flights: 40, hours: '12.5h' },
    deltas_pct: { flights: 12, hours: -4, active_pilots: 0, active_vehicles: 5 },
  },
  flights: [
    { id: 101, external_id: 'FLT-ABCDEF12', pilot_name: 'Jane Pilot', vehicle_name: 'Skydio X10', purpose: 'Patrol', duration_seconds: 1200 },
    { id: 102, external_id: null, pilot_name: 'Bob Pilot', vehicle_name: 'Mavic 3', purpose: 'Survey', duration_seconds: 600 },
  ],
  maintenance: [
    { id: 1, description: 'Prop replacement', next_due: '2026-07-01' },
  ],
  compliance: {
    compliance_score: 92, pilots_current: 6, total_pilots: 7,
    currency_rules_active: 1, expired_certifications: 0, overdue_maintenance: 1,
    pilots_lapsed: 1,
    operating_authorities_tracked: 1, expired_authorities: [], expiring_authorities: [],
    score_cap_reason: null,
    pilot_currency_status: [
      { pilot_id: 5, pilot_name: 'Lapsed Larry', is_current: false, earliest_expires_date: null },
    ],
    expiring_certifications: [
      { pilot_id: 9, days_remaining: 12 },
    ],
  },
  topPilots: [{ pilot_id: 5, pilot_name: 'Top Tom', hours: 33 }],
  topVehicles: [{ vehicle_id: 2, label: 'Skydio X10', hours: 27 }],
  activity: [{ label: '2026-05', flights: 30, hours: 10 }],
  locations: [{ vehicle_id: 2, label: 'Skydio X10', location_text: 'North' }],
  pilots: [{ id: 7, first_name: 'Active', last_name: 'Annie', status: 'active' }],
  settings: [],
  // Object-valued nested fields — the regression bait.
  weather: {
    station: { name: 'KDCA', id: 'KDCA' },
    coordinates: { lat: 38.8977, lon: -77.0365 },
    advisory: { status: 'GO', reason: 'Clear skies' },
    wind_kts: 6, visibility_sm: 10, ceiling_ft: 12000,
  },
}

describe('DashboardPage', () => {
  it('renders without crashing under providers + MSW', async () => {
    mockDashboard({})
    renderWithProviders(<DashboardPage />, { role: 'admin' })
    // Hero greeting always renders once loading resolves.
    expect(await screen.findByText(/Good (morning|afternoon|evening)/)).toBeInTheDocument()
  })

  it('renders populated tiles as text', async () => {
    mockDashboard(POPULATED)
    renderWithProviders(<DashboardPage />, { role: 'admin' })

    // Hero compliance summary.
    expect(await screen.findByText(/6 of 7 pilots current/)).toBeInTheDocument()
    // Stat tiles.
    expect(screen.getByText('Flights (30d)')).toBeInTheDocument()
    expect(screen.getByText('Active Pilots')).toBeInTheDocument()
    // Recent flights list rendered.
    expect(screen.getByText('Jane Pilot')).toBeInTheDocument()
    // Weather tile object fields rendered as scalars.
    expect(screen.getByText('KDCA')).toBeInTheDocument()
    expect(screen.getByText('GO')).toBeInTheDocument()
    expect(screen.getByText('6kt')).toBeInTheDocument()
    // Operating authority clause appears once the unit tracks any.
    expect(screen.getByText(/authority current/)).toBeInTheDocument()
  })

  it('surfaces the compliance score cap reason on the hero tile', async () => {
    mockDashboard({
      ...POPULATED,
      compliance: {
        ...POPULATED.compliance,
        compliance_score: 50,
        score_cap_reason: 'Capped at 50: 1 operating authority expired',
        expired_authorities: [{ id: 1, title: 'Blanket public safety COA', grounds_unit: true }],
      },
    })
    renderWithProviders(<DashboardPage />, { role: 'admin' })

    expect(await screen.findByText('Capped at 50: 1 operating authority expired')).toBeInTheDocument()
    expect(screen.getByText(/1 expired authority/)).toBeInTheDocument()
  })

  // HEADLINE: React #31 regression guard. A fully-populated payload that
  // includes object-valued fields must not crash and must never render the
  // literal "[object Object]" string into the DOM.
  it('does NOT render [object Object] when payloads include nested objects (React #31 regression)', async () => {
    mockDashboard(POPULATED)
    renderWithProviders(<DashboardPage />, { role: 'admin' })

    // Wait for content to settle (weather is the last async fetch).
    expect(await screen.findByText('KDCA')).toBeInTheDocument()

    // The crash signature: an object stringified into JSX.
    expect(screen.queryByText('[object Object]')).toBeNull()
    expect(document.body.textContent).not.toContain('[object Object]')

    // Key tiles are present as text, proving the page mounted fully.
    expect(screen.getByText(/Recent Flights/)).toBeInTheDocument()
    expect(screen.getByText('Weather')).toBeInTheDocument()
    expect(screen.getByText('Currency Risk')).toBeInTheDocument()
    expect(screen.getByText('Activity by Month')).toBeInTheDocument()
  })

  it('shows empty-state copy when every payload is empty', async () => {
    mockDashboard({})
    renderWithProviders(<DashboardPage />, { role: 'admin' })

    // Recent flights empty state.
    expect(await screen.findByText('No recent flights')).toBeInTheDocument()
    // Weather tile unavailable fallback (weather resolved to null).
    expect(screen.getByText('Weather widget unavailable')).toBeInTheDocument()
    // Leaderboards empty.
    expect(screen.getAllByText('No flight activity').length).toBeGreaterThan(0)
  })

  it('survives a 500 on the primary stats endpoint (errors are swallowed, page still renders)', async () => {
    mockDashboard({})
    server.use(http.get('/api/dashboard/stats', () =>
      HttpResponse.json({ detail: 'boom' }, { status: 500 })))

    renderWithProviders(<DashboardPage />, { role: 'admin' })

    // Page still renders its hero rather than crashing to a blank screen.
    expect(await screen.findByText(/Good (morning|afternoon|evening)/)).toBeInTheDocument()
    // Stat tile falls back to its default value.
    const flightsTile = screen.getByText('Flights (30d)').closest('div')
    expect(within(flightsTile).getByText('0')).toBeInTheDocument()
  })
})
