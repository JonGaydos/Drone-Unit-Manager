import { describe, it, expect } from 'vitest'
import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import FleetPage from './FleetPage'

// Default tab is "vehicles" (read from globalThis.location.search, which has no
// ?tab in jsdom). Mount endpoints for the vehicles tab:
//   GET /vehicles                         (vehicleModels effect + load)
//   GET /vehicle-registrations/current    (enrichment, swallowed on failure)
const VEHICLES = '/api/vehicles'
const CURRENT_REGS = '/api/vehicle-registrations/current'

const VEHICLE_ROWS = [
  { id: 1, nickname: 'Falcon', manufacturer: 'DJI', model: 'Mavic 3', serial_number: 'SN-001', status: 'active' },
  { id: 2, nickname: 'Hawk', manufacturer: 'Skydio', model: 'X10', serial_number: 'SN-002', status: 'maintenance' },
]

function mockVehicles(rows = VEHICLE_ROWS) {
  server.use(
    http.get(VEHICLES, () => HttpResponse.json(rows)),
    http.get(CURRENT_REGS, () => HttpResponse.json([])),
  )
}

describe('FleetPage', () => {
  it('renders without crashing', async () => {
    mockVehicles()
    renderWithProviders(<FleetPage />, { role: 'admin' })
    expect(await screen.findByText('Falcon')).toBeInTheDocument()
  })

  it('loads and renders vehicle rows from a populated payload', async () => {
    mockVehicles()
    renderWithProviders(<FleetPage />, { role: 'admin' })

    expect(await screen.findByRole('link', { name: 'Falcon' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Hawk' })).toBeInTheDocument()
    expect(screen.getByText('DJI')).toBeInTheDocument()
    expect(screen.getByText('Skydio')).toBeInTheDocument()
  })

  it('shows the empty state when there are no vehicles', async () => {
    mockVehicles([])
    renderWithProviders(<FleetPage />, { role: 'admin' })
    expect(await screen.findByText('No vehicles found')).toBeInTheDocument()
  })

  it('shows the error banner when the primary endpoint 500s', async () => {
    server.use(
      http.get(VEHICLES, () => HttpResponse.json({ detail: 'boom' }, { status: 500 })),
      http.get(CURRENT_REGS, () => HttpResponse.json([])),
    )
    renderWithProviders(<FleetPage />, { role: 'admin' })
    // load() surfaces the thrown error.message into the error banner.
    expect(await screen.findByText(/HTTP 500|boom|500/)).toBeInTheDocument()
  })

  it('filters the list with the search box', async () => {
    mockVehicles()
    const { user } = renderWithProviders(<FleetPage />, { role: 'admin' })

    await screen.findByRole('link', { name: 'Falcon' })
    await user.type(screen.getByPlaceholderText('Search vehicles...'), 'Hawk')

    expect(screen.queryByRole('link', { name: 'Falcon' })).toBeNull()
    expect(screen.getByRole('link', { name: 'Hawk' })).toBeInTheDocument()
  })

  it('renders the row name as a link to the vehicle detail route', async () => {
    mockVehicles()
    renderWithProviders(<FleetPage />, { role: 'admin' })

    const link = await screen.findByRole('link', { name: 'Falcon' })
    expect(link).toHaveAttribute('href', '/fleet/vehicles/1')
  })

  it('shows the Add button for a supervisor but hides it for a viewer', async () => {
    mockVehicles()
    const { unmount } = renderWithProviders(<FleetPage />, { role: 'supervisor' })
    expect(await screen.findByText('Falcon')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Add Vehicle/ })).toBeInTheDocument()
    unmount()

    server.use(http.get('/api/auth/me', () => HttpResponse.json({ id: 9, username: 'viewer', role: 'viewer' })))
    mockVehicles()
    renderWithProviders(<FleetPage />, { role: 'viewer' })
    expect(await screen.findByText('Falcon')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Add Vehicle/ })).toBeNull()
  })

  it('switches tabs and loads the batteries endpoint', async () => {
    mockVehicles()
    server.use(http.get('/api/batteries', () => HttpResponse.json([
      { id: 5, nickname: 'Cell A', serial_number: 'B-1', manufacturer: 'DJI', model: 'TB30', cycle_count: 12, health_pct: 88, status: 'active' },
    ])))
    const { user } = renderWithProviders(<FleetPage />, { role: 'admin' })

    await screen.findByText('Falcon')
    await user.click(screen.getByRole('button', { name: /Batteries/ }))

    expect(await screen.findByRole('link', { name: 'Cell A' })).toBeInTheDocument()
  })

  it('shows the Other tab with lifecycle dates and detail links', async () => {
    mockVehicles()
    server.use(http.get('/api/other-equipment', () => HttpResponse.json([
      { id: 3, name: 'Pelican case', category: 'case', serial_number: null, status: 'active', acquired_date: '2024-02-10', decommissioned_date: null },
    ])))
    const { user } = renderWithProviders(<FleetPage />, { role: 'admin' })

    await screen.findByText('Falcon')
    await user.click(screen.getByRole('button', { name: /Other/ }))

    const link = await screen.findByRole('link', { name: 'Pelican case' })
    expect(link).toHaveAttribute('href', '/fleet/other/3')
    expect(screen.getByText('2024-02-10')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Add Other Item/ })).toBeInTheDocument()
  })
  // --- Status filter --------------------------------------------------------
  //
  // Retired kit was listed alongside active on every tab. The default now hides
  // it, but "in service" deliberately is NOT "status === active": a vehicle
  // grounded for maintenance is still in the fleet, and the incident workflow
  // sets that status automatically.

  const MIXED = [
    { id: 1, nickname: 'Falcon', manufacturer: 'DJI', model: 'Mavic 3', serial_number: 'SN-001', status: 'active' },
    { id: 2, nickname: 'Hawk', manufacturer: 'Skydio', model: 'X10', serial_number: 'SN-002', status: 'maintenance' },
    { id: 3, nickname: 'Relic', manufacturer: 'Skydio', model: 'X2E', serial_number: 'SN-003', status: 'retired' },
    { id: 4, nickname: 'Cracked', manufacturer: 'Skydio', model: 'X2E', serial_number: 'SN-004', status: 'damaged' },
  ]

  const statusSelect = () => screen.getByRole('combobox', { name: 'Status' })

  it('hides retired and damaged equipment by default', async () => {
    mockVehicles(MIXED)
    renderWithProviders(<FleetPage />, { role: 'admin' })

    expect(await screen.findByRole('link', { name: 'Falcon' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Relic' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Cracked' })).not.toBeInTheDocument()
  })

  it('keeps a vehicle grounded for maintenance visible by default', async () => {
    mockVehicles(MIXED)
    renderWithProviders(<FleetPage />, { role: 'admin' })

    // The whole point of filtering on decommissioned rather than on
    // status !== 'active': this aircraft is still in the fleet.
    expect(await screen.findByRole('link', { name: 'Hawk' })).toBeInTheDocument()
  })

  it('says how many items the status filter is withholding', async () => {
    mockVehicles(MIXED)
    renderWithProviders(<FleetPage />, { role: 'admin' })

    expect(await screen.findByText('2 hidden')).toBeInTheDocument()
  })

  it('shows everything on "All statuses"', async () => {
    mockVehicles(MIXED)
    const { user } = renderWithProviders(<FleetPage />, { role: 'admin' })
    await screen.findByRole('link', { name: 'Falcon' })

    await user.selectOptions(statusSelect(), 'all')

    expect(screen.getByRole('link', { name: 'Relic' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Cracked' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Falcon' })).toBeInTheDocument()
    expect(screen.queryByText(/hidden/)).not.toBeInTheDocument()
  })

  it('shows only retired and damaged when asked for them', async () => {
    mockVehicles(MIXED)
    const { user } = renderWithProviders(<FleetPage />, { role: 'admin' })
    await screen.findByRole('link', { name: 'Falcon' })

    await user.selectOptions(statusSelect(), 'decommissioned')

    expect(screen.getByRole('link', { name: 'Relic' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Cracked' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Falcon' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Hawk' })).not.toBeInTheDocument()
  })

  it('applies the filter on the other tabs too, and keeps the choice across a switch', async () => {
    mockVehicles(MIXED)
    server.use(http.get('/api/batteries', () => HttpResponse.json([
      { id: 5, nickname: 'Cell A', serial_number: 'B-1', status: 'active' },
      { id: 6, nickname: 'Cell Dead', serial_number: 'B-2', status: 'retired' },
      { id: 7, nickname: 'Cell Bulged', serial_number: 'B-3', status: 'damaged' },
    ])))
    const { user } = renderWithProviders(<FleetPage />, { role: 'admin' })
    await screen.findByRole('link', { name: 'Falcon' })

    await user.click(screen.getByRole('button', { name: /Batteries/ }))

    expect(await screen.findByRole('link', { name: 'Cell A' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Cell Dead' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Cell Bulged' })).not.toBeInTheDocument()

    // The choice carries across tabs rather than silently resetting.
    await user.selectOptions(statusSelect(), 'all')
    expect(screen.getByRole('link', { name: 'Cell Dead' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Vehicles/ }))
    expect(await screen.findByRole('link', { name: 'Relic' })).toBeInTheDocument()
  })

  it('combines the status filter with the search box', async () => {
    mockVehicles(MIXED)
    const { user } = renderWithProviders(<FleetPage />, { role: 'admin' })
    await screen.findByRole('link', { name: 'Falcon' })

    await user.type(screen.getByPlaceholderText(/Search vehicles/i), 'Skydio')

    // Hawk is Skydio and in service; Relic is Skydio but retired.
    expect(screen.getByRole('link', { name: 'Hawk' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Relic' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Falcon' })).not.toBeInTheDocument()
  })
  // --- Export CSV on every tab, and a toolbar that stops moving ------------

  it('offers Export CSV on every equipment tab, not just Vehicles', async () => {
    mockVehicles()
    for (const ep of ['/api/batteries', '/api/controllers', '/api/docks',
                      '/api/sensors', '/api/attachments', '/api/other-equipment']) {
      server.use(http.get(ep, () => HttpResponse.json([])))
    }
    const { user } = renderWithProviders(<FleetPage />, { role: 'admin' })
    await screen.findByRole('link', { name: 'Falcon' })

    for (const tab of [/Batteries/, /Controllers/, /Docks/, /Sensors/, /Attachments/, /Other/]) {
      await user.click(screen.getByRole('button', { name: tab }))
      expect(await screen.findByRole('button', { name: /Export CSV/ })).toBeInTheDocument()
    }
  })

  it('exports the tab it is on, using the fleet endpoint for non-vehicle types', async () => {
    const requested = []
    mockVehicles()
    server.use(
      http.get('/api/batteries', () => HttpResponse.json([])),
      http.get('/api/export/fleet/batteries/csv', ({ request }) => {
        requested.push(new URL(request.url).pathname)
        return new HttpResponse('Serial', { headers: { 'Content-Type': 'text/csv' } })
      }),
    )
    const { user } = renderWithProviders(<FleetPage />, { role: 'admin' })
    await screen.findByRole('link', { name: 'Falcon' })

    await user.click(screen.getByRole('button', { name: /Batteries/ }))
    await user.click(await screen.findByRole('button', { name: /Export CSV/ }))

    await screen.findByRole('button', { name: /Export CSV/ })
    expect(requested).toContain('/api/export/fleet/batteries/csv')
  })

  it('keeps the status filter in the right-hand group on every tab', async () => {
    mockVehicles(MIXED)
    server.use(http.get('/api/docks', () => HttpResponse.json([])))
    const { user } = renderWithProviders(<FleetPage />, { role: 'admin' })
    await screen.findByRole('link', { name: 'Falcon' })

    // The filter, Export and Add all live in one right-anchored container, so
    // the filter no longer slides when a tab changes which buttons exist.
    const groupOf = (el) => el.closest('div')
    const onVehicles = groupOf(statusSelect())
    expect(within(onVehicles).getByRole('button', { name: /Export CSV/ })).toBeInTheDocument()
    expect(within(onVehicles).getByRole('button', { name: /Add Vehicle/ })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Docks/ }))
    const onDocks = groupOf(statusSelect())
    expect(within(onDocks).getByRole('button', { name: /Export CSV/ })).toBeInTheDocument()
    expect(within(onDocks).getByRole('button', { name: /Add Dock/ })).toBeInTheDocument()
  })
})
