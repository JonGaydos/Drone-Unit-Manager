import { describe, it, expect, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import AnalyticsPage from './AnalyticsPage'

// jsdom cannot lay charts out, so BarChart and YAxis are replaced with stubs
// that expose what the page hands them: each bar chart's data, and each
// category axis's interval and rendered tick labels.
let chartData = []
vi.mock('recharts', async (orig) => {
  const actual = await orig()
  return {
    ...actual,
    ResponsiveContainer: ({ children }) => <div>{children}</div>,
    BarChart: ({ data, children }) => {
      chartData = data || []
      return <div data-testid="bar-chart" data-chart={JSON.stringify(data)}>{children}</div>
    },
    YAxis: ({ dataKey, interval, tick }) => {
      if (!dataKey) return null
      return (
        <svg data-testid={`yaxis-${dataKey}`} data-interval={String(interval)}>
          {chartData.map((d, i) => (
            <g key={i}>{typeof tick === 'function' ? tick({ x: 0, y: 0, payload: { value: d[dataKey] } }) : <text>{d[dataKey]}</text>}</g>
          ))}
        </svg>
      )
    },
    Bar: () => null,
    XAxis: () => null,
    CartesianGrid: () => null,
    Tooltip: () => null,
  }
})

const FLIGHTS = [
  { id: 1, pilot_id: 1, pilot_name: 'Jane Doe', vehicle_id: 2, vehicle_name: 'Unit-u4vf', purpose: 'Patrol', date: '2024-06-01', duration_seconds: 3600 },
  { id: 2, pilot_id: 1, pilot_name: 'Jane Doe', vehicle_id: 3, vehicle_name: 'Unit-9n84', purpose: 'Patrol', date: '2024-06-02', duration_seconds: 1800 },
  { id: 3, pilot_id: 2, pilot_name: 'Sam Roe', vehicle_id: 2, vehicle_name: 'Unit-u4vf', purpose: 'Patrol', date: '2024-06-03', duration_seconds: 7200 },
]

function mockMount({ purposes, vehicles } = {}) {
  server.use(
    http.get('/api/dashboard/analytics/flights-by-purpose', () => HttpResponse.json(purposes ?? [{ purpose: 'Patrol', count: 3 }])),
    http.get('/api/dashboard/analytics/flights-by-year', () => HttpResponse.json([{ year: 2024, count: 3 }])),
    http.get('/api/dashboard/analytics/flights-by-pilot', () => HttpResponse.json([])),
    http.get('/api/dashboard/analytics/avg-duration-by-year', () => HttpResponse.json([])),
    http.get('/api/dashboard/analytics/monthly-flights', () => HttpResponse.json([])),
    http.get('/api/dashboard/analytics/vehicle-hours', () => HttpResponse.json(vehicles ?? [
      { vehicle_id: 2, vehicle_name: 'Skydio X2E (Unit-u4vf)', hours: 3 },
      { vehicle_id: 3, vehicle_name: 'Skydio X2E (Unit-9n84)', hours: 0.5 },
    ])),
    http.get('/api/dashboard/analytics/pilot-hours', () => HttpResponse.json([
      { pilot_id: 1, pilot_name: 'Jane Doe', hours: 1.5, flight_count: 2 },
      { pilot_id: 2, pilot_name: 'Sam Roe', hours: 2, flight_count: 1 },
    ])),
    http.get('/api/flights', () => HttpResponse.json({ flights: FLIGHTS, total_pages: 1 })),
  )
}

const vehicleChart = () => JSON.parse(
  screen.getAllByTestId('bar-chart').find(el => el.dataset.chart.includes('vehicle_id')).dataset.chart)

describe('AnalyticsPage charts', () => {
  it('sums filtered vehicle hours by vehicle id, not by a differently built name (E-4)', async () => {
    mockMount()
    const { user } = renderWithProviders(<AnalyticsPage />, { role: 'admin' })
    await screen.findByText('Pilot Hours Leaderboard')

    await user.click(screen.getByText('Jane Doe'))
    await screen.findByRole('button', { name: 'Clear Filters' })
    const rows = vehicleChart()
    expect(rows.map(r => [r.vehicle_id, r.filtered])).toEqual([[2, 1], [3, 0.5]])
  })

  // E-5: multi-word purposes wrapped onto several lines and overlapped. Each
  // tick is one line, cut with an ellipsis when long, full text in a tooltip.
  it('draws each purpose label on one line (E-5)', async () => {
    mockMount({ purposes: [
      { purpose: 'Other Agency Assist', count: 3 },
      { purpose: 'A purpose name far too long for the axis', count: 1 },
    ] })
    renderWithProviders(<AnalyticsPage />, { role: 'admin' })
    const axis = await screen.findByTestId('yaxis-purpose')
    const texts = [...axis.querySelectorAll('text')]
    expect(texts.map(t => t.querySelector('tspan'))).toEqual([null, null])
    expect(texts[0].lastChild.textContent).toBe('Other Agency Assist')
    expect(texts[1].lastChild.textContent).toMatch(/…$/)
    expect(texts[1].querySelector('title').textContent).toBe('A purpose name far too long for the axis')
  })

  // E-6: Recharts hid every other vehicle label; interval 0 shows them all.
  it('labels every vehicle bar (E-6)', async () => {
    mockMount()
    renderWithProviders(<AnalyticsPage />, { role: 'admin' })
    const axis = await screen.findByTestId('yaxis-vehicle_name')
    expect(axis.dataset.interval).toBe('0')
    expect([...axis.querySelectorAll('text')].map(t => t.lastChild.textContent))
      .toEqual(['Skydio X2E (Unit-u4vf)', 'Skydio X2E (Unit-9n84)'])
  })
})

