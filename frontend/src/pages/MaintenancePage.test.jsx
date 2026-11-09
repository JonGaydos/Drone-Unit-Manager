import { describe, it, expect } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { withPermissions } from '@/test/permissions'
import { fleetOptions, pilotOption, serialOption, vehicleOption } from '@/test/options'
import { renderWithProviders } from '@/test/render'
import { addDays, todayLocal } from '@/lib/utils'
import MaintenancePage from './MaintenancePage'

// Mount endpoints. Entity-list effect:
//   GET /fleet/options /pilots/options
// loadAll() (MSW ignores query strings, so all three /maintenance* requests
// match a single handler unless given distinct paths):
//   GET /maintenance?upcoming=true   -> http.get('/api/maintenance')
//   GET /maintenance                 -> http.get('/api/maintenance')
//   GET /maintenance/schedules?all=true -> http.get('/api/maintenance/schedules')
const VEHICLES = [
  vehicleOption({ id: 1, nickname: 'Falcon', model: 'Mavic 3', serialNumber: 'SN-001' }),
  vehicleOption({ id: 9, nickname: 'OldBird', model: 'Mavic 2', serialNumber: 'SN-OLD', status: 'retired' }),
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
    vehicles: VEHICLES,
    batteries: [],
    pilots: () => HttpResponse.json([pilotOption(5, 'Jane Doe')]),
    // Returns upcoming when ?upcoming=true present, else history.
    maintenance: ({ request }) =>
      HttpResponse.json(new URL(request.url).searchParams.get('upcoming') ? UPCOMING : HISTORY),
    schedules: () => HttpResponse.json(SCHEDULES),
    ...overrides,
  }
  server.use(
    http.get('/api/fleet/options', () => HttpResponse.json(fleetOptions({ vehicles: base.vehicles, batteries: base.batteries }))),
    http.get('/api/pilots/options', base.pilots),
    http.get('/api/maintenance/schedules', base.schedules),
    http.get('/api/maintenance', base.maintenance),
  )
}

describe('MaintenancePage', () => {
  it('marks a task due today as due today, and one due yesterday as overdue', async () => {
    mockMount({
      maintenance: ({ request }) => HttpResponse.json(new URL(request.url).searchParams.get('upcoming')
        ? [{ ...UPCOMING[0], next_due_date: todayLocal() }] : HISTORY),
      schedules: () => HttpResponse.json([{ ...SCHEDULES[0], next_due: addDays(todayLocal(), -1) }]),
    })
    renderWithProviders(<MaintenancePage />, { role: 'admin' })
    expect(await screen.findByText('(Due today)')).toBeInTheDocument()
    expect(await screen.findByText('(Overdue)')).toBeInTheDocument()
  })

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

  // The record form is the shared Modal: a named dialog that closes on Escape.
  it('opens the record form as a named dialog that closes on Escape', async () => {
    mockMount()
    const { user } = renderWithProviders(<MaintenancePage />, { role: 'admin' })

    await screen.findByText('Prop swap')
    await user.click(screen.getByRole('button', { name: /Add Maintenance/ }))
    expect(await screen.findByRole('dialog', { name: 'Add Maintenance' })).toBeInTheDocument()
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
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

    server.use(http.get('/api/auth/me', () => HttpResponse.json(withPermissions({ id: 7, username: 'pilot', role: 'pilot' }))))
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
    mockMount({ batteries: [serialOption(2, 'Batt A', 'B-001')] })
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
    mockMount({ batteries: [serialOption(2, 'Batt A', 'B-001')] })
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

  it('labels schedule picker rows without empty or repeated serials', async () => {
    mockMount({ batteries: [serialOption(2, 'Batt A', 'B-001'), serialOption(3, 'B-002')] })
    server.use(http.get('/api/fleet/options', () => HttpResponse.json(fleetOptions({
      batteries: [serialOption(2, 'Batt A', 'B-001'), serialOption(3, 'B-002')],
      controllers: [{ id: 4, name: 'Pad', status: 'active' }],
    }))))
    const { user } = renderWithProviders(<MaintenancePage />, { role: 'admin' })
    await user.click(await screen.findByRole('button', { name: /Add Schedule \/ Task/ }))
    await screen.findByRole('heading', { name: 'Add Schedule / Task' })
    const type = screen.getByLabelText(/Type/)
    await user.selectOptions(type, 'battery')
    expect(await screen.findByRole('option', { name: 'Batt A (B-001)' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'B-002' })).toBeInTheDocument()
    await user.selectOptions(type, 'controller')
    expect(await screen.findByRole('option', { name: 'Pad' })).toBeInTheDocument()
  })

  it('marks Description required and names it when left blank', async () => {
    mockMount()
    let posted = false
    server.use(http.post('/api/maintenance', () => { posted = true; return HttpResponse.json({}) }))
    const { user } = renderWithProviders(<MaintenancePage />, { role: 'admin' })
    await screen.findByText('Prop swap')
    await user.click(screen.getByRole('button', { name: /Add Maintenance/ }))
    const dialog = await screen.findByRole('dialog', { name: 'Add Maintenance' })
    const description = within(dialog).getByLabelText('Description *')
    expect(description).toBeRequired()
    await user.selectOptions(within(dialog).getByLabelText('Entity'), '1')
    await user.type(description, '   ')
    await user.click(within(dialog).getByRole('button', { name: 'Add Maintenance' }))
    expect(await within(dialog).findByText('Description is required.')).toBeInTheDocument()
    expect(posted).toBe(false)
  })
})
