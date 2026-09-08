import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import WeatherPage from './WeatherPage'

// Mount: GET /settings -> resolveOrgLocation -> GET /weather/briefing?lat&lon.
// LocationPickerMap renders under the react-leaflet stub. recharts charts use
// the stubbed ResponsiveContainer. Both mount fetches .catch -> swallowed.
// Location-driven fetch: submitting "lat, lon" calls /weather/briefing again.

const SETTINGS = [
  { key: 'org_default_lat', value: '38.8977' },
  { key: 'org_default_lon', value: '-77.0365' },
  { key: 'org_location_name', value: 'HQ' },
]

const BRIEFING = {
  advisory: { status: 'go', reasons: ['Winds calm'] },
  local_weather: { wind_speed_mph: 5, temperature_f: 70, humidity_pct: 40, weather_code: 0 },
  metar: { visibility_miles: 10, ceiling_ft: 5000, flight_category: 'VFR' },
  forecast: [{ time: '2026-06-15T12:00:00Z', wind_mph: 5, gusts_mph: 8, temp_f: 70, precip_prob: 10, cloud_cover: 20 }],
}

function mockMount(overrides = {}) {
  const base = {
    settings: () => HttpResponse.json(SETTINGS),
    briefing: () => HttpResponse.json(BRIEFING),
    ...overrides,
  }
  server.use(
    http.get('/api/settings', base.settings),
    http.get('/api/weather/briefing', base.briefing),
  )
}

// Mount with the org settings and a briefing handler that records the lat,lon
// it was queried for. Extra handlers (e.g. /api/geocode) are appended. Returns
// the array the briefing handler pushes "lat,lon" strings into.
function mockBriefingRecorder(extra = []) {
  const requested = []
  server.use(
    http.get('/api/settings', () => HttpResponse.json(SETTINGS)),
    http.get('/api/weather/briefing', ({ request }) => {
      const u = new URL(request.url)
      requested.push(`${u.searchParams.get('lat')},${u.searchParams.get('lon')}`)
      return HttpResponse.json(BRIEFING)
    }),
    ...extra,
  )
  return requested
}

describe('WeatherPage', () => {
  it('renders without crashing', async () => {
    mockMount()
    renderWithProviders(<WeatherPage />, { role: 'admin' })
    expect(await screen.findByText('Pre-Flight Weather Briefing')).toBeInTheDocument()
  })

  it('loads the org-default briefing and renders the advisory + conditions', async () => {
    mockMount()
    renderWithProviders(<WeatherPage />, { role: 'admin' })
    expect(await screen.findByText('GO')).toBeInTheDocument()
    expect(screen.getByText('Winds calm')).toBeInTheDocument()
    expect(screen.getByText('Current Conditions')).toBeInTheDocument()
  })

  it('shows the empty prompt when the org briefing is null', async () => {
    mockMount({ briefing: () => HttpResponse.json(null) })
    renderWithProviders(<WeatherPage />, { role: 'admin' })
    expect(await screen.findByText(/Enter coordinates or use your GPS/)).toBeInTheDocument()
  })

  it('shows the empty prompt when the briefing endpoint 500s (error swallowed)', async () => {
    mockMount({ briefing: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }) })
    renderWithProviders(<WeatherPage />, { role: 'admin' })
    expect(await screen.findByText(/Enter coordinates or use your GPS/)).toBeInTheDocument()
  })

  it('fetches a new briefing for typed coordinates on submit', async () => {
    const requested = mockBriefingRecorder()
    const { user } = renderWithProviders(<WeatherPage />, { role: 'admin' })
    await screen.findByText('GO')

    const input = screen.getByLabelText('Coordinates or Address')
    await user.clear(input)
    await user.type(input, '40.7128, -74.0060')
    await user.click(screen.getByRole('button', { name: /Check Weather/ }))

    await screen.findByText('GO')
    expect(requested.some(r => r.startsWith('40.7128,-74.006'))).toBe(true)
  })

  it('geocodes a typed address, then fetches the briefing for the result', async () => {
    let geocodedFor = null
    const requested = mockBriefingRecorder([
      http.get('/api/geocode', ({ request }) => {
        geocodedFor = new URL(request.url).searchParams.get('q')
        return HttpResponse.json({ lat: 30.371, lon: -86.203, display_name: 'Freeport, FL 32439' })
      }),
    ])
    const { user } = renderWithProviders(<WeatherPage />, { role: 'admin' })
    await screen.findByText('GO')

    const input = screen.getByLabelText('Coordinates or Address')
    await user.clear(input)
    await user.type(input, 'Freeport FL 32439')
    await user.click(screen.getByRole('button', { name: /Check Weather/ }))

    await screen.findByText('GO')
    expect(geocodedFor).toBe('Freeport FL 32439')
    expect(requested.some(r => r.startsWith('30.371,-86.203'))).toBe(true)
    // the resolved address replaces what was typed
    expect(screen.getByLabelText('Coordinates or Address')).toHaveValue('Freeport, FL 32439')
  })
})
