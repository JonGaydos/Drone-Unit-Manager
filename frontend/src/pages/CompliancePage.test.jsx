import { describe, it, expect } from 'vitest'
import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import CompliancePage from './CompliancePage'

// Mount endpoint:
//   GET /dashboard/compliance   (primary; failure swallowed -> "Failed to load compliance data.")
const COMPLIANCE = {
  compliance_score: 72,
  expired_certifications: 2,
  expiring_certifications: [{ pilot_id: 5, days_remaining: 12 }],
  expired_registrations: 0,
  overdue_maintenance: 1,
  open_incidents: 0,
  unreviewed_flights: 3,
  pending_flight_plans: 0,
  operating_authorities_tracked: 2,
  expired_authorities: [],
  expiring_authorities: [],
  score_cap_reason: null,
  total_pilots: 5,
  total_vehicles: 3,
}

function mockMount(overrides = {}) {
  const base = {
    compliance: () => HttpResponse.json(COMPLIANCE),
    ...overrides,
  }
  server.use(http.get('/api/dashboard/compliance', base.compliance))
}

describe('CompliancePage', () => {
  it('renders without crashing', async () => {
    mockMount()
    renderWithProviders(<CompliancePage />, { role: 'admin' })
    expect(await screen.findByRole('heading', { name: 'Compliance Dashboard' })).toBeInTheDocument()
  })

  it('renders the compliance score and stat cards from a populated payload', async () => {
    mockMount()
    renderWithProviders(<CompliancePage />, { role: 'admin' })
    expect(await screen.findByRole('heading', { name: 'Compliance Dashboard' })).toBeInTheDocument()
    expect(screen.getByText('72')).toBeInTheDocument()          // score circle
    expect(screen.getByText('Expired Certs')).toBeInTheDocument()
    // attention item built from expired certs
    expect(screen.getByText('Expired Certifications')).toBeInTheDocument()
  })

  it.each(['Out of Currency', 'Pilot Currency Status', 'Currency Compliance', 'Pilots Out of Currency'])(
    'has no currency text: %s', async (text) => {
      mockMount()
      renderWithProviders(<CompliancePage />, { role: 'admin' })
      await screen.findByRole('heading', { name: 'Compliance Dashboard' })
      expect(screen.queryByText(text)).toBeNull()
    })

  it('offers no Send currency reminders to a manager', async () => {
    mockMount()
    renderWithProviders(<CompliancePage />, { role: 'admin' })
    await screen.findByRole('heading', { name: 'Compliance Dashboard' })
    expect(screen.queryByRole('button', { name: /Send Reminders/ })).toBeNull()
    expect(screen.queryByText(/Send currency reminders/)).toBeNull()
  })

  it('names the pilot and certification on an expiring-cert item, apart from its label', async () => {
    mockMount({
      compliance: () => HttpResponse.json({
        ...COMPLIANCE,
        expiring_certifications: [
          { pilot_id: 32, pilot_name: 'Robin Vale', cert_type_id: 1, cert_type_name: 'Part 107', days_remaining: 22 },
        ],
      }),
    })
    renderWithProviders(<CompliancePage />, { role: 'admin' })
    const item = await screen.findByRole('button', { name: /Expiring Certification/ })
    expect(item).toHaveTextContent('Expiring Certification Robin Vale - Part 107 - 22 days remaining')
  })

  it('offers Generate Compliance Report only to a role that can generate reports', async () => {
    mockMount()
    renderWithProviders(<CompliancePage />, { role: 'supervisor' })
    expect(await screen.findByRole('button', { name: /Generate Compliance Report/ })).toBeInTheDocument()
  })

  it('hides Generate Compliance Report from a viewer', async () => {
    mockMount()
    renderWithProviders(<CompliancePage />, { role: 'viewer' })
    await screen.findByRole('heading', { name: 'Compliance Dashboard' })
    expect(screen.queryByRole('button', { name: /Generate Compliance Report/ })).toBeNull()
  })

  it('shows the failure fallback when /dashboard/compliance 500s', async () => {
    mockMount({ compliance: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }) })
    renderWithProviders(<CompliancePage />, { role: 'admin' })
    expect(await screen.findByText('Failed to load compliance data.')).toBeInTheDocument()
  })

  it('shows the cap reason under the score when an authority has expired', async () => {
    mockMount({
      compliance: () => HttpResponse.json({
        ...COMPLIANCE,
        compliance_score: 50,
        score_cap_reason: 'Capped at 50: 1 operating authority expired',
        expired_authorities: [
          { id: 1, title: 'Blanket public safety COA', identifier: '2026-WSA-1234', grounds_unit: true, days_remaining: -30 },
        ],
      }),
    })
    renderWithProviders(<CompliancePage />, { role: 'admin' })

    expect(await screen.findByText('Capped at 50: 1 operating authority expired')).toBeInTheDocument()
    // Grounding items outrank every other severity, so this is the first row.
    const attention = screen.getByText('Operating Authority Expired').closest('button')
    expect(within(attention).getByText('grounding')).toBeInTheDocument()
    expect(within(attention).getByText(/2026-WSA-1234/)).toBeInTheDocument()
  })

  it('treats a non-grounding expired authority as critical rather than grounding', async () => {
    mockMount({
      compliance: () => HttpResponse.json({
        ...COMPLIANCE,
        expired_authorities: [
          { id: 2, title: 'Night operations waiver', identifier: null, grounds_unit: false, days_remaining: -3 },
        ],
      }),
    })
    renderWithProviders(<CompliancePage />, { role: 'admin' })

    const row = await screen.findByText('Operating Authority Expired (restricted operations)')
    expect(within(row.closest('button')).getByText('critical')).toBeInTheDocument()
    expect(screen.queryByText('grounding')).toBeNull()
  })

  it('lists an expiring authority without capping the score', async () => {
    mockMount({
      compliance: () => HttpResponse.json({
        ...COMPLIANCE,
        expiring_authorities: [
          { id: 1, title: 'Blanket public safety COA', identifier: '2026-WSA-1234', grounds_unit: true, days_remaining: 45 },
        ],
      }),
    })
    renderWithProviders(<CompliancePage />, { role: 'admin' })

    expect(await screen.findByText('Operating Authority Expiring')).toBeInTheDocument()
    expect(screen.getByText(/45 days remaining/)).toBeInTheDocument()
  })

  describe('Requirements score', () => {
    it('shows the Requirements score next to the compliance score, which requirements data leaves unchanged', async () => {
      mockMount()
      server.use(http.get('/api/requirements/status', () => HttpResponse.json({ score: 0.95, requirements: [] })))
      renderWithProviders(<CompliancePage />, { role: 'admin' })
      const score = await screen.findByRole('figure', { name: 'Requirements score' })
      expect(within(score).getByText('95%')).toBeInTheDocument()
      // The compliance score is the payload's own value, not mixed with requirements.
      expect(screen.getByText('72')).toBeInTheDocument()
      expect(screen.getByText('Compliance Score')).toBeInTheDocument()
    })

    it('says No results yet when the Requirements score is null', async () => {
      mockMount()
      server.use(http.get('/api/requirements/status', () => HttpResponse.json({ score: null, requirements: [] })))
      renderWithProviders(<CompliancePage />, { role: 'admin' })
      const score = await screen.findByRole('figure', { name: 'Requirements score' })
      expect(within(score).getByText('No results yet')).toBeInTheDocument()
    })

    it('hides the Requirements score without requirements.view', async () => {
      let asked = false
      mockMount()
      server.use(http.get('/api/requirements/status', () => { asked = true; return HttpResponse.json({ score: 1, requirements: [] }) }))
      renderWithProviders(<CompliancePage />, { role: 'viewer', permissions: { 'requirements.view': 'no' } })
      expect(await screen.findByText('72')).toBeInTheDocument()
      expect(screen.queryByRole('figure', { name: 'Requirements score' })).toBeNull()
      expect(asked).toBe(false)
    })
  })
})
