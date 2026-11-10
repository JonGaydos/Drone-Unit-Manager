import { describe, it, expect } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { fleetOptions, pilotOption, vehicleOption } from '@/test/options'
import { renderWithProviders } from '@/test/render'
import MissionLogPage from './MissionLogPage'

// Mount endpoints (Promise.all in load()):
//   GET /mission-logs?...        (array)
//   GET /pilots /vehicles
//   GET /settings/mission_purposes  -> { value } (.catch -> { value: '' })
const MISSIONS = [
  { id: 1, date: '2026-05-01', title: 'River Search', reason: 'Search', location: 'River', man_hours: 4, status: 'completed', vehicle_id: 2, vehicle_name: 'Falcon', pilots: [{ id: 11, pilot_id: 5, pilot_name: 'Jane Doe', role: 'PIC', hours: 4 }] },
  { id: 2, date: '2026-05-02', title: 'Night Patrol', reason: 'Patrol', location: 'Downtown', man_hours: 2, status: 'planned', pilots: [] },
]

function mockMount(overrides = {}) {
  const base = {
    missions: () => HttpResponse.json(MISSIONS),
    ...overrides,
  }
  server.use(
    http.get('/api/mission-logs', base.missions),
    http.get('/api/pilots/options', () => HttpResponse.json([pilotOption(5, 'Jane Doe')])),
    http.get('/api/fleet/options', () => HttpResponse.json(fleetOptions({ vehicles: [vehicleOption({ id: 2, nickname: 'Falcon', model: 'Mavic 3' })] }))),
    http.get('/api/settings/mission_purposes', () => HttpResponse.json({ value: '' })),
  )
}

describe('MissionLogPage', () => {
  it('renders without crashing', async () => {
    mockMount()
    renderWithProviders(<MissionLogPage />, { role: 'admin' })
    expect(await screen.findByText('River Search')).toBeInTheDocument()
  })

  it('loads and renders mission rows from a populated payload', async () => {
    mockMount()
    renderWithProviders(<MissionLogPage />, { role: 'admin' })
    expect(await screen.findByText('River Search')).toBeInTheDocument()
    expect(screen.getByText('Night Patrol')).toBeInTheDocument()
  })

  it('shows the empty state when there are no missions', async () => {
    mockMount({ missions: () => HttpResponse.json([]) })
    renderWithProviders(<MissionLogPage />, { role: 'admin' })
    expect(await screen.findByText('No mission logs found')).toBeInTheDocument()
  })

  it('shows the error banner when the primary endpoint 500s', async () => {
    mockMount({ missions: () => HttpResponse.json({ detail: 'missions boom' }, { status: 500 }) })
    renderWithProviders(<MissionLogPage />, { role: 'admin' })
    expect(await screen.findByText('missions boom')).toBeInTheDocument()
  })

  it('searches on the server so older missions are reachable', async () => {
    mockMount({
      missions: ({ request }) => {
        const q = (new URL(request.url).searchParams.get('search') || '').toLowerCase()
        return HttpResponse.json(MISSIONS.filter(m => m.title.toLowerCase().includes(q)))
      },
    })
    const { user } = renderWithProviders(<MissionLogPage />, { role: 'admin' })

    await screen.findByText('River Search')
    await user.type(screen.getByPlaceholderText('Search missions...'), 'Night')

    await waitFor(() => expect(screen.queryByText('River Search')).toBeNull())
    expect(screen.getByText('Night Patrol')).toBeInTheDocument()
  })

  it('says when the list is cut off at the page size', async () => {
    const many = Array.from({ length: 200 }, (_, i) => ({ ...MISSIONS[1], id: i + 1, title: `Mission ${i}` }))
    mockMount({ missions: () => HttpResponse.json(many) })
    renderWithProviders(<MissionLogPage />, { role: 'admin' })
    expect(await screen.findByText(/Showing the 200 most recent matches/)).toBeInTheDocument()
  }, 15000)

  it('lists inactive pilots under their own heading in the filter', async () => {
    mockMount()
    server.use(http.get('/api/pilots/options', () => HttpResponse.json([
      pilotOption(5, 'Jane Doe'),
      pilotOption(6, 'Old Timer', { status: 'inactive' }),
    ])))
    const { container } = renderWithProviders(<MissionLogPage />, { role: 'admin' })
    await screen.findByText('River Search')
    const group = container.querySelector('optgroup[label="Inactive"]')
    expect(within(group).getByText('Old Timer')).toBeInTheDocument()
    expect(within(group).queryByText('Jane Doe')).toBeNull()
  })

  it('offers delete on the own roster log only at own, and hides Import from a pilot', async () => {
    mockMount()
    server.use(http.get('/api/mission-logs', () => HttpResponse.json([
      { id: 1, title: 'Mine', date: '2026-01-01', status: 'completed', created_by_id: null, pilots: [{ pilot_id: 5, pilot_name: 'Jane Doe' }] },
      { id: 2, title: 'Theirs', date: '2026-01-02', status: 'completed', created_by_id: 99, pilots: [] },
    ])))
    renderWithProviders(<MissionLogPage />, { user: { id: 3, username: 'p', role: 'pilot', pilot_id: 5 } })
    await screen.findByText('Mine')
    expect(screen.getAllByRole('button', { name: 'Delete' })).toHaveLength(1)
    expect(screen.queryByRole('button', { name: /Import/ })).toBeNull()
  })

  // E-14: a native select is as wide as its longest option, so one very long
  // pilot name pushed the page sideways. The filter selects are capped and
  // clip their text.
  it('caps the width of the filter selects (E-14)', async () => {
    mockMount()
    renderWithProviders(<MissionLogPage />, { role: 'admin' })
    await screen.findByText('River Search')
    const filters = [...document.querySelectorAll('select')].filter(s => /^All /.test(s.options[0]?.text || ''))
    expect(filters.length).toBeGreaterThan(0)
    for (const select of filters) {
      expect(select).toHaveClass('max-w-64', 'truncate')
    }
  })
})
