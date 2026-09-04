import { describe, it, expect } from 'vitest'
import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import ChecklistPage from './ChecklistPage'

// Mount endpoints (Promise.all in load()):
//   GET /checklists/templates    (array)
//   GET /checklists/completions  (array)
//   GET /pilots /vehicles
const TEMPLATES = [
  { id: 1, name: 'Pre-Flight Safety', description: 'Standard checks', vehicle_model: 'DJI Mavic 3', is_active: true, items: [{ label: 'Props secure', required: true }, { label: 'Battery charged', required: true }] },
]
const COMPLETIONS = [
  { id: 10, completed_at: '2026-05-01T10:00:00', pilot_name: 'Jane Doe', vehicle_name: 'Falcon', template_name: 'Pre-Flight Safety', all_passed: true, responses: [] },
]

function mockMount(overrides = {}) {
  const base = {
    templates: () => HttpResponse.json(TEMPLATES),
    completions: () => HttpResponse.json(COMPLETIONS),
    ...overrides,
  }
  server.use(
    http.get('/api/checklists/templates', base.templates),
    http.get('/api/checklists/completions', base.completions),
    http.get('/api/pilots', () => HttpResponse.json([{ id: 5, first_name: 'Jane', last_name: 'Doe', full_name: 'Jane Doe', is_active: true }])),
    http.get('/api/vehicles', () => HttpResponse.json([{ id: 2, nickname: 'Falcon', model: 'Mavic 3', manufacturer: 'DJI' }])),
  )
}

describe('ChecklistPage', () => {
  it('renders without crashing', async () => {
    mockMount()
    renderWithProviders(<ChecklistPage />, { role: 'admin' })
    expect(await screen.findByText('Pre-Flight Safety')).toBeInTheDocument()
  })

  it('loads and renders template cards from a populated payload', async () => {
    mockMount()
    renderWithProviders(<ChecklistPage />, { role: 'admin' })
    expect(await screen.findByText('Pre-Flight Safety')).toBeInTheDocument()
    expect(screen.getByText('2 items')).toBeInTheDocument()
  })

  it('shows the empty templates state', async () => {
    mockMount({ templates: () => HttpResponse.json([]) })
    renderWithProviders(<ChecklistPage />, { role: 'admin' })
    expect(await screen.findByText('No Templates Yet')).toBeInTheDocument()
  })

  it('falls back to the empty UI when the primary endpoint 500s', async () => {
    // load() swallows the error into a toast; templates stays [] so empty UI shows.
    mockMount({ templates: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }) })
    renderWithProviders(<ChecklistPage />, { role: 'admin' })
    expect(await screen.findByText('No Templates Yet')).toBeInTheDocument()
  })

  it('switches to the Completions tab and renders completion rows', async () => {
    mockMount()
    const { user } = renderWithProviders(<ChecklistPage />, { role: 'admin' })

    await screen.findByText('Pre-Flight Safety')
    await user.click(screen.getByRole('button', { name: 'Completions' }))

    expect(await screen.findByText('Jane Doe')).toBeInTheDocument()
    expect(screen.getByText('Falcon')).toBeInTheDocument()
  })

  it('shows the empty completions state', async () => {
    mockMount({ completions: () => HttpResponse.json([]) })
    const { user } = renderWithProviders(<ChecklistPage />, { role: 'admin' })

    await screen.findByText('Pre-Flight Safety')
    await user.click(screen.getByRole('button', { name: 'Completions' }))
    expect(await screen.findByText('No Completions Yet')).toBeInTheDocument()
  })

  it('opens the Complete Checklist modal and renders template items for marking (pilot)', async () => {
    mockMount()
    const { user } = renderWithProviders(<ChecklistPage />, { role: 'pilot' })

    await screen.findByText('Pre-Flight Safety')
    await user.click(screen.getByRole('button', { name: /Complete Checklist/ }))

    const dialog = await screen.findByRole('dialog')
    await user.selectOptions(within(dialog).getByLabelText('Template *'), '1')

    // Selecting the template renders its items as checkable rows.
    expect(await within(dialog).findByText('Props secure')).toBeInTheDocument()
    expect(within(dialog).getByText('Battery charged')).toBeInTheDocument()
    // Required items unchecked surfaces the warning.
    expect(within(dialog).getByText('Some required items are not checked')).toBeInTheDocument()
  })
})
