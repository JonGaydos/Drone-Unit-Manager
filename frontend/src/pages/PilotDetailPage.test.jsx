import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
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
})
