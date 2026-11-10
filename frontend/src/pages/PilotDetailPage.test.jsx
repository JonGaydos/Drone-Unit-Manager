import { describe, it, expect } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderRoute } from '@/test/render'
import PilotDetailPage from './PilotDetailPage'

// Route param: :id. Mount endpoints (Promise.all + a folders prefetch):
//   GET /folders
//   GET /pilots/:id                 (primary; failure -> "Pilot not found")
//   GET /pilots/:id/stats
//   GET /flights?pilot_id=:id
//   GET /pilot-certifications?pilot_id=:id      (.catch -> [])
//   GET /currency/status/:id                    (.catch -> null)
//   GET /dashboard/analytics/pilot-performance/:id (.catch -> null)
//   GET /pilots/:id/needs-attention             (.catch -> null)
//   GET /documents?...              (DocumentUpload)
const PILOT = {
  id: 7, first_name: 'Ada', last_name: 'Lovelace', full_name: 'Ada Lovelace',
  email: 'ada@unit.gov', badge_number: 'A-1', status: 'active',
}

function mockMount(overrides = {}) {
  const base = {
    pilot: () => HttpResponse.json(PILOT),
    stats: () => HttpResponse.json({ total_flights: 12, total_flight_hours: 3, avg_flight_duration_seconds: 600 }),
    flights: () => HttpResponse.json({ flights: [] }),
    certs: () => HttpResponse.json([]),
    currency: () => HttpResponse.json(null),
    performance: () => HttpResponse.json(null),
    needsAttention: () => HttpResponse.json({ items: [] }),
    folders: () => HttpResponse.json([]),
    documents: () => HttpResponse.json([]),
    ...overrides,
  }
  server.use(
    http.get('/api/pilots/:id/stats', base.stats),
    http.get('/api/pilots/:id/needs-attention', base.needsAttention),
    http.get('/api/pilots/:id', base.pilot),
    http.get('/api/flights', base.flights),
    http.get('/api/pilot-certifications', base.certs),
    http.get('/api/currency/status/:id', base.currency),
    http.get('/api/dashboard/analytics/pilot-performance/:id', base.performance),
    http.get('/api/folders', base.folders),
    http.get('/api/documents', base.documents),
  )
}

const render = (role = 'admin') =>
  renderRoute(<PilotDetailPage />, { path: '/pilots/:id', route: '/pilots/7', role })

describe('PilotDetailPage', () => {
  it('renders without crashing', async () => {
    mockMount()
    render()
    expect(await screen.findByRole('heading', { name: 'Ada Lovelace' })).toBeInTheDocument()
  })

  it('renders profile fields and stats from a populated payload', async () => {
    mockMount()
    render()
    expect(await screen.findByRole('heading', { name: 'Ada Lovelace' })).toBeInTheDocument()
    expect(screen.getByText('ada@unit.gov')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()    // total flights stat
    expect(screen.getByText('Badge: A-1')).toBeInTheDocument()
  })

  it('shows empty states for flights and certifications', async () => {
    mockMount()
    render()
    expect(await screen.findByText('No flights yet')).toBeInTheDocument()
    expect(screen.getByText('No certifications assigned')).toBeInTheDocument()
    // needs-attention empty -> all clear message
    expect(screen.getByText(/All clear/)).toBeInTheDocument()
  })

  it('renders needs-attention items without rendering raw objects', async () => {
    mockMount({
      needsAttention: () => HttpResponse.json({
        items: [
          { level: 'red', text: 'Part 107 expired' },
          { level: 'amber', text: 'Night currency lapses in 10 days' },
        ],
      }),
    })
    render()
    expect(await screen.findByText('Part 107 expired')).toBeInTheDocument()
    expect(screen.getByText('Night currency lapses in 10 days')).toBeInTheDocument()
    expect(screen.queryByText(/\[object Object\]/)).toBeNull()
  })

  it('shows the not-found fallback when the pilot 500s', async () => {
    mockMount({ pilot: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }) })
    render()
    expect(await screen.findByText('Pilot not found')).toBeInTheDocument()
  })

  it('lets a pilot edit and attach documents to their own record, without Status', async () => {
    mockMount()
    const me = { id: 3, username: 'ada', role: 'pilot', pilot_id: 7 }
    const { user } = renderRoute(<PilotDetailPage />, { path: '/pilots/:id', route: '/pilots/7', user: me })
    await screen.findByRole('heading', { name: 'Ada Lovelace' })
    expect(screen.getByRole('button', { name: 'Upload' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Edit profile' }))
    expect(screen.getByLabelText('Email')).toBeInTheDocument()
    expect(screen.queryByLabelText('Status')).toBeNull()
  })

  it("does not offer a pilot Upload or Edit on another pilot's record", async () => {
    mockMount()
    const me = { id: 4, username: 'sam', role: 'pilot', pilot_id: 9 }
    renderRoute(<PilotDetailPage />, { path: '/pilots/:id', route: '/pilots/7', user: me })
    await screen.findByRole('heading', { name: 'Ada Lovelace' })
    expect(screen.queryByRole('button', { name: 'Upload' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Edit profile' })).toBeNull()
  })

  it('keeps the page when /stats is refused', async () => {
    mockMount({ stats: () => HttpResponse.json({ detail: 'no' }, { status: 403 }) })
    render()
    expect(await screen.findByRole('heading', { name: 'Ada Lovelace' })).toBeInTheDocument()
  })

  it('does not ask for stats or flights with flights.view off', async () => {
    const asked = []
    mockMount({
      stats: () => { asked.push('stats'); return HttpResponse.json({}) },
      flights: () => { asked.push('flights'); return HttpResponse.json({ flights: [] }) },
    })
    renderRoute(<PilotDetailPage />, {
      path: '/pilots/:id', route: '/pilots/7', role: 'pilot', permissions: { 'flights.view': 'no' },
    })
    expect(await screen.findByRole('heading', { name: 'Ada Lovelace' })).toBeInTheDocument()
    expect(asked).toEqual([])
  })

  it('without pilots.contacts, hides the contact inputs and leaves them out of the save', async () => {
    let body = null
    mockMount()
    server.use(http.patch('/api/pilots/:id', async ({ request }) => { body = await request.json(); return HttpResponse.json(PILOT) }))
    const { user } = renderRoute(<PilotDetailPage />, {
      path: '/pilots/:id', route: '/pilots/7', user: { id: 3, username: 'ada', role: 'pilot', pilot_id: 7 },
      permissions: { 'pilots.contacts': 'no' },
    })
    await screen.findByRole('heading', { name: 'Ada Lovelace' })
    await user.click(screen.getByRole('button', { name: 'Edit profile' }))
    expect(screen.queryByLabelText('Email')).toBeNull()
    await user.click(screen.getByRole('button', { name: /^Save/ }))
    await waitFor(() => expect(body).not.toBeNull())
    for (const field of ['email', 'phone', 'phone_type', 'phone_work']) {
      expect(body).not.toHaveProperty(field)
    }
  })

  it('refuses to save a blank first or last name', async () => {
    let patched = false
    mockMount()
    server.use(http.patch('/api/pilots/:id', () => { patched = true; return HttpResponse.json(PILOT) }))
    const { user } = render()
    await screen.findByRole('heading', { name: 'Ada Lovelace' })
    await user.click(screen.getByRole('button', { name: 'Edit profile' }))
    expect(screen.getByLabelText('First Name *')).toBeRequired()
    await user.clear(screen.getByLabelText('First Name *'))
    await user.type(screen.getByLabelText('First Name *'), '   ')
    await user.click(screen.getByRole('button', { name: /^Save/ }))
    expect(await screen.findByText('Required: First Name')).toBeInTheDocument()
    expect(patched).toBe(false)
  })

  describe('performance tiles', () => {
    const PERFORMANCE = {
      total_flights: 4, total_flight_hours: 2, avg_duration_min: 30, vehicles_flown: 1,
      training_hours: 5, mission_hours: 6, incidents: 2, flights_by_month: [], flights_by_purpose: [],
    }

    it('shows the log and incident tiles when the values are present', async () => {
      mockMount({ performance: () => HttpResponse.json(PERFORMANCE) })
      render()
      expect(await screen.findByText('Training Hours')).toBeInTheDocument()
      expect(screen.getByText('5h')).toBeInTheDocument()
      expect(screen.getByText('Mission Hours')).toBeInTheDocument()
      expect(screen.getByText('Incidents')).toBeInTheDocument()
    })

    it('shows one set of flight total cards', async () => {
      mockMount({ performance: () => HttpResponse.json(PERFORMANCE) })
      render()
      expect(await screen.findByText('Training Hours')).toBeInTheDocument()
      for (const label of ['Total Flights', 'Flight Hours', 'Avg Duration']) {
        expect(screen.getAllByText(label)).toHaveLength(1)
      }
    })

    it('shows a zero value rather than hiding the tile', async () => {
      mockMount({ performance: () => HttpResponse.json({ ...PERFORMANCE, training_hours: 0, incidents: 0 }) })
      render()
      expect(await screen.findByText('0h')).toBeInTheDocument()
      expect(screen.getByText('Incidents')).toBeInTheDocument()
    })

    it('hides the tiles whose view is off', async () => {
      mockMount({
        performance: () => HttpResponse.json({ ...PERFORMANCE, training_hours: null, mission_hours: null, incidents: null }),
      })
      render()
      expect((await screen.findAllByText('Avg Duration')).length).toBeGreaterThan(0)
      expect(screen.queryByText('Training Hours')).toBeNull()
      expect(screen.queryByText('Mission Hours')).toBeNull()
      expect(screen.queryByText('Incidents')).toBeNull()
      expect(screen.queryByText('nullh')).toBeNull()
    })
  })

  it('stays rendered with the pilot when secondary requests 500', async () => {
    const boom = () => HttpResponse.json({ detail: 'boom' }, { status: 500 })
    mockMount({ stats: boom, flights: boom, certs: boom, currency: boom, performance: boom, needsAttention: boom, folders: boom })
    render()
    expect(await screen.findByRole('heading', { name: 'Ada Lovelace' })).toBeInTheDocument()
    expect(screen.queryByText('Pilot not found')).toBeNull()
  })

  it('loads the profile photo with the session token and shows it from a blob URL', async () => {
    let auth = null
    mockMount({ pilot: () => HttpResponse.json({ ...PILOT, photo_url: '/api/pilots/7/photo/view' }) })
    server.use(http.get('/api/pilots/7/photo/view', ({ request }) => {
      auth = request.headers.get('Authorization')
      return new HttpResponse(new Uint8Array([0x89, 0x50, 0x4e, 0x47]), { headers: { 'Content-Type': 'image/png' } })
    }))
    render()
    const img = await screen.findByRole('img', { name: 'Ada Lovelace' })
    expect(img.getAttribute('src')).toMatch(/^blob:/)
    expect(auth).toBe('Bearer test-token')
  })
})
