import { describe, it, expect } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import OperatingAuthorityPage from './OperatingAuthorityPage'

// Mount endpoint:
//   GET /operating-authorities   (failure -> toast, empty list)
// Writes: POST / PATCH / DELETE /operating-authorities
const AUTHORITIES = [
  {
    id: 1, authority_type: 'coa', identifier: '2026-WSA-1234',
    title: 'Blanket public safety COA', issue_date: '2026-01-01', expiry_date: '2024-06-01',
    status: 'expired', days_remaining: -400, record_status: 'active', grounds_unit: true,
    notes: null, document_count: 1,
  },
  {
    id: 2, authority_type: 'part_107_waiver', identifier: '107W-2026-0001',
    title: 'Night operations waiver', issue_date: '2026-01-01', expiry_date: '2030-01-01',
    status: 'active', days_remaining: 900, record_status: 'active', grounds_unit: false,
    notes: null, document_count: 0,
  },
  {
    id: 3, authority_type: 'coa', identifier: '2023-WSA-0001',
    title: 'Prior COA', issue_date: '2023-01-01', expiry_date: '2025-12-31',
    status: 'expired', days_remaining: -200, record_status: 'superseded', grounds_unit: true,
    notes: null, document_count: 2,
  },
]

function mockMount(overrides = {}) {
  const base = {
    list: () => HttpResponse.json(AUTHORITIES),
    ...overrides,
  }
  server.use(http.get('/api/operating-authorities', base.list))
}

describe('OperatingAuthorityPage', () => {
  it('renders without crashing', async () => {
    mockMount()
    renderWithProviders(<OperatingAuthorityPage />, { role: 'admin' })
    expect(await screen.findByRole('heading', { name: /Operating Authority/ })).toBeInTheDocument()
  })

  it('renders a row per authority with its status badge', async () => {
    mockMount()
    renderWithProviders(<OperatingAuthorityPage />, { role: 'admin' })
    expect(await screen.findByText('Blanket public safety COA')).toBeInTheDocument()
    expect(screen.getByText('Night operations waiver')).toBeInTheDocument()
    expect(screen.getByText('Expired')).toBeInTheDocument()
    expect(screen.getByText('Active')).toBeInTheDocument()
  })

  it('shows the hand-set record status ahead of the expiry math', async () => {
    mockMount()
    renderWithProviders(<OperatingAuthorityPage />, { role: 'admin' })
    // Row 3 expired long ago but is marked superseded, so it reads Superseded.
    expect(await screen.findByText('Superseded')).toBeInTheDocument()
    expect(screen.getAllByText('Expired')).toHaveLength(1)
  })

  it('counts down the days on an authority inside the warning window', async () => {
    mockMount({
      list: () => HttpResponse.json([
        { ...AUTHORITIES[0], status: 'expiring', days_remaining: 45, expiry_date: '2026-10-10' },
      ]),
    })
    renderWithProviders(<OperatingAuthorityPage />, { role: 'admin' })
    expect(await screen.findByText('Expires in 45d')).toBeInTheDocument()
  })

  it('marks an authority whose lapse does not ground the unit', async () => {
    mockMount()
    renderWithProviders(<OperatingAuthorityPage />, { role: 'admin' })
    expect(await screen.findByText('Does not ground the unit')).toBeInTheDocument()
  })

  it('flags a record with no document attached', async () => {
    mockMount()
    renderWithProviders(<OperatingAuthorityPage />, { role: 'admin' })
    expect(await screen.findByText('None attached')).toBeInTheDocument()
  })

  it('shows the empty state and says the score is unaffected', async () => {
    mockMount({ list: () => HttpResponse.json([]) })
    renderWithProviders(<OperatingAuthorityPage />, { role: 'admin' })
    expect(await screen.findByText('No operating authorities on file')).toBeInTheDocument()
    expect(screen.getByText(/compliance score is unaffected/)).toBeInTheDocument()
  })

  it('falls back to the empty state when the list request 500s', async () => {
    mockMount({ list: () => new HttpResponse(null, { status: 500 }) })
    renderWithProviders(<OperatingAuthorityPage />, { role: 'admin' })
    expect(await screen.findByText('No operating authorities on file')).toBeInTheDocument()
  })

  it('hides the write controls from a pilot', async () => {
    mockMount()
    // Override /auth/me so the resolved role is pilot, not the default admin.
    server.use(http.get('/api/auth/me', () =>
      HttpResponse.json({ id: 3, username: 'pilot', role: 'pilot' })))
    renderWithProviders(<OperatingAuthorityPage />, { role: 'pilot' })
    expect(await screen.findByText('Blanket public safety COA')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Add Authority/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Edit / })).not.toBeInTheDocument()
    // Reading the attached documents stays available.
    expect(screen.getAllByRole('button', { name: /^Documents for / }).length).toBe(3)
  })

  it('posts a new authority from the create form', async () => {
    let posted = null
    mockMount()
    server.use(http.post('/api/operating-authorities', async ({ request }) => {
      posted = await request.json()
      return HttpResponse.json({ id: 9 }, { status: 201 })
    }))
    const user = userEvent.setup()
    renderWithProviders(<OperatingAuthorityPage />, { role: 'admin' })

    await user.click(await screen.findByRole('button', { name: /Add Authority/ }))
    await user.type(screen.getByLabelText('Title'), 'New COA')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(posted).toMatchObject({
      authority_type: 'coa',
      title: 'New COA',
      record_status: 'active',
      grounds_unit: true,
    })
  })

  it('opens the edit form prefilled with the row it was opened from', async () => {
    mockMount()
    const user = userEvent.setup()
    renderWithProviders(<OperatingAuthorityPage />, { role: 'admin' })

    await user.click(await screen.findByRole('button', { name: 'Edit Night operations waiver' }))

    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByLabelText('Title')).toHaveValue('Night operations waiver')
    expect(within(dialog).getByLabelText('COA / waiver number')).toHaveValue('107W-2026-0001')
    expect(within(dialog).getByLabelText('Record status')).toHaveValue('active')
    expect(within(dialog).getByRole('checkbox')).not.toBeChecked()
  })
})
