import { describe, it, expect } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { withPermissions } from '@/test/permissions'
import { pilotOption } from '@/test/options'
import { renderWithProviders } from '@/test/render'
import CertificationsPage from './CertificationsPage'

// Mount endpoints (Promise.all in load() + a folders prefetch):
//   GET /certification-types
//   GET /certifications/matrix   ({ matrix: [...] })
//   GET /pilots
//   GET /settings/cert_status_labels  (.catch -> { value: '' })
//   GET /folders                 (.catch)
// Bulk-renew interaction: POST /pilot-certifications/bulk-renew
const CERT_TYPES = [
  { id: 1, name: 'Part 107', category: 'faa', has_expiration: true, renewal_period_months: 24, is_active: true },
  { id: 2, name: 'NIST Basic', category: 'nist', has_expiration: true, renewal_period_months: 12, is_active: true },
]
const MATRIX = [
  {
    pilot_id: 5, pilot_name: 'Ada Lovelace',
    certs: { 1: { id: 100, status: 'valid', issue_date: '2024-01-01', expiration_date: '2099-01-01' } },
  },
]

function mockMount(overrides = {}) {
  const base = {
    certTypes: () => HttpResponse.json(CERT_TYPES),
    matrix: () => HttpResponse.json({ matrix: MATRIX }),
    pilots: () => HttpResponse.json([pilotOption(5, 'Ada Lovelace')]),
    labels: () => HttpResponse.json({ value: '' }),
    folders: () => HttpResponse.json([]),
    ...overrides,
  }
  server.use(
    http.get('/api/certification-types', base.certTypes),
    http.get('/api/certifications/matrix', base.matrix),
    http.get('/api/pilots/options', base.pilots),
    http.get('/api/settings/cert_status_labels', base.labels),
    http.get('/api/folders', base.folders),
  )
}

describe('CertificationsPage', () => {
  it('renders without crashing', async () => {
    mockMount()
    renderWithProviders(<CertificationsPage />, { role: 'admin' })
    expect(await screen.findByRole('link', { name: 'Ada Lovelace' })).toBeInTheDocument()
  })

  it('renders the cert matrix with pilot rows and cert-type columns', async () => {
    mockMount()
    renderWithProviders(<CertificationsPage />, { role: 'admin' })
    expect(await screen.findByRole('link', { name: 'Ada Lovelace' })).toBeInTheDocument()
    // cert-type column headers
    expect(screen.getByText('Part 107')).toBeInTheDocument()
    expect(screen.getByText('NIST Basic')).toBeInTheDocument()
    // status cell rendered (valid -> "valid")
    expect(screen.getByText('valid')).toBeInTheDocument()
  })

  it('shows the empty matrix state', async () => {
    mockMount({ matrix: () => HttpResponse.json({ matrix: [] }) })
    renderWithProviders(<CertificationsPage />, { role: 'admin' })
    expect(await screen.findByText('No pilots or certifications configured yet')).toBeInTheDocument()
  })

  it('shows the inline error banner when certification-types 500s', async () => {
    mockMount({ certTypes: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }) })
    renderWithProviders(<CertificationsPage />, { role: 'admin' })
    expect(await screen.findByText('No pilots or certifications configured yet')).toBeInTheDocument()
    expect(screen.getByText(/boom|HTTP 500|500/)).toBeInTheDocument()
  })

  it('bulk-renews selected certs and fires POST /pilot-certifications/bulk-renew with the captured body', async () => {
    let captured = null
    mockMount()
    server.use(
      http.post('/api/pilot-certifications/bulk-renew', async ({ request }) => {
        captured = await request.json()
        return HttpResponse.json({ renewed: 1 })
      }),
    )

    const { user } = renderWithProviders(<CertificationsPage />, { role: 'admin' })
    await screen.findByRole('link', { name: 'Ada Lovelace' })

    // Select the cert for bulk renewal, then open the bulk-renew modal.
    await user.click(screen.getByRole('checkbox', { name: 'Select certification for bulk renewal' }))
    await user.click(screen.getByRole('button', { name: 'Renew selected' }))

    const dialog = await screen.findByRole('dialog')
    await user.clear(within(dialog).getByLabelText('Issue date'))
    await user.type(within(dialog).getByLabelText('Issue date'), '2026-06-01')
    await user.click(within(dialog).getByRole('button', { name: 'Renew All' }))

    await screen.findByRole('link', { name: 'Ada Lovelace' })
    expect(captured).toMatchObject({ pilot_certification_ids: [100], issue_date: '2026-06-01' })
  })

  it('hides supervisor-only controls for a non-supervisor (pilot)', async () => {
    server.use(http.get('/api/auth/me', () => HttpResponse.json(withPermissions({ id: 3, username: 'p', role: 'pilot' }))))
    mockMount()
    renderWithProviders(<CertificationsPage />, { role: 'pilot' })
    await screen.findByRole('link', { name: 'Ada Lovelace' })
    expect(screen.queryByRole('button', { name: /Assign Cert/ })).toBeNull()
    expect(screen.queryByRole('checkbox', { name: 'Select certification for bulk renewal' })).toBeNull()
  })

  it('removes a certification from the edit modal after confirmation', async () => {
    let deleted = null
    mockMount()
    server.use(
      http.get('/api/pilot-certifications/:id/history', () => HttpResponse.json([])),
      http.get('/api/documents', () => HttpResponse.json([])),
      http.delete('/api/pilot-certifications/:id', ({ params }) => {
        deleted = params.id
        return HttpResponse.json({ ok: true })
      }),
    )

    const { user } = renderWithProviders(<CertificationsPage />, { role: 'admin' })
    await screen.findByRole('link', { name: 'Ada Lovelace' })

    // Open the edit modal by clicking the filled cell's status badge.
    await user.click(screen.getByText('valid'))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Remove' }))

    // Confirm dialog appears on top, says the renewal history goes too; confirm.
    expect(await screen.findByText(/and its renewal history/)).toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: 'Confirm' }))

    expect(deleted).toBe('100')
  })

  it('sends null for a date or number cleared in Edit Certification (C-F21)', async () => {
    let body = null
    mockMount({ matrix: () => HttpResponse.json({ matrix: [{ ...MATRIX[0], certs: { 1: {
      ...MATRIX[0].certs[1], certificate_number: 'CN-1', notes: null } } }] }) })
    server.use(
      http.get('/api/pilot-certifications/:id/history', () => HttpResponse.json([])),
      http.get('/api/documents', () => HttpResponse.json([])),
      http.patch('/api/pilot-certifications/100', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ id: 100 })
      }),
    )
    const { user } = renderWithProviders(<CertificationsPage />, { role: 'admin' })
    await screen.findByRole('link', { name: 'Ada Lovelace' })
    await user.click(screen.getByText('valid'))
    const dialog = await screen.findByRole('dialog')
    await user.clear(within(dialog).getByLabelText('Expiration Date'))
    await user.clear(within(dialog).getByLabelText('Certificate Number'))
    await user.click(within(dialog).getByRole('button', { name: 'Update' }))

    await waitFor(() => expect(body).not.toBeNull())
    expect(body.expiration_date).toBeNull()
    expect(body.certificate_number).toBeNull()
    expect(body).not.toHaveProperty('notes')
    expect(body.issue_date).toBe('2024-01-01')
  })

  it('hides and unhides a cert type from the types tab', async () => {
    let captured = null
    mockMount({
      certTypes: () => HttpResponse.json([
        ...CERT_TYPES,
        { id: 3, name: 'Legacy Cert', category: 'custom', has_expiration: false, is_active: false },
      ]),
    })
    server.use(
      http.patch('/api/certification-types/:id', async ({ params, request }) => {
        captured = { id: params.id, body: await request.json() }
        return HttpResponse.json({ id: Number(params.id), name: 'Legacy Cert', category: 'custom', is_active: true })
      }),
    )

    const { user } = renderWithProviders(<CertificationsPage />, { role: 'admin' })
    await screen.findByRole('link', { name: 'Ada Lovelace' })

    // Hidden type is excluded from the matrix columns.
    expect(screen.queryByText('Legacy Cert')).toBeNull()

    await user.click(screen.getByRole('button', { name: 'Cert Types' }))
    expect(await screen.findByText('Legacy Cert')).toBeInTheDocument()
    expect(screen.getByText('Hidden')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Unhide' }))
    expect(captured).toMatchObject({ id: '3', body: { is_active: true } })
  })

  it('prefills the assign modal from an empty matrix cell', async () => {
    mockMount()
    const { user } = renderWithProviders(<CertificationsPage />, { role: 'admin' })
    await screen.findByRole('link', { name: 'Ada Lovelace' })

    // Ada has no NIST Basic cert; her row's second cert cell is empty ("not started").
    await user.click(within(screen.getByRole('table')).getByText('not started'))
    const dialog = await screen.findByRole('dialog')

    expect(within(dialog).getByLabelText('Pilot')).toHaveValue('5')
    expect(within(dialog).getByLabelText('Certification')).toHaveValue('2')
  })

  it('shows an existing cert read-only with its documents without certifications.manage', async () => {
    mockMount()
    server.use(http.get('/api/documents', () => HttpResponse.json([])))
    const { user } = renderWithProviders(<CertificationsPage />, { role: 'pilot' })
    await screen.findByRole('link', { name: 'Ada Lovelace' })
    await user.click(screen.getByText('valid'))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Documents')).toBeInTheDocument()
    for (const name of ['Update', 'Renew', 'Remove']) {
      expect(within(dialog).queryByRole('button', { name })).toBeNull()
    }
  })

  it('does not open the assign form on an empty cell without certifications.manage', async () => {
    mockMount()
    const { user } = renderWithProviders(<CertificationsPage />, { role: 'pilot' })
    await screen.findByRole('link', { name: 'Ada Lovelace' })
    await user.click(screen.getAllByText('not started')[0])
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('does not ask for folders with files.view off', async () => {
    let asked = false
    mockMount()
    server.use(http.get('/api/folders', () => { asked = true; return HttpResponse.json([]) }))
    renderWithProviders(<CertificationsPage />, { role: 'pilot', permissions: { 'files.view': 'no' } })
    await screen.findByRole('link', { name: 'Ada Lovelace' })
    expect(asked).toBe(false)
  })

  it('marks expired and expiring cells and filters by that state', async () => {
    const soon = new Date(Date.now() + 20 * 86400000).toISOString().slice(0, 10)
    mockMount({
      matrix: () => HttpResponse.json({ matrix: [
        { pilot_id: 5, pilot_name: 'Ada Lovelace', certs: {
          1: { id: 100, status: 'complete', expiration_date: '2020-01-01' },
          2: { id: 101, status: 'complete', expiration_date: soon },
        } },
        { pilot_id: 6, pilot_name: 'Grace Hopper', certs: {
          1: { id: 102, status: 'complete', expiration_date: '2099-01-01' },
          2: { id: null, status: 'not_started', expiration_date: null },
        } },
      ] }),
    })
    const { user } = renderWithProviders(<CertificationsPage />, { role: 'admin' })
    await screen.findByRole('link', { name: 'Ada Lovelace' })
    const table = screen.getByRole('table')
    expect(within(table).getByText('expired')).toHaveClass('text-danger')
    expect(within(table).getByText('expiring soon')).toHaveClass('text-warning')
    expect(within(table).getByText('complete')).toHaveClass('text-success')
    await user.selectOptions(screen.getByDisplayValue('All Statuses'), 'expired')
    expect(screen.getByRole('link', { name: 'Ada Lovelace' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Grace Hopper' })).toBeNull()
    await user.selectOptions(screen.getByDisplayValue('expired'), 'expiring')
    expect(screen.getByRole('link', { name: 'Ada Lovelace' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Grace Hopper' })).toBeNull()
  })

  it('hides pilots with no certification records when Hide empty is ticked', async () => {
    mockMount({
      matrix: () => HttpResponse.json({ matrix: [
        { pilot_id: 5, pilot_name: 'Ada Lovelace', certs: {
          1: { id: 100, status: 'complete', expiration_date: '2099-01-01' },
          2: { id: null, status: 'not_started', expiration_date: null },
        } },
        { pilot_id: 6, pilot_name: 'Grace Hopper', certs: {
          1: { id: null, status: 'not_started', expiration_date: null },
          2: { id: null, status: 'not_started', expiration_date: null },
        } },
      ] }),
    })
    const { user } = renderWithProviders(<CertificationsPage />, { role: 'admin' })
    await screen.findByRole('link', { name: 'Grace Hopper' })
    await user.click(screen.getByRole('checkbox', { name: /Hide empty/i }))
    expect(screen.getByRole('link', { name: 'Ada Lovelace' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Grace Hopper' })).toBeNull()
  })
})
