import { describe, it, expect } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
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
    http.get('/api/pilots', () => HttpResponse.json([{ id: 5, full_name: 'Jane Doe', is_active: true }])),
    http.get('/api/vehicles', () => HttpResponse.json([{ id: 2, nickname: 'Falcon', model: 'Mavic 3' }])),
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
    server.use(http.get('/api/pilots', () => HttpResponse.json([
      { id: 5, full_name: 'Jane Doe', first_name: 'Jane', status: 'active' },
      { id: 6, full_name: 'Old Timer', first_name: 'Old', status: 'inactive' },
    ])))
    const { container } = renderWithProviders(<MissionLogPage />, { role: 'admin' })
    await screen.findByText('River Search')
    const group = container.querySelector('optgroup[label="Inactive"]')
    expect(within(group).getByText('Old Timer')).toBeInTheDocument()
    expect(within(group).queryByText('Jane Doe')).toBeNull()
  })
})
