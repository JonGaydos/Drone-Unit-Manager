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
  pilots_lapsed: 1,
  pilots_current: 4,
  total_pilots: 5,
  total_vehicles: 3,
  currency_rules_active: 1,
  pilot_currency_status: [
    {
      pilot_id: 5, pilot_name: 'Ada Lovelace', email: 'ada@unit.gov', is_current: false,
      earliest_expires_date: null,
      rules: [{ rule_id: 1, rule_name: 'Quarterly', actual_hours: 1, required_hours: 5, actual_flights: 1, required_flights: 3, period_days: 90, is_current: false }],
    },
    {
      pilot_id: 6, pilot_name: 'Grace Hopper', email: 'grace@unit.gov', is_current: true,
      earliest_expires_date: '2026-12-31',
      rules: [{ rule_id: 1, rule_name: 'Quarterly', actual_hours: 9, required_hours: 5, actual_flights: 4, required_flights: 3, period_days: 90, is_current: true }],
    },
  ],
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

  it('renders lapsed currency rows without rendering raw rule objects', async () => {
    mockMount()
    renderWithProviders(<CompliancePage />, { role: 'admin' })
    expect(await screen.findByText('Ada Lovelace')).toBeInTheDocument()
    // LAPSED badge for the out-of-currency pilot
    expect(screen.getByText('LAPSED')).toBeInTheDocument()
    // Rule details rendered as text, not [object Object]
    expect(screen.getByText(/Quarterly: 1\/5 hours flown/)).toBeInTheDocument()
    expect(screen.queryByText(/\[object Object\]/)).toBeNull()
  })

  it('shows the failure fallback when /dashboard/compliance 500s', async () => {
    mockMount({ compliance: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }) })
    renderWithProviders(<CompliancePage />, { role: 'admin' })
    expect(await screen.findByText('Failed to load compliance data.')).toBeInTheDocument()
  })

  it('filters the currency section to lapsed only', async () => {
    mockMount()
    const { user } = renderWithProviders(<CompliancePage />, { role: 'admin' })
    await screen.findByText('Ada Lovelace')

    // Default view (lapsed + expiring 30d) lists Ada; Grace expires far out so is hidden.
    expect(screen.queryByText('Grace Hopper')).toBeNull()

    // "All pilots" surfaces the current pilot too.
    const section = document.getElementById('currency')
    await user.selectOptions(within(section).getByRole('combobox'), 'all')
    expect(await screen.findByText('Grace Hopper')).toBeInTheDocument()
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

  // The tile answers "what fraction of pilots are current", and it has to
  // refuse the question when nothing defines what current means. 100% against
  // no rule reads as a pass the unit has not earned.
  describe('currency compliance tile', () => {
    // The label sits in its own div inside the tile, so closest('div') would
    // return that label, not the card holding the number.
    const tile = () => screen.getByText('Currency Compliance').parentElement

    it('shows a dash and says so when no currency rule is configured', async () => {
      mockMount({ compliance: () => HttpResponse.json({ ...COMPLIANCE, currency_rules_active: 0 }) })
      renderWithProviders(<CompliancePage />, { role: 'admin' })

      await screen.findByRole('heading', { name: 'Compliance Dashboard' })
      expect(within(tile()).getByText(String.fromCharCode(8212))).toBeInTheDocument()
      expect(within(tile()).getByText('no rules')).toBeInTheDocument()
    })

    it('shows the percentage of pilots current when rules exist', async () => {
      mockMount({ compliance: () => HttpResponse.json({
        ...COMPLIANCE, currency_rules_active: 1, pilots_current: 3, total_pilots: 4 }) })
      renderWithProviders(<CompliancePage />, { role: 'admin' })

      await screen.findByRole('heading', { name: 'Compliance Dashboard' })
      expect(within(tile()).getByText('75%')).toBeInTheDocument()
    })

    it('reads 100% rather than dividing by zero when the unit has no pilots', async () => {
      mockMount({ compliance: () => HttpResponse.json({
        ...COMPLIANCE, currency_rules_active: 1, pilots_current: 0, total_pilots: 0,
        pilot_currency_status: [] }) })
      renderWithProviders(<CompliancePage />, { role: 'admin' })

      await screen.findByRole('heading', { name: 'Compliance Dashboard' })
      expect(within(tile()).getByText('100%')).toBeInTheDocument()
    })
  })
})
