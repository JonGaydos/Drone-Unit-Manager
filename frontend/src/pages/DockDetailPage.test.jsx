import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderRoute } from '@/test/render'
import DockDetailPage from './DockDetailPage'

// Route param: :id. Mount endpoints:
//   GET /docks/:id                (primary; failure -> "Dock not found")
//   GET /maintenance?entity_type=dock&entity_id=:id
//   GET /documents?...            (DocumentUpload)
const DOCK = {
  id: 2, name: 'Rooftop Dock', serial_number: 'D-002',
  location_name: 'HQ Roof', lat: 40.1234, lon: -74.5678, status: 'online',
}

function mockMount(overrides = {}) {
  const base = {
    dock: () => HttpResponse.json(DOCK),
    maintenance: () => HttpResponse.json([]),
    documents: () => HttpResponse.json([]),
    ...overrides,
  }
  server.use(
    http.get('/api/docks/:id', base.dock),
    http.get('/api/maintenance', base.maintenance),
    http.get('/api/documents', base.documents),
  )
}

const render = () => renderRoute(<DockDetailPage />, { path: '/fleet/docks/:id', route: '/fleet/docks/2', role: 'admin' })

describe('DockDetailPage', () => {
  it('renders without crashing', async () => {
    mockMount()
    render()
    expect(await screen.findByRole('heading', { name: 'Rooftop Dock' })).toBeInTheDocument()
  })

  it('renders key entity fields and the location section', async () => {
    mockMount()
    render()
    expect(await screen.findByText('S/N: D-002')).toBeInTheDocument()
    expect(screen.getByText('HQ Roof')).toBeInTheDocument()
    // Map section renders when coords are valid.
    expect(screen.getByRole('heading', { name: 'Location' })).toBeInTheDocument()
  })

  it('omits the map and shows the empty maintenance state without coords', async () => {
    mockMount({ dock: () => HttpResponse.json({ ...DOCK, lat: null, lon: null }) })
    render()
    expect(await screen.findByText('No maintenance records')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Location' })).toBeNull()
  })

  it('shows the not-found fallback when the dock 500s', async () => {
    mockMount({ dock: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }) })
    render()
    expect(await screen.findByText('Dock not found')).toBeInTheDocument()
  })

  it('hides the edit control for a non-admin (supervisor)', async () => {
    server.use(http.get('/api/auth/me', () => HttpResponse.json({ id: 2, username: 'sup', role: 'supervisor' })))
    mockMount()
    renderRoute(<DockDetailPage />, { path: '/fleet/docks/:id', route: '/fleet/docks/2', role: 'supervisor' })
    await screen.findByRole('heading', { name: 'Rooftop Dock' })
    // Documents upload is intentionally visible for pilot+ roles; the page's
    // own (unnamed icon) edit control must not render for a supervisor.
    const buttons = screen.getAllByRole('button')
    expect(buttons).toHaveLength(1)
    expect(buttons[0]).toHaveAccessibleName(/Upload/)
  })
})
