import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderRoute } from '@/test/render'
import AttachmentDetailPage from './AttachmentDetailPage'

// Route param: :id. Mount endpoints:
//   GET /attachments/:id          (primary; failure -> "Attachment not found")
//   GET /attachments/:id/stats
//   GET /attachments/:id/flights
//   GET /maintenance?entity_type=attachment&entity_id=:id
//   GET /documents?...            (DocumentUpload)
const ATTACHMENT = {
  id: 8, name: 'Spotlight', serial_number: 'A-008', type: 'lighting',
  manufacturer: 'Lume', model: 'L1', status: 'active',
}

function mockMount(overrides = {}) {
  const base = {
    attachment: () => HttpResponse.json(ATTACHMENT),
    stats: () => HttpResponse.json({ total_flights: 7, total_hours: 4, unique_pilots: 3 }),
    flights: () => HttpResponse.json([]),
    maintenance: () => HttpResponse.json([]),
    documents: () => HttpResponse.json([]),
    ...overrides,
  }
  server.use(
    http.get('/api/attachments/:id/stats', base.stats),
    http.get('/api/attachments/:id/flights', base.flights),
    http.get('/api/attachments/:id', base.attachment),
    http.get('/api/maintenance', base.maintenance),
    http.get('/api/documents', base.documents),
  )
}

const render = () => renderRoute(<AttachmentDetailPage />, { path: '/fleet/attachments/:id', route: '/fleet/attachments/8', role: 'admin' })

describe('AttachmentDetailPage', () => {
  it('renders without crashing', async () => {
    mockMount()
    render()
    expect(await screen.findByRole('heading', { name: 'Spotlight' })).toBeInTheDocument()
  })

  it('renders key entity fields and stats from a populated payload', async () => {
    mockMount()
    render()
    expect(await screen.findByText('S/N: A-008')).toBeInTheDocument()
    expect(screen.getByText('Type: lighting')).toBeInTheDocument()
    expect(screen.getByText('Lume')).toBeInTheDocument()
    expect(screen.getByText('7')).toBeInTheDocument()  // total flights stat
  })

  it('shows empty states when collections are empty', async () => {
    mockMount()
    render()
    expect(await screen.findByText('No flights recorded for this attachment')).toBeInTheDocument()
    expect(screen.getByText('No maintenance records')).toBeInTheDocument()
  })

  it('shows the not-found fallback when the attachment 500s', async () => {
    mockMount({ attachment: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }) })
    render()
    expect(await screen.findByText('Attachment not found')).toBeInTheDocument()
  })

  it('hides the edit control for a non-admin (supervisor)', async () => {
    server.use(http.get('/api/auth/me', () => HttpResponse.json({ id: 2, username: 'sup', role: 'supervisor' })))
    mockMount()
    renderRoute(<AttachmentDetailPage />, { path: '/fleet/attachments/:id', route: '/fleet/attachments/8', role: 'supervisor' })
    await screen.findByRole('heading', { name: 'Spotlight' })
    // Documents upload is intentionally visible for pilot+ roles; the page's
    // own (unnamed icon) edit control must not render for a supervisor.
    const buttons = screen.getAllByRole('button')
    expect(buttons).toHaveLength(1)
    expect(buttons[0]).toHaveAccessibleName(/Upload/)
  })
})
