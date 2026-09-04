import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderRoute } from '@/test/render'
import ControllerDetailPage from './ControllerDetailPage'

// Route param: :id. Mount endpoints:
//   GET /controllers/:id          (primary; failure -> "Controller not found")
//   GET /maintenance?entity_type=controller&entity_id=:id
//   GET /pilots
//   GET /documents?...            (DocumentUpload)
const CONTROLLER = {
  id: 3, nickname: 'RC Pro', serial_number: 'C-003', manufacturer: 'DJI',
  model: 'RC Plus', status: 'active', assigned_pilot_id: 5,
}

function mockMount(overrides = {}) {
  const base = {
    controller: () => HttpResponse.json(CONTROLLER),
    maintenance: () => HttpResponse.json([]),
    pilots: () => HttpResponse.json([{ id: 5, full_name: 'Jane Doe' }]),
    documents: () => HttpResponse.json([]),
    ...overrides,
  }
  server.use(
    http.get('/api/controllers/:id', base.controller),
    http.get('/api/maintenance', base.maintenance),
    http.get('/api/pilots', base.pilots),
    http.get('/api/documents', base.documents),
  )
}

const render = () => renderRoute(<ControllerDetailPage />, { path: '/fleet/controllers/:id', route: '/fleet/controllers/3', role: 'admin' })

describe('ControllerDetailPage', () => {
  it('renders without crashing', async () => {
    mockMount()
    render()
    expect(await screen.findByRole('heading', { name: 'RC Pro' })).toBeInTheDocument()
  })

  it('renders key entity fields and the assigned pilot', async () => {
    mockMount()
    render()
    expect(await screen.findByText('S/N: C-003')).toBeInTheDocument()
    expect(screen.getByText('DJI')).toBeInTheDocument()
    expect(screen.getByText('RC Plus')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Jane Doe' }).length).toBeGreaterThan(0)
  })

  it('shows the empty maintenance state', async () => {
    mockMount()
    render()
    expect(await screen.findByText('No maintenance records')).toBeInTheDocument()
  })

  it('shows the not-found fallback when the controller 500s', async () => {
    mockMount({ controller: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }) })
    render()
    expect(await screen.findByText('Controller not found')).toBeInTheDocument()
  })

  it('hides the edit control for a non-admin (supervisor)', async () => {
    server.use(http.get('/api/auth/me', () => HttpResponse.json({ id: 2, username: 'sup', role: 'supervisor' })))
    mockMount()
    renderRoute(<ControllerDetailPage />, { path: '/fleet/controllers/:id', route: '/fleet/controllers/3', role: 'supervisor' })
    await screen.findByRole('heading', { name: 'RC Pro' })
    // Documents upload is intentionally visible for pilot+ roles; the page's
    // own (unnamed icon) edit control must not render for a supervisor.
    const buttons = screen.getAllByRole('button')
    expect(buttons).toHaveLength(1)
    expect(buttons[0]).toHaveAccessibleName(/Upload/)
  })
})
