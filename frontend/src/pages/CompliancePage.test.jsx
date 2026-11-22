import { describe, it, expect } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import { Route, Routes, useLocation } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import CompliancePage, { LegacyRequirementsRedirect } from './CompliancePage'

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
  pilots_out_of_standing: 2,
  requirements_active: 1,
  requirements_score: null,
  score_breakdown: [
    { area: 'Certifications', points_lost: 10, detail: '2 of 5 active pilots with an expired certification' },
    { area: 'Registrations', points_lost: 0, detail: '0 of 3 active vehicles with an expired registration' },
    { area: 'Maintenance', points_lost: 5, detail: '1 overdue maintenance task' },
    { area: 'Flight requirements', points_lost: 6, detail: '2 of 5 active pilots missed or lapsed on a flight requirement' },
  ],
}

function mockMount(overrides = {}) {
  const base = {
    compliance: () => HttpResponse.json(COMPLIANCE),
    ...overrides,
  }
  server.use(http.get('/api/dashboard/compliance', base.compliance))
}

function LocationProbe() {
  const location = useLocation()
  return <p data-testid="location">{location.pathname + location.search}</p>
}

const BASE_REQ = {
  description: null, recurring: true, window_start_day: null, window_end_day: null, span_length: null,
  span_unit: null, every_months: null, target_flights: null, model_mode: 'all', models: [], time_mode: 'any',
  window_start_time: null, window_end_time: null, purposes: [], pilot_ids: [], reminder_days: 7,
  start_date: '2026-10-01', end_date: null, active_changed_at: null, created_at: '2026-10-01T00:00:00',
  updated_at: '2026-10-01T00:00:00', current_period: null,
}
const MONTHLY = { ...BASE_REQ, id: 4, name: 'Monthly hour', period_type: 'calendar_month', target_minutes: 60, is_active: true }
const STATUS = {
  score: null,
  inactive_count: 0,
  requirements: [{
    requirement_id: 4, name: 'Monthly hour', period_type: 'calendar_month', target_minutes: 60, target_flights: null,
    model_mode: 'all', rolling: null, pending_periods: [],
    current_period: {
      start: '2026-11-01', end: '2026-11-30', days_left: 10, review_until: '2026-12-14',
      pilots: [{
        pilot_id: 1, pilot_name: 'Pat Pilot', status: 'met', totals: { '*': { minutes: 75, flights: 1 } }, met_by_model: {},
        excluded_no_takeoff: 0, unreviewed_in_period: 0, excused: false, excused_reason: null,
      }],
    },
  }],
}
const TEMPLATE = {
  id: 7, name: 'Night hour',
  settings: {
    name: 'Night hour', description: null, period_type: 'span', recurring: false, window_start_day: null,
    window_end_day: null, span_length: 2, span_unit: 'weeks', every_months: null, target_minutes: 60,
    target_flights: null, model_mode: 'all', models: [], time_mode: 'any', window_start_time: null,
    window_end_time: null, purposes: [], reminder_days: 3, is_active: true,
  },
  created_at: '2026-10-01T00:00:00', updated_at: '2026-10-01T00:00:00',
}

/** The requirements endpoints; returns the set of manager-only endpoints that were asked for. */
function mockRequirements({ templates = [] } = {}) {
  const asked = new Set()
  const seen = (name, body) => () => { asked.add(name); return HttpResponse.json(body) }
  server.use(
    http.get('/api/requirements', seen('requirements', [MONTHLY])),
    http.get('/api/requirements/status', seen('status', STATUS)),
    http.get('/api/requirements/history', seen('history', [])),
    http.get('/api/requirements/templates', seen('templates', templates)),
    http.get('/api/requirements/models', seen('models', [])),
    http.get('/api/requirements/settings', seen('settings', { grace_days: 14, fiscal_year_start_month: 10, emails_enabled: false })),
    http.get('/api/flights/purposes/list', seen('purposes', [])),
    http.get('/api/pilots/options', seen('pilots', [])),
    http.get('/api/settings', seen('unit settings', [])),
  )
  return asked
}

describe('CompliancePage', () => {
  it('renders without crashing', async () => {
    mockMount()
    renderWithProviders(<CompliancePage />, { role: 'admin' })
    expect(await screen.findByRole('heading', { name: 'Compliance', level: 1 })).toBeInTheDocument()
  })

  it('renders the compliance score and stat cards from a populated payload', async () => {
    mockMount()
    renderWithProviders(<CompliancePage />, { role: 'admin' })
    expect(await screen.findByRole('heading', { name: 'Compliance', level: 1 })).toBeInTheDocument()
    expect(await screen.findByText('72')).toBeInTheDocument()   // score circle
    expect(screen.getByText('Expired Certs')).toBeInTheDocument()
    // attention item built from expired certs
    expect(screen.getByText('Expired Certifications')).toBeInTheDocument()
  })

  it.each(['Out of Currency', 'Pilot Currency Status', 'Currency Compliance', 'Pilots Out of Currency'])(
    'has no currency text: %s', async (text) => {
      mockMount()
      renderWithProviders(<CompliancePage />, { role: 'admin' })
      await screen.findByText('72')
      expect(screen.queryByText(text)).toBeNull()
    })

  it('offers no Send currency reminders to a manager', async () => {
    mockMount()
    renderWithProviders(<CompliancePage />, { role: 'admin' })
    await screen.findByText('72')
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
    await screen.findByText('72')
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
  describe('Overview', () => {
    it('lists where the score lost points, leaving out areas that lost none', async () => {
      mockMount()
      renderWithProviders(<CompliancePage />, { role: 'admin' })
      const breakdown = await screen.findByRole('list', { name: 'Score breakdown' })
      const items = within(breakdown).getAllByRole('listitem')
      expect(items.map(item => item.textContent)).toEqual([
        'Certifications-10 points2 of 5 active pilots with an expired certification',
        'Maintenance-5 points1 overdue maintenance task',
        'Flight requirements-6 points2 of 5 active pilots missed or lapsed on a flight requirement',
      ])
      expect(screen.queryByText(/Deductions add up to more than 100/)).toBeNull()
    })

    it('says the deductions passed 100 when the score is 0', async () => {
      mockMount({ compliance: () => HttpResponse.json({ ...COMPLIANCE, compliance_score: 0 }) })
      renderWithProviders(<CompliancePage />, { role: 'admin' })
      expect(await screen.findByText('Deductions add up to more than 100, so the score stops at 0.')).toBeInTheDocument()
    })

    it('shows a Missed or lapsed card that opens the Flight Requirements tab', async () => {
      mockMount()
      const { user } = renderWithProviders(<><CompliancePage /><LocationProbe /></>, { role: 'viewer', route: '/compliance' })
      const card = await screen.findByRole('button', { name: /Missed or lapsed/ })
      expect(card).toHaveTextContent('2')
      await user.click(card)
      await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/compliance?tab=requirements'))
    })

    it('leaves out the Missed or lapsed card without requirements.view', async () => {
      mockMount()
      renderWithProviders(<CompliancePage />, { role: 'viewer', permissions: { 'requirements.view': 'no' } })
      await screen.findByText('72')
      expect(screen.queryByRole('button', { name: /Missed or lapsed/ })).toBeNull()
    })

    it('shows the This Period section', async () => {
      mockMount()
      renderWithProviders(<CompliancePage />, { role: 'viewer' })
      expect(await screen.findByRole('region', { name: 'This Period' })).toBeInTheDocument()
    })
  })

  describe('tabs', () => {
    const tabNames = () => screen.getAllByRole('tab').map(tab => tab.textContent)

    it('gives a viewer Overview and Flight Requirements, without Setup or manage requests', async () => {
      const asked = mockRequirements()
      mockMount()
      const { user } = renderWithProviders(<CompliancePage />, { role: 'viewer', route: '/compliance' })
      await screen.findByText('72')
      expect(tabNames()).toEqual(['Overview', 'Flight Requirements'])
      expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true')
      await user.click(screen.getByRole('tab', { name: 'Flight Requirements' }))
      const row = (await within(await screen.findByRole('region', { name: 'Requirements' })).findByText('Monthly hour')).closest('li')
      expect(within(row).getByRole('link', { name: 'Pat Pilot' })).toHaveAttribute('href', '/pilots/1')
      for (const name of [/New requirement/, /^Edit /, /^Switch (on|off) /, /^Delete /]) {
        expect(screen.queryByRole('button', { name })).toBeNull()
      }
      expect(asked.has('templates')).toBe(false)
      expect(asked.has('models')).toBe(false)
      expect(asked.has('settings')).toBe(false)
    })

    it('gives a manager the Setup tab with templates and requirement settings', async () => {
      mockRequirements()
      mockMount()
      renderWithProviders(<CompliancePage />, { role: 'supervisor', route: '/compliance?tab=setup' })
      expect(await screen.findByRole('heading', { name: 'Templates' })).toBeInTheDocument()
      expect(screen.getByRole('heading', { name: 'Requirement Settings' })).toBeInTheDocument()
      expect(tabNames()).toEqual(['Overview', 'Flight Requirements', 'Setup'])
      expect(screen.getByRole('tab', { name: 'Setup' })).toHaveAttribute('aria-selected', 'true')
      expect(screen.queryByText('72')).toBeNull()
    })

    it('opens the Flight Requirements tab from ?tab=requirements with manage controls for a manager', async () => {
      mockRequirements()
      mockMount()
      renderWithProviders(<CompliancePage />, { role: 'supervisor', route: '/compliance?tab=requirements' })
      expect(await screen.findByRole('button', { name: 'New requirement' })).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: 'Flight Requirements' })).toHaveAttribute('aria-selected', 'true')
      expect(screen.queryByRole('heading', { name: 'Templates' })).toBeNull()
    })

    it('shows the Overview for ?tab=setup without requirements.manage', async () => {
      mockRequirements()
      mockMount()
      renderWithProviders(<CompliancePage />, { role: 'viewer', route: '/compliance?tab=setup' })
      expect(await screen.findByText('72')).toBeInTheDocument()
      expect(screen.queryByRole('heading', { name: 'Templates' })).toBeNull()
      expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true')
    })

    it('shows only the Overview without requirements.view', async () => {
      mockMount()
      renderWithProviders(<CompliancePage />, { role: 'viewer', route: '/compliance?tab=requirements', permissions: { 'requirements.view': 'no' } })
      expect(await screen.findByText('72')).toBeInTheDocument()
      expect(screen.queryByRole('tab', { name: 'Flight Requirements' })).toBeNull()
    })

    it('puts the chosen tab in the address', async () => {
      mockRequirements()
      mockMount()
      const { user } = renderWithProviders(<><CompliancePage /><LocationProbe /></>, { role: 'supervisor', route: '/compliance' })
      await screen.findByText('72')
      await user.click(screen.getByRole('tab', { name: 'Setup' }))
      await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/compliance?tab=setup'))
      await user.click(screen.getByRole('tab', { name: 'Overview' }))
      await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/compliance?tab=overview'))
    })

    it('opens a template from Setup as a new requirement on the Flight Requirements tab', async () => {
      mockRequirements({ templates: [TEMPLATE] })
      mockMount()
      const { user } = renderWithProviders(<CompliancePage />, { role: 'supervisor', route: '/compliance?tab=setup' })
      await user.click(await screen.findByRole('button', { name: 'New from template Night hour' }))
      expect(await screen.findByLabelText('Name')).toHaveValue('Night hour')
      expect(screen.getByRole('tab', { name: 'Flight Requirements' })).toHaveAttribute('aria-selected', 'true')
      expect(screen.getByLabelText('Starts')).toHaveValue('')
    })

    it('sends /requirements to the Flight Requirements tab', async () => {
      mockMount()
      renderWithProviders(
        <>
          <Routes>
            <Route path="/requirements" element={<LegacyRequirementsRedirect />} />
            <Route path="/compliance" element={<p>Compliance page</p>} />
          </Routes>
          <LocationProbe />
        </>,
        { role: 'viewer', route: '/requirements' },
      )
      expect(await screen.findByText('Compliance page')).toBeInTheDocument()
      expect(screen.getByTestId('location')).toHaveTextContent('/compliance?tab=requirements')
    })
  })
})
