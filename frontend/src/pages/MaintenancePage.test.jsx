import { describe, it, expect } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import MaintenancePage from './MaintenancePage'

// Mount endpoints. Entity-list effect:
//   GET /vehicles /batteries /controllers /docks /pilots
// loadAll() (MSW ignores query strings, so all three /maintenance* requests
// match a single handler unless given distinct paths):
//   GET /maintenance?upcoming=true   -> http.get('/api/maintenance')
//   GET /maintenance                 -> http.get('/api/maintenance')
//   GET /maintenance/schedules?all=true -> http.get('/api/maintenance/schedules')
const VEHICLES = [
  { id: 1, nickname: 'Falcon', model: 'Mavic 3', serial_number: 'SN-001', status: 'active' },
  { id: 9, nickname: 'OldBird', model: 'Mavic 2', serial_number: 'SN-OLD', status: 'retired' },
]

const HISTORY = [
  { id: 10, entity_type: 'vehicle', entity_id: 1, maintenance_type: 'scheduled', description: 'Prop swap', performed_by: 'Jane', performed_date: '2026-05-01' },
]
const UPCOMING = [
  { id: 20, entity_type: 'vehicle', entity_id: 1, maintenance_type: 'inspection', description: 'Annual inspection', next_due_date: '2026-07-01' },
]
const SCHEDULES = [
  { id: 30, name: 'Monthly check', entity_type: 'vehicle', entity_id: 1, frequency: 'monthly', is_active: true, next_due: '2026-07-01' },
]

function mockMount(overrides = {}) {
  const base = {
    vehicles: () => HttpResponse.json(VEHICLES),
    batteries: () => HttpResponse.json([]),
    controllers: () => HttpResponse.json([]),
    docks: () => HttpResponse.json([]),
    otherEquipment: () => HttpResponse.json([]),
    pilots: () => HttpResponse.json([{ id: 5, full_name: 'Jane Doe', is_active: true }]),
    // Returns upcoming when ?upcoming=true present, else history.
    maintenance: ({ request }) =>
      HttpResponse.json(new URL(request.url).searchParams.get('upcoming') ? UPCOMING : HISTORY),
    schedules: () => HttpResponse.json(SCHEDULES),
    ...overrides,
  }
  server.use(
    http.get('/api/vehicles', base.vehicles),
    http.get('/api/batteries', base.batteries),
    http.get('/api/controllers', base.controllers),
    http.get('/api/docks', base.docks),
    http.get('/api/other-equipment', base.otherEquipment),
    http.get('/api/pilots', base.pilots),
    http.get('/api/maintenance/schedules', base.schedules),
    http.get('/api/maintenance', base.maintenance),
  )
}

describe('MaintenancePage', () => {
  it('renders without crashing', async () => {
    mockMount()
    renderWithProviders(<MaintenancePage />, { role: 'admin' })
    expect(await screen.findByRole('heading', { name: 'Upcoming' })).toBeInTheDocument()
  })

  it('renders upcoming, history, and schedule rows from populated payloads', async () => {
    mockMount()
    renderWithProviders(<MaintenancePage />, { role: 'admin' })

    expect(await screen.findByText('Annual inspection')).toBeInTheDocument()  // upcoming
    expect(screen.getByText('Prop swap')).toBeInTheDocument()                 // history
    expect(screen.getByText('Monthly check')).toBeInTheDocument()            // schedule
  })

  it('resolves the entity nickname in the schedules table', async () => {
    mockMount()
    renderWithProviders(<MaintenancePage />, { role: 'admin' })

    await screen.findByText('Monthly check')
    // Upcoming card, history row, and schedules row all resolve to the nickname
    expect(screen.getAllByText('Falcon')).toHaveLength(3)
    expect(screen.queryByText(/vehicle #1\b/i)).toBeNull()
  })

  it('excludes retired entities from the Add Maintenance and Add Schedule dropdowns', async () => {
    mockMount()
    const { user } = renderWithProviders(<MaintenancePage />, { role: 'admin' })

    await screen.findByText('Prop swap')
    await user.click(screen.getByRole('button', { name: /Add Maintenance/ }))
    await screen.findByRole('heading', { name: 'Add Maintenance' })
    let entitySelect = screen.getByLabelText('Entity')
    expect(entitySelect).toHaveTextContent('Falcon')
    expect(entitySelect).not.toHaveTextContent('OldBird')
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    await user.click(screen.getByRole('button', { name: /Add Schedule \/ Task/ }))
    await screen.findByRole('heading', { name: 'Add Schedule / Task' })
    entitySelect = screen.getByLabelText('Entity')
    await waitFor(() => expect(entitySelect).toHaveTextContent('Falcon'))
    expect(entitySelect).not.toHaveTextContent('OldBird')
  })

  it('shows the empty states when all collections are empty', async () => {
    mockMount({
      maintenance: () => HttpResponse.json([]),
      schedules: () => HttpResponse.json([]),
    })
    renderWithProviders(<MaintenancePage />, { role: 'admin' })

    expect(await screen.findByText('No upcoming maintenance')).toBeInTheDocument()
    expect(screen.getByText('No maintenance records found')).toBeInTheDocument()
    expect(screen.getByText('No maintenance schedules found')).toBeInTheDocument()
  })

  it('falls back to empty UI when the maintenance endpoints 500', async () => {
    // loadAll swallows failures per-promise with .catch(() => []).
    mockMount({
      maintenance: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      schedules: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }),
    })
    renderWithProviders(<MaintenancePage />, { role: 'admin' })

    expect(await screen.findByText('No upcoming maintenance')).toBeInTheDocument()
    expect(screen.getByText('No maintenance records found')).toBeInTheDocument()
  })

  it('filters records via the search box', async () => {
    mockMount()
    const { user } = renderWithProviders(<MaintenancePage />, { role: 'admin' })

    await screen.findByText('Prop swap')
    await user.type(screen.getByPlaceholderText('Search maintenance...'), 'Annual')

    expect(screen.getByText('Annual inspection')).toBeInTheDocument()
    expect(screen.queryByText('Prop swap')).toBeNull()
  })

  it('shows Add Schedule for a supervisor but hides it for a pilot', async () => {
    mockMount()
    const { unmount } = renderWithProviders(<MaintenancePage />, { role: 'supervisor' })
    expect(await screen.findByRole('button', { name: /Add Schedule/ })).toBeInTheDocument()
    unmount()

    server.use(http.get('/api/auth/me', () => HttpResponse.json({ id: 7, username: 'pilot', role: 'pilot' })))
    mockMount()
    renderWithProviders(<MaintenancePage />, { role: 'pilot' })
    await screen.findByText('Monthly check')
    expect(screen.queryByRole('button', { name: /Add Schedule/ })).toBeNull()
  })

  it('opens the Add Maintenance modal from the toolbar (pilot+)', async () => {
    mockMount()
    const { user } = renderWithProviders(<MaintenancePage />, { role: 'admin' })

    await screen.findByText('Prop swap')
    await user.click(screen.getByRole('button', { name: /Add Maintenance/ }))
    expect(await screen.findByRole('heading', { name: 'Add Maintenance' })).toBeInTheDocument()
  })

  it('offers Other and Organization-wide as entity types in the Add Maintenance modal', async () => {
    mockMount()
    const { user } = renderWithProviders(<MaintenancePage />, { role: 'admin' })

    await screen.findByText('Prop swap')
    await user.click(screen.getByRole('button', { name: /Add Maintenance/ }))
    await screen.findByRole('heading', { name: 'Add Maintenance' })

    const entityType = screen.getByLabelText('Entity Type')
    expect(entityType).toContainHTML('<option value="other">Other</option>')
    expect(entityType).toContainHTML('<option value="organization">Organization-wide</option>')

    // "other" is backed by the other_equipment table: an enabled picker
    // with an optional "No specific item" choice for legacy-style records.
    await user.selectOptions(entityType, 'other')
    const entitySelect = screen.getByLabelText('Entity')
    expect(entitySelect).toBeEnabled()
    expect(entitySelect).toContainHTML('<option value="">No specific item</option>')

    await user.selectOptions(entityType, 'organization')
    expect(screen.getByLabelText('Entity')).toBeDisabled()
    expect(screen.getByLabelText('Entity')).toHaveValue('All')
  })

  it('opens the Add Schedule / Task modal from the toolbar with one-time support', async () => {
    mockMount()
    const { user } = renderWithProviders(<MaintenancePage />, { role: 'admin' })

    await screen.findByText('Monthly check')
    await user.click(screen.getByRole('button', { name: /Add Schedule \/ Task/ }))
    expect(await screen.findByRole('heading', { name: 'Add Schedule / Task' })).toBeInTheDocument()

    const frequency = screen.getByLabelText('Frequency')
    expect(frequency).toContainHTML('<option value="one_time">One-time task</option>')

    // Selecting one-time makes the due date required
    await user.selectOptions(frequency, 'one_time')
    expect(screen.getByLabelText('Due Date *')).toBeRequired()
  })

  it('sends the new entity when editing a record to a different type', async () => {
    let patched = null
    mockMount({ batteries: () => HttpResponse.json([{ id: 2, nickname: 'Batt A', serial_number: 'B-001' }]) })
    server.use(http.patch('/api/maintenance/:id', async ({ request, params }) => {
      patched = { id: params.id, body: await request.json() }
      return HttpResponse.json({ ok: true })
    }))
    const { user } = renderWithProviders(<MaintenancePage />, { role: 'admin' })

    await screen.findByText('Prop swap')
    await user.click(screen.getAllByTitle('Edit')[0])
    await screen.findByRole('heading', { name: 'Edit Maintenance' })

    await user.selectOptions(screen.getByLabelText('Entity Type'), 'battery')
    await user.selectOptions(screen.getByLabelText('Entity'), '2')
    await user.click(screen.getByRole('button', { name: 'Update' }))

    await waitFor(() => expect(patched).not.toBeNull())
    expect(patched.id).toBe('10')
    expect(patched.body.entity_type).toBe('battery')
    expect(patched.body.entity_id).toBe(2)
  })

  it('blocks submitting an edit with a changed type but no entity selected', async () => {
    let patchHit = false
    mockMount({ batteries: () => HttpResponse.json([{ id: 2, nickname: 'Batt A', serial_number: 'B-001' }]) })
    server.use(http.patch('/api/maintenance/:id', () => { patchHit = true; return HttpResponse.json({ ok: true }) }))
    const { user } = renderWithProviders(<MaintenancePage />, { role: 'admin' })

    await screen.findByText('Prop swap')
    await user.click(screen.getAllByTitle('Edit')[0])
    await screen.findByRole('heading', { name: 'Edit Maintenance' })

    await user.selectOptions(screen.getByLabelText('Entity Type'), 'battery')
    await user.click(screen.getByRole('button', { name: 'Update' }))

    expect(await screen.findByText('Please select a battery.')).toBeInTheDocument()
    expect(patchHit).toBe(false)
  })

  it('opens the documents modal from a history row paperclip', async () => {
    mockMount()
    server.use(http.get('/api/documents', () => HttpResponse.json([])))
    const { user } = renderWithProviders(<MaintenancePage />, { role: 'admin' })

    await screen.findByText('Prop swap')
    await user.click(screen.getAllByTitle('Documents')[0])
    expect(await screen.findByText('No documents uploaded')).toBeInTheDocument()
  })
})
