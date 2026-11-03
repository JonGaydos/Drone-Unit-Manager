import { describe, it, expect, vi, afterEach } from 'vitest'
import { screen, within, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import RolePermissionsGrid from './RolePermissionsGrid'

// Endpoints: GET /api/permissions, PUT /api/permissions, POST /api/permissions/reset.

const def = (key, feature, action, kind, requires = null, viewer_locked = false) => (
  { key, feature, action, kind, defaults: {}, viewer_locked, requires }
)
const REGISTRY = [
  def('flights.view', 'Flights', 'View', 'bool'),
  def('flights.create', 'Flights', 'Create', 'bool', 'flights.view', true),
  def('flights.edit', 'Flights', 'Edit', 'level', 'flights.view', true),
  def('fleet.view', 'Fleet equipment', 'View', 'bool'),
  def('fleet.manage', 'Fleet equipment', 'Manage', 'bool', 'fleet.view', true),
  def('checkouts.use', 'Equipment checkouts', 'Check out, check in', 'bool', 'fleet.view', true),
]
const VALUES = {
  admin: { 'flights.view': 'yes', 'flights.create': 'yes', 'flights.edit': 'all', 'fleet.view': 'yes', 'fleet.manage': 'yes', 'checkouts.use': 'yes' },
  supervisor: { 'flights.view': 'yes', 'flights.create': 'yes', 'flights.edit': 'all', 'fleet.view': 'yes', 'fleet.manage': 'yes', 'checkouts.use': 'yes' },
  pilot: { 'flights.view': 'yes', 'flights.create': 'yes', 'flights.edit': 'own', 'fleet.view': 'yes', 'fleet.manage': 'no', 'checkouts.use': 'yes' },
  viewer: { 'flights.view': 'yes', 'flights.create': 'no', 'flights.edit': 'none', 'fleet.view': 'yes', 'fleet.manage': 'no', 'checkouts.use': 'no' },
}
const PAYLOAD = { registry: REGISTRY, values: VALUES }

function setWide(wide) {
  globalThis.matchMedia = (query) => ({
    matches: wide, media: query, addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {},
  })
}

function mockGet(payload = PAYLOAD) {
  server.use(http.get('/api/permissions', () => HttpResponse.json(payload)))
}

async function renderGrid() {
  mockGet()
  const utils = renderWithProviders(<RolePermissionsGrid />, { role: 'admin' })
  await screen.findByLabelText('Pilot, Flights, Edit')
  return utils
}

const cell = (role, feature, action) => screen.getByLabelText(`${role}, ${feature}, ${action}`)

afterEach(() => setWide(false))

describe('RolePermissionsGrid wide layout', () => {
  it('renders every feature and action from the response with the current values', async () => {
    setWide(true)
    await renderGrid()
    for (const feature of ['Flights', 'Fleet equipment', 'Equipment checkouts']) {
      expect(screen.getByRole('rowheader', { name: feature })).toBeInTheDocument()
    }
    expect(screen.getByText('Check out, check in')).toBeInTheDocument()
    expect(cell('Pilot', 'Flights', 'Edit')).toHaveValue('own')
    expect(cell('Supervisor', 'Flights', 'Edit')).toHaveValue('all')
    expect(cell('Pilot', 'Fleet equipment', 'Manage')).toHaveValue('no')
  })

  it('shows Admin locked on and not editable', async () => {
    setWide(true)
    await renderGrid()
    const admin = cell('Admin', 'Flights', 'Edit')
    expect(admin).toBeDisabled()
    expect(admin).toHaveValue('all')
    expect(cell('Admin', 'Flights', 'View')).toHaveValue('yes')
  })

  it('disables locked viewer cells with a reason, and keeps viewer view editable', async () => {
    setWide(true)
    await renderGrid()
    const locked = cell('Viewer', 'Flights', 'Create')
    expect(locked).toBeDisabled()
    expect(locked).toHaveAccessibleDescription('Viewers are read only')
    expect(cell('Viewer', 'Flights', 'View')).toBeEnabled()
  })

  it('turning a view off lowers dependents across features and disables them with a reason', async () => {
    setWide(true)
    const { user } = await renderGrid()
    await user.selectOptions(cell('Pilot', 'Fleet equipment', 'View'), 'no')
    const checkout = cell('Pilot', 'Equipment checkouts', 'Check out, check in')
    expect(checkout).toHaveValue('no')
    expect(checkout).toBeDisabled()
    expect(checkout).toHaveAccessibleDescription('Needs Fleet equipment view on')
    // Other roles and features are untouched
    expect(cell('Supervisor', 'Equipment checkouts', 'Check out, check in')).toHaveValue('yes')
    expect(cell('Pilot', 'Flights', 'Edit')).toBeEnabled()

    await user.selectOptions(cell('Pilot', 'Fleet equipment', 'View'), 'yes')
    expect(checkout).toBeEnabled()
    expect(checkout).toHaveValue('no')
  })

  it('shows save and discard only when there are changes', async () => {
    setWide(true)
    const { user } = await renderGrid()
    expect(screen.queryByRole('button', { name: 'Save changes' })).not.toBeInTheDocument()
    await user.selectOptions(cell('Pilot', 'Flights', 'Edit'), 'all')
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeInTheDocument()
    expect(screen.getByText('1 unsaved change')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Discard' }))
    expect(cell('Pilot', 'Flights', 'Edit')).toHaveValue('own')
    expect(screen.queryByRole('button', { name: 'Save changes' })).not.toBeInTheDocument()
  })

  it('saves only changed cells and refreshes from the response', async () => {
    setWide(true)
    let body = null
    const returned = structuredClone(VALUES)
    returned.pilot['flights.edit'] = 'all'
    server.use(http.put('/api/permissions', async ({ request }) => {
      body = await request.json()
      return HttpResponse.json({ registry: REGISTRY, values: returned })
    }))
    const { user } = await renderGrid()
    await user.selectOptions(cell('Pilot', 'Flights', 'Edit'), 'all')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(body).not.toBeNull())
    expect(body).toEqual({ changes: [{ role: 'pilot', key: 'flights.edit', value: 'all' }] })
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Save changes' })).not.toBeInTheDocument())
    expect(cell('Pilot', 'Flights', 'Edit')).toHaveValue('all')
  })

  it('shows a server error and keeps the draft', async () => {
    setWide(true)
    server.use(http.put('/api/permissions', () => HttpResponse.json(
      { detail: 'flights.edit: invalid value' }, { status: 422 },
    )))
    const { user } = await renderGrid()
    await user.selectOptions(cell('Pilot', 'Flights', 'Edit'), 'all')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('flights.edit: invalid value')
    expect(cell('Pilot', 'Flights', 'Edit')).toHaveValue('all')
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeEnabled()
  })

  it('asks before resetting and refreshes from the response', async () => {
    setWide(true)
    const reset = vi.fn()
    const defaults = structuredClone(VALUES)
    defaults.pilot['flights.edit'] = 'none'
    server.use(http.post('/api/permissions/reset', () => {
      reset()
      return HttpResponse.json({ registry: REGISTRY, values: defaults })
    }))
    const { user } = await renderGrid()
    await user.click(screen.getByRole('button', { name: 'Reset to defaults' }))
    const dialog = await screen.findByRole('dialog')
    expect(reset).not.toHaveBeenCalled()
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(reset).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Reset to defaults' }))
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Reset to defaults' }))
    await waitFor(() => expect(cell('Pilot', 'Flights', 'Edit')).toHaveValue('none'))
    expect(reset).toHaveBeenCalledTimes(1)
  })

  it('shows an error with a retry when loading fails', async () => {
    setWide(true)
    server.use(http.get('/api/permissions', () => HttpResponse.json({ detail: 'down' }, { status: 500 })))
    renderWithProviders(<RolePermissionsGrid />, { role: 'admin' })
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })
})

describe('RolePermissionsGrid narrow layout', () => {
  it('shows one card per feature and reaches every role through a selector', async () => {
    setWide(false)
    mockGet()
    const { user } = renderWithProviders(<RolePermissionsGrid />, { role: 'admin' })
    await screen.findByLabelText('Supervisor, Flights, Edit')
    expect(screen.getAllByRole('group').map(g => g.getAttribute('aria-label')))
      .toEqual(['Flights', 'Fleet equipment', 'Equipment checkouts'])
    expect(screen.queryByLabelText('Pilot, Flights, Edit')).not.toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Role'), 'pilot')
    expect(cell('Pilot', 'Flights', 'Edit')).toHaveValue('own')
    await user.selectOptions(cell('Pilot', 'Flights', 'Edit'), 'all')
    await user.selectOptions(screen.getByLabelText('Role'), 'viewer')
    expect(cell('Viewer', 'Flights', 'Create')).toBeDisabled()
    expect(screen.getAllByText('Viewers are read only').length).toBeGreaterThan(0)
    await user.selectOptions(screen.getByLabelText('Role'), 'admin')
    expect(cell('Admin', 'Flights', 'Edit')).toBeDisabled()
    // The draft survives switching roles
    await user.selectOptions(screen.getByLabelText('Role'), 'pilot')
    expect(cell('Pilot', 'Flights', 'Edit')).toHaveValue('all')
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeInTheDocument()
  })
})
