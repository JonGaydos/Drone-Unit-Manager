import { describe, it, expect } from 'vitest'
import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
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
    certs: { 1: { id: 100, status: 'valid', issue_date: '2024-01-01', expiration_date: '2026-01-01' } },
  },
]

function mockMount(overrides = {}) {
  const base = {
    certTypes: () => HttpResponse.json(CERT_TYPES),
    matrix: () => HttpResponse.json({ matrix: MATRIX }),
    pilots: () => HttpResponse.json([{ id: 5, first_name: 'Ada', last_name: 'Lovelace', full_name: 'Ada Lovelace', status: 'active' }]),
    labels: () => HttpResponse.json({ value: '' }),
    folders: () => HttpResponse.json([]),
    ...overrides,
  }
  server.use(
    http.get('/api/certification-types', base.certTypes),
    http.get('/api/certifications/matrix', base.matrix),
    http.get('/api/pilots', base.pilots),
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
    server.use(http.get('/api/auth/me', () => HttpResponse.json({ id: 3, username: 'p', role: 'pilot' })))
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

    // Confirm dialog appears on top; confirm the removal.
    await user.click(await screen.findByRole('button', { name: 'Confirm' }))

    expect(deleted).toBe('100')
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
})
