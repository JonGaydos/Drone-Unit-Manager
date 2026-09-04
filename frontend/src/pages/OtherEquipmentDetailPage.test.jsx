import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderRoute } from '@/test/render'
import OtherEquipmentDetailPage from './OtherEquipmentDetailPage'

// Route param: :id. Mount endpoints:
//   GET /other-equipment/:id      (primary; failure -> "Equipment item not found")
//   GET /maintenance?entity_type=other&entity_id=:id
//   GET /documents?...            (DocumentUpload)
const ITEM = {
  id: 4, name: 'Pelican case', category: 'case', serial_number: 'PC-004',
  status: 'active', acquired_date: '2024-02-10', decommissioned_date: null, notes: 'Foam cut for X10',
}

function mockMount(overrides = {}) {
  const base = {
    item: () => HttpResponse.json(ITEM),
    maintenance: () => HttpResponse.json([]),
    documents: () => HttpResponse.json([]),
    ...overrides,
  }
  server.use(
    http.get('/api/other-equipment/:id', base.item),
    http.get('/api/maintenance', base.maintenance),
    http.get('/api/documents', base.documents),
  )
}

const render = () => renderRoute(<OtherEquipmentDetailPage />, { path: '/fleet/other/:id', route: '/fleet/other/4', role: 'admin' })

describe('OtherEquipmentDetailPage', () => {
  it('renders without crashing', async () => {
    mockMount()
    render()
    expect(await screen.findByRole('heading', { name: 'Pelican case' })).toBeInTheDocument()
  })

  it('renders category, serial, lifecycle dates, and notes', async () => {
    mockMount()
    render()
    expect(await screen.findByText('Category: case')).toBeInTheDocument()
    expect(screen.getByText('S/N: PC-004')).toBeInTheDocument()
    expect(screen.getByText('Acquired: 2024-02-10')).toBeInTheDocument()
    expect(screen.getByText('Foam cut for X10')).toBeInTheDocument()
  })

  it('shows the maintenance empty state', async () => {
    mockMount()
    render()
    expect(await screen.findByText('No maintenance records')).toBeInTheDocument()
  })

  it('shows the not-found fallback when the item 500s', async () => {
    mockMount({ item: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }) })
    render()
    expect(await screen.findByText('Equipment item not found')).toBeInTheDocument()
  })

  it('hides the edit control for a non-admin (supervisor)', async () => {
    server.use(http.get('/api/auth/me', () => HttpResponse.json({ id: 2, username: 'sup', role: 'supervisor' })))
    mockMount()
    renderRoute(<OtherEquipmentDetailPage />, { path: '/fleet/other/:id', route: '/fleet/other/4', role: 'supervisor' })
    await screen.findByRole('heading', { name: 'Pelican case' })
    // Documents upload is intentionally visible for pilot+ roles; the page's
    // own (unnamed icon) edit control must not render for a supervisor.
    const buttons = screen.getAllByRole('button')
    expect(buttons).toHaveLength(1)
    expect(buttons[0]).toHaveAccessibleName(/Upload/)
  })
})
