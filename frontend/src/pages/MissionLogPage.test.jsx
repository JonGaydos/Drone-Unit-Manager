import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
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

  it('narrows the visible rows with the search box', async () => {
    mockMount()
    const { user } = renderWithProviders(<MissionLogPage />, { role: 'admin' })

    await screen.findByText('River Search')
    await user.type(screen.getByPlaceholderText('Search missions...'), 'Night')

    expect(screen.queryByText('River Search')).toBeNull()
    expect(screen.getByText('Night Patrol')).toBeInTheDocument()
  })
})
