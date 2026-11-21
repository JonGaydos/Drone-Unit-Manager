import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { withPermissions } from '@/test/permissions'
import { pilotOption } from '@/test/options'
import { renderWithProviders } from '@/test/render'
import { addDays, todayLocal } from '@/lib/utils'
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
    certs: {
      1: { id: 100, status: 'valid', issue_date: '2024-01-01', expiration_date: '2099-01-01' },
      // The API fills every empty pilot and type pair with a placeholder like this one.
      2: { id: null, status: 'not_started', issue_date: null, expiration_date: null, certificate_number: null, nist_level: null, notes: null },
    },
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

// jsdom reports every media query as false (a phone); these tests run at
// desktop width, where the matrix is the default view.
const realMatchMedia = globalThis.matchMedia
function setWide(wide) {
  globalThis.matchMedia = (query) => ({ ...realMatchMedia(query), matches: wide })
}

const ADA_PART107 = /^Ada Lovelace, Part 107: valid, expires Jan 1, 2099$/
const ADA_NIST = /^Ada Lovelace, NIST Basic: not started, no expiration date$/

describe('CertificationsPage', () => {
  beforeEach(() => setWide(true))
  afterEach(() => { globalThis.matchMedia = realMatchMedia })
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
    // status cell rendered as an icon labelled with pilot, cert, status and date
    expect(screen.getByRole('button', { name: ADA_PART107 })).toHaveAttribute('title', 'Expires Jan 1, 2099')
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

    // Open the edit modal by clicking the filled cell's status icon.
    await user.click(screen.getByRole('button', { name: ADA_PART107 }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Remove' }))

    // Confirm dialog appears on top, says the renewal history goes too; confirm.
    expect(await screen.findByText(/and its renewal history/)).toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: 'Confirm' }))

    expect(deleted).toBe('100')
  })

  // Opens Edit Certification on Ada's cert with the cell fields given, and
  // records the PATCH body the dialog sends.
  async function openEditCert(cellFields) {
    const sent = { body: null }
    mockMount({ matrix: () => HttpResponse.json({ matrix: [{ ...MATRIX[0], certs: { 1: {
      ...MATRIX[0].certs[1], ...cellFields } } }] }) })
    server.use(
      http.get('/api/pilot-certifications/:id/history', () => HttpResponse.json([])),
      http.get('/api/documents', () => HttpResponse.json([])),
      http.patch('/api/pilot-certifications/100', async ({ request }) => {
        sent.body = await request.json()
        return HttpResponse.json({ id: 100 })
      }),
    )
    const { user } = renderWithProviders(<CertificationsPage />, { role: 'admin' })
    await screen.findByRole('link', { name: 'Ada Lovelace' })
    await user.click(screen.getByRole('button', { name: /^Ada Lovelace, Part 107:/ }))
    const dialog = await screen.findByRole('dialog')
    return { user, dialog, sent }
  }

  it('sends null for a date or number cleared in Edit Certification (C-F21)', async () => {
    const { user, dialog, sent } = await openEditCert({ certificate_number: 'CN-1', notes: null })
    await user.clear(within(dialog).getByLabelText('Expiration Date'))
    await user.clear(within(dialog).getByLabelText('Certificate Number'))
    await user.click(within(dialog).getByRole('button', { name: 'Update' }))

    await waitFor(() => expect(sent.body).not.toBeNull())
    const body = sent.body
    expect(body.expiration_date).toBeNull()
    expect(body.certificate_number).toBeNull()
    expect(body).not.toHaveProperty('notes')
    expect(body.issue_date).toBe('2024-01-01')
  })

  it('shows the stored notes in Edit Certification and sends null when they are cleared (C-F21)', async () => {
    const { user, dialog, sent } = await openEditCert({ notes: 'Checkride with the chief pilot' })
    const notes = within(dialog).getByLabelText('Notes')
    expect(notes).toHaveValue('Checkride with the chief pilot')
    await user.clear(notes)
    await user.click(within(dialog).getByRole('button', { name: 'Update' }))

    await waitFor(() => expect(sent.body).not.toBeNull())
    expect(sent.body.notes).toBeNull()
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
    await user.click(within(screen.getByRole('table')).getByRole('button', { name: ADA_NIST }))
    const dialog = await screen.findByRole('dialog')

    expect(within(dialog).getByText('Assign Certification')).toBeInTheDocument()
    expect(within(dialog).getByLabelText('Pilot')).toHaveValue('5')
    expect(within(dialog).getByLabelText('Certification')).toHaveValue('2')
  })

  it('shows an existing cert read-only with its documents without certifications.manage', async () => {
    mockMount()
    server.use(http.get('/api/documents', () => HttpResponse.json([])))
    const { user } = renderWithProviders(<CertificationsPage />, { role: 'pilot' })
    await screen.findByRole('link', { name: 'Ada Lovelace' })
    await user.click(screen.getByRole('button', { name: ADA_PART107 }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Documents')).toBeInTheDocument()
    for (const name of ['Update', 'Renew', 'Remove']) {
      expect(within(dialog).queryByRole('button', { name })).toBeNull()
    }
  })

  it('shows no bulk-renewal checkbox on a placeholder cell', async () => {
    mockMount()
    renderWithProviders(<CertificationsPage />, { role: 'admin' })
    await screen.findByRole('link', { name: 'Ada Lovelace' })
    const cell = within(screen.getByRole('table')).getByRole('button', { name: ADA_NIST }).closest('td')
    expect(within(cell).queryByRole('checkbox')).toBeNull()
  })

  it('does not make a placeholder cell clickable or focusable for a pilot with file access', async () => {
    mockMount()
    server.use(http.get('/api/documents', () => HttpResponse.json([])))
    const { user } = renderWithProviders(<CertificationsPage />, { role: 'pilot' })
    await screen.findByRole('link', { name: 'Ada Lovelace' })
    const icon = within(screen.getByRole('table')).getByRole('img', { name: ADA_NIST })
    expect(within(icon.closest('td')).queryByRole('button')).toBeNull()
    expect(icon).not.toHaveAttribute('tabindex')
    await user.click(icon)
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('does not open the assign form on an empty cell without certifications.manage', async () => {
    mockMount()
    const { user } = renderWithProviders(<CertificationsPage />, { role: 'pilot' })
    await screen.findByRole('link', { name: 'Ada Lovelace' })
    await user.click(screen.getByRole('img', { name: ADA_NIST }))
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
    const soon = addDays(todayLocal(), 20)
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
    expect(within(table).getByRole('button', { name: /^Ada Lovelace, Part 107: expired, expired Jan 1, 2020$/ })).toHaveClass('text-danger')
    expect(within(table).getByRole('button', { name: /^Ada Lovelace, NIST Basic: expiring soon, expires / })).toHaveClass('text-warning')
    expect(within(table).getByRole('button', { name: /^Grace Hopper, Part 107: complete, / })).toHaveClass('text-success')
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

  describe('views', () => {
    // One cert per urgency group: expired, 20, 50 and 80 days out, and current.
    function viewsMatrix() {
      const today = todayLocal()
      return [
        { pilot_id: 5, pilot_name: 'Ada Lovelace', certs: {
          1: { id: 100, status: 'complete', expiration_date: '2020-01-01' },
          2: { id: 101, status: 'complete', expiration_date: addDays(today, 20) },
        } },
        { pilot_id: 6, pilot_name: 'Grace Hopper', certs: {
          1: { id: 102, status: 'complete', expiration_date: addDays(today, 50) },
          2: { id: null, status: 'not_started', expiration_date: null },
        } },
        { pilot_id: 7, pilot_name: 'Lin Tran', certs: {
          1: { id: 103, status: 'complete', expiration_date: addDays(today, 80) },
          2: { id: 104, status: 'active', expiration_date: '2099-01-01' },
        } },
      ]
    }
    function mountViews() {
      mockMount({
        matrix: () => HttpResponse.json({ matrix: viewsMatrix() }),
        pilots: () => HttpResponse.json([pilotOption(5, 'Ada Lovelace'), pilotOption(6, 'Grace Hopper'), pilotOption(7, 'Lin Tran')]),
      })
      server.use(
        http.get('/api/pilot-certifications/:id/history', () => HttpResponse.json([])),
        http.get('/api/documents', () => HttpResponse.json([])),
      )
      return renderWithProviders(<CertificationsPage />, { role: 'admin' })
    }
    async function chooseView(user, name) {
      await screen.findByRole('link', { name: 'Ada Lovelace' })
      await user.click(screen.getByRole('button', { name }))
    }
    const section = (title) => screen.getByRole('region', { name: title })

    it('offers Matrix, By pilot and By urgency, with Matrix pressed on a wide screen', async () => {
      mountViews()
      await screen.findByRole('link', { name: 'Ada Lovelace' })
      expect(screen.getByRole('button', { name: 'Matrix' })).toHaveAttribute('aria-pressed', 'true')
      expect(screen.getByRole('button', { name: 'By pilot' })).toHaveAttribute('aria-pressed', 'false')
      expect(screen.getByRole('button', { name: 'By urgency' })).toHaveAttribute('aria-pressed', 'false')
    })

    it('pins the pilot column and header row inside the matrix scroll box', async () => {
      mountViews()
      await screen.findByRole('link', { name: 'Ada Lovelace' })
      const corner = screen.getByRole('columnheader', { name: 'Pilot' })
      // Pinned cells use an opaque background, not the (translucent in some themes) card.
      expect(corner.className).toMatch(/sticky top-0 left-0 z-30 matrix-pin/)
      expect(screen.getByRole('columnheader', { name: /Part 107/ }).className).toMatch(/sticky top-0 z-20 matrix-pin/)
      const pilotCell = screen.getByRole('link', { name: 'Ada Lovelace' }).closest('td')
      expect(pilotCell.className).toMatch(/sticky left-0 z-10 matrix-pin/)
      expect(pilotCell.className).not.toMatch(/bg-card/)
      expect(screen.getByRole('table').parentElement.className).toMatch(/overflow-auto/)
    })

    it('shows one card per pilot with certification chips in By pilot', async () => {
      const { user } = mountViews()
      await chooseView(user, 'By pilot')
      expect(screen.queryByRole('table')).toBeNull()
      const card = screen.getByRole('listitem', { name: 'Grace Hopper' })
      expect(within(card).getByRole('link', { name: 'Grace Hopper' })).toBeInTheDocument()
      const chip = within(card).getByRole('button', { name: /^Grace Hopper, Part 107: expiring soon, expires / })
      expect(chip).toHaveClass('text-warning')
      expect(chip).toHaveTextContent(/Part 107/)
      expect(screen.getAllByRole('listitem', { name: /Lovelace|Hopper|Tran/ })).toHaveLength(3)
    })

    it('opens the edit modal from a chip and the assign modal from an empty chip in By pilot', async () => {
      const { user } = mountViews()
      await chooseView(user, 'By pilot')
      await user.click(screen.getByRole('button', { name: /^Ada Lovelace, Part 107: expired/ }))
      expect(await screen.findByRole('dialog', { name: 'Edit Certification' })).toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: 'Cancel' }))
      await user.click(screen.getByRole('button', { name: /^Grace Hopper, NIST Basic: not started/ }))
      const dialog = await screen.findByRole('dialog', { name: 'Assign Certification' })
      expect(within(dialog).getByLabelText('Pilot')).toHaveValue('6')
      expect(within(dialog).getByLabelText('Certification')).toHaveValue('2')
    })

    it('groups certifications by urgency with pilot, certification and date', async () => {
      const { user } = mountViews()
      await chooseView(user, 'By urgency')
      expect(within(section('Expired')).getByRole('button', { name: /^Ada Lovelace, Part 107: expired/ })).toBeInTheDocument()
      expect(within(section('Expired')).getByText('Jan 1, 2020')).toBeInTheDocument()
      expect(within(section('Expiring within 30 days')).getByRole('button', { name: /^Ada Lovelace, NIST Basic:/ })).toBeInTheDocument()
      expect(within(section('Expiring within 60 days')).getByRole('button', { name: /^Grace Hopper, Part 107:/ })).toBeInTheDocument()
      expect(within(section('Expiring within 90 days')).getByRole('button', { name: /^Lin Tran, Part 107:/ })).toBeInTheDocument()
      expect(within(section('Current')).getByRole('button', { name: /^Lin Tran, NIST Basic: active/ })).toBeInTheDocument()
      expect(within(section('Current')).getByRole('link', { name: 'Lin Tran' })).toBeInTheDocument()
      // The empty placeholder is not an urgency item.
      expect(screen.queryByRole('button', { name: /NIST Basic: not started/ })).toBeNull()
    })

    it('opens the edit modal from an urgency item', async () => {
      const { user } = mountViews()
      await chooseView(user, 'By urgency')
      await user.click(within(section('Expired')).getByRole('button', { name: /^Ada Lovelace, Part 107:/ }))
      const dialog = await screen.findByRole('dialog', { name: 'Edit Certification' })
      expect(within(dialog).getByRole('button', { name: 'Renew' })).toBeInTheDocument()
    })

    it('applies the pilot search in By pilot', async () => {
      const { user } = mountViews()
      await chooseView(user, 'By pilot')
      await user.type(screen.getByPlaceholderText('Search pilots...'), 'grace')
      expect(screen.getByRole('listitem', { name: 'Grace Hopper' })).toBeInTheDocument()
      expect(screen.queryByRole('listitem', { name: 'Ada Lovelace' })).toBeNull()
    })

    it('applies the status filter and category filter in By urgency', async () => {
      const { user } = mountViews()
      await chooseView(user, 'By urgency')
      await user.selectOptions(screen.getByDisplayValue('All Statuses'), 'expiring')
      expect(screen.queryByRole('button', { name: /: expired/ })).toBeNull()
      expect(screen.queryByRole('button', { name: /^Lin Tran, NIST Basic/ })).toBeNull()
      expect(within(section('Expiring within 30 days')).getByRole('button', { name: /^Ada Lovelace, NIST Basic:/ })).toBeInTheDocument()
      await user.selectOptions(screen.getByDisplayValue('All Categories'), 'faa')
      expect(screen.queryByRole('button', { name: /NIST Basic/ })).toBeNull()
      expect(within(section('Expiring within 60 days')).getByRole('button', { name: /^Grace Hopper, Part 107:/ })).toBeInTheDocument()
    })

    it('hides pilots with no records in By pilot when Hide empty is ticked', async () => {
      mockMount({ matrix: () => HttpResponse.json({ matrix: [
        ...viewsMatrix(),
        { pilot_id: 8, pilot_name: 'Kim Park', certs: { 1: { id: null, status: 'not_started' }, 2: { id: null, status: 'not_started' } } },
      ] }) })
      const { user } = renderWithProviders(<CertificationsPage />, { role: 'admin' })
      await chooseView(user, 'By pilot')
      expect(screen.getByRole('listitem', { name: 'Kim Park' })).toBeInTheDocument()
      await user.click(screen.getByRole('checkbox', { name: /Hide empty/i }))
      expect(screen.queryByRole('listitem', { name: 'Kim Park' })).toBeNull()
    })

    it('keeps bulk renewal in the matrix only', async () => {
      const { user } = mountViews()
      await screen.findByRole('link', { name: 'Ada Lovelace' })
      await user.click(screen.getAllByRole('checkbox', { name: 'Select certification for bulk renewal' })[0])
      expect(screen.getByRole('button', { name: 'Renew selected' })).toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: 'By pilot' }))
      expect(screen.queryByRole('checkbox', { name: 'Select certification for bulk renewal' })).toBeNull()
      expect(screen.queryByRole('button', { name: 'Renew selected' })).toBeNull()
    })

    it('explains By urgency when the status filter can never appear there', async () => {
      const { user } = mountViews()
      await chooseView(user, 'By urgency')
      await user.selectOptions(screen.getByDisplayValue('All Statuses'), 'pending')
      expect(screen.getByText('By urgency lists dated and current records')).toBeInTheDocument()
      expect(screen.queryByRole('region', { name: 'Expired' })).toBeNull()
    })

    it('clears the bulk selection when leaving the matrix', async () => {
      const { user } = mountViews()
      await screen.findByRole('link', { name: 'Ada Lovelace' })
      await user.click(screen.getAllByRole('checkbox', { name: 'Select certification for bulk renewal' })[0])
      await user.click(screen.getByRole('button', { name: 'By pilot' }))
      await user.click(screen.getByRole('button', { name: 'Matrix' }))
      expect(screen.queryByRole('button', { name: 'Renew selected' })).toBeNull()
    })

    it('raises the matrix header above the pinned pilot column', async () => {
      mountViews()
      await screen.findByRole('link', { name: 'Ada Lovelace' })
      const thead = screen.getByRole('columnheader', { name: 'Pilot' }).closest('thead')
      expect(thead.style.zIndex).toBe('30')
    })

    it('remembers the chosen view', async () => {
      const { user } = mountViews()
      await chooseView(user, 'By urgency')
      expect(localStorage.getItem('certifications.view')).toBe('urgency')
    })

    it('restores the stored view', async () => {
      localStorage.setItem('certifications.view', 'urgency')
      mountViews()
      await screen.findAllByRole('link', { name: 'Ada Lovelace' })
      expect(screen.getByRole('button', { name: 'By urgency' })).toHaveAttribute('aria-pressed', 'true')
      expect(section('Expired')).toBeInTheDocument()
    })

    it('defaults to By pilot on a narrow screen with nothing stored', async () => {
      setWide(false)
      mountViews()
      await screen.findByRole('link', { name: 'Ada Lovelace' })
      expect(screen.getByRole('button', { name: 'By pilot' })).toHaveAttribute('aria-pressed', 'true')
      expect(screen.queryByRole('table')).toBeNull()
    })

    it('falls back to the default view when storage throws', async () => {
      const realGetItem = Storage.prototype.getItem
      const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(function getItem(key) {
        if (key === 'certifications.view') throw new Error('denied')
        return realGetItem.call(this, key)
      })
      try {
        mockMount()
        renderWithProviders(<CertificationsPage />, { role: 'admin' })
        expect(await screen.findByRole('button', { name: 'Matrix' })).toHaveAttribute('aria-pressed', 'true')
      } finally {
        spy.mockRestore()
      }
    })
  })
})
