import { describe, it, expect } from 'vitest'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import RequirementsTab from './RequirementsTab'
import { todayLocal } from '@/lib/utils'

const REQ = {
  id: 4, name: 'Quarterly models', description: null, period_type: 'calendar_quarter', recurring: true,
  window_start_day: null, window_end_day: null, span_length: null, span_unit: null, every_months: null,
  target_minutes: 15, target_flights: null, model_mode: 'each', models: ['X10', 'X2E'], time_mode: 'any',
  window_start_time: null, window_end_time: null, purposes: [], pilot_ids: [1], reminder_days: 7,
  is_active: true, start_date: '2026-10-01', end_date: null, active_changed_at: null,
  created_at: '2026-10-01T00:00:00', updated_at: '2026-10-01T00:00:00', current_period: null,
}
const OFF = { ...REQ, id: 5, name: 'Old monthly', period_type: 'calendar_month', is_active: false, target_minutes: 60 }
const TEMPLATE = {
  id: 7, name: 'Night hour',
  settings: {
    name: 'Night hour', description: null, period_type: 'span', recurring: false, window_start_day: null,
    window_end_day: null, span_length: 2, span_unit: 'weeks', every_months: null, target_minutes: 60,
    target_flights: null, model_mode: 'all', models: [], time_mode: 'night', window_start_time: null,
    window_end_time: null, purposes: [], reminder_days: 3, is_active: true,
  },
  created_at: '2026-10-01T00:00:00', updated_at: '2026-10-01T00:00:00',
}

function mock({ settings = [{ key: 'org_default_lat', value: '1.5' }, { key: 'org_default_lon', value: '2.5' }], requirements = [REQ, OFF] } = {}) {
  const calls = []
  const record = (method) => async ({ request, params }) => {
    const body = method === 'DELETE' ? null : await request.json()
    calls.push({ method, url: new URL(request.url).pathname, body, params })
    return HttpResponse.json({ ok: true, id: 99, ...(body || {}) })
  }
  server.use(
    http.get('/api/requirements', () => HttpResponse.json(requirements)),
    http.get('/api/requirements/templates', () => HttpResponse.json([TEMPLATE])),
    http.get('/api/requirements/models', () => HttpResponse.json([{ name: 'X10', aircraft: 4, retired: 0 }, { name: 'X2E', aircraft: 2, retired: 0 }])),
    http.get('/api/requirements/settings', () => HttpResponse.json({ grace_days: 14, fiscal_year_start_month: 10, emails_enabled: false })),
    http.get('/api/settings', () => HttpResponse.json(settings)),
    http.get('/api/flights/purposes/list', () => HttpResponse.json([{ id: 1, name: 'Patrol', is_active: true, sort_order: 0 }])),
    http.get('/api/pilots/options', () => HttpResponse.json([{ id: 1, full_name: 'Pat Pilot', badge_number: 'B-1', status: 'active' }])),
    http.post('/api/requirements', record('POST')),
    http.patch('/api/requirements/:id', record('PATCH')),
    http.delete('/api/requirements/:id', record('DELETE')),
    http.post('/api/requirements/templates', record('POST')),
    http.patch('/api/requirements/templates/:id', record('PATCH')),
    http.delete('/api/requirements/templates/:id', record('DELETE')),
    http.put('/api/requirements/settings', record('PUT')),
  )
  return calls
}

function renderTab() {
  return renderWithProviders(<RequirementsTab />, { role: 'supervisor' })
}

describe('RequirementsTab', () => {
  it('lists requirements with period, target and status', async () => {
    mock()
    renderTab()
    const row = (await screen.findByText('Quarterly models')).closest('li')
    expect(within(row).getByText('Calendar quarter, recurring')).toBeInTheDocument()
    expect(within(row).getByText('15 min')).toBeInTheDocument()
    expect(within(row).getByText('Active')).toBeInTheDocument()
    const off = screen.getByText('Old monthly').closest('li')
    expect(within(off).getByText('Inactive')).toBeInTheDocument()
  })

  it('creates a requirement', async () => {
    const calls = mock()
    const { user } = renderTab()
    await screen.findByText('Quarterly models')
    await user.click(screen.getByRole('button', { name: 'New requirement' }))
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Monthly hour' } })
    fireEvent.change(screen.getByLabelText('Hours'), { target: { value: '1' } })
    fireEvent.change(screen.getByLabelText('Starts'), { target: { value: '2026-11-01' } })
    await user.click(screen.getByRole('button', { name: 'Save requirement' }))
    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0]).toMatchObject({ method: 'POST', url: '/api/requirements' })
    expect(calls[0].body).toMatchObject({
      name: 'Monthly hour', period_type: 'calendar_month', recurring: true, target_minutes: 60,
      model_mode: 'all', models: [], pilot_ids: [], start_date: '2026-11-01', end_date: null,
    })
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Save requirement' })).toBeNull())
  })

  it('edits a requirement with a PATCH', async () => {
    const calls = mock()
    const { user } = renderTab()
    await user.click(await screen.findByRole('button', { name: 'Edit Quarterly models' }))
    expect(screen.getByLabelText('Name')).toHaveValue('Quarterly models')
    await user.click(screen.getByRole('button', { name: 'Save requirement' }))
    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0]).toMatchObject({ method: 'PATCH', url: '/api/requirements/4' })
    expect(calls[0].body).toMatchObject({ model_mode: 'each', models: ['X10', 'X2E'], pilot_ids: [1] })
  })

  it('warns about a past start only on a new requirement, not when editing one', async () => {
    mock({ requirements: [{ ...REQ, start_date: '2020-01-01' }] })
    const { user } = renderTab()
    await user.click(await screen.findByRole('button', { name: 'Edit Quarterly models' }))
    expect(screen.getByLabelText('Starts')).toHaveValue('2020-01-01')
    expect(screen.queryByText(/starts in the past/)).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    await user.click(screen.getByRole('button', { name: 'New requirement' }))
    fireEvent.change(screen.getByLabelText('Starts'), { target: { value: '2020-01-01' } })
    expect(screen.getByText(/starts in the past/)).toBeInTheDocument()
  })

  it('duplicates into a prefilled form named "Copy of ..." without saving', async () => {
    const calls = mock()
    const { user } = renderTab()
    await user.click(await screen.findByRole('button', { name: 'Duplicate Quarterly models' }))
    expect(screen.getByLabelText('Name')).toHaveValue('Copy of Quarterly models')
    expect(screen.getByLabelText('Minutes')).toHaveValue(15)
    expect(screen.getByRole('radio', { name: 'Selected pilots' })).toBeChecked()
    expect(calls).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Save requirement' }))
    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0]).toMatchObject({ method: 'POST', url: '/api/requirements' })
    expect(calls[0].body.name).toBe('Copy of Quarterly models')
    expect(calls[0].body.start_date).toBe(todayLocal())
  })

  it('downloads a requirement\'s results as CSV with reports.export, and hides it without', async () => {
    let asked = null
    mock()
    server.use(http.get('/api/export/requirements/:id/csv', ({ request, params }) => {
      asked = { id: params.id, pilot: new URL(request.url).searchParams.get('pilot_id') }
      return new HttpResponse('Requirement\n', { headers: { 'Content-Type': 'text/csv' } })
    }))
    globalThis.URL.createObjectURL ??= () => 'blob:csv'
    globalThis.URL.revokeObjectURL ??= () => {}
    const { user, unmount } = renderTab()
    await user.click(await screen.findByRole('button', { name: 'Download Quarterly models results as CSV' }))
    await waitFor(() => expect(asked).toEqual({ id: '4', pilot: null }))
    unmount()
    mock()
    renderWithProviders(<RequirementsTab />, { role: 'supervisor', permissions: { 'reports.export': 'no' } })
    await screen.findByText('Quarterly models')
    expect(screen.queryByRole('button', { name: /as CSV/ })).toBeNull()
  })

  it('shows why a requirement with history cannot be deleted', async () => {
    mock()
    server.use(http.delete('/api/requirements/:id', () =>
      HttpResponse.json({ detail: 'This requirement has saved results. Switch it off instead.' }, { status: 409 })))
    const { user } = renderTab()
    await user.click(await screen.findByRole('button', { name: 'Delete Quarterly models' }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete' }))
    expect(await screen.findByText('This requirement has saved results. Switch it off instead.')).toBeInTheDocument()
  })

  it('deletes a requirement after confirming', async () => {
    const calls = mock()
    const { user } = renderTab()
    await user.click(await screen.findByRole('button', { name: 'Delete Old monthly' }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0]).toMatchObject({ method: 'DELETE', url: '/api/requirements/5' })
  })

  it('opens a template passed in the location state as a new requirement, without dates or pilots', async () => {
    mock()
    renderWithProviders(<RequirementsTab />, {
      role: 'supervisor', route: { pathname: '/compliance', search: '?tab=requirements', state: { template: TEMPLATE } },
    })
    expect(await screen.findByLabelText('Name')).toHaveValue('Night hour')
    expect(screen.getByLabelText('Period')).toHaveValue('span')
    expect(screen.getByLabelText('Length')).toHaveValue(2)
    expect(screen.getByRole('radio', { name: /Night/ })).toBeChecked()
    expect(screen.getByLabelText('Starts')).toHaveValue('')
    expect(screen.getByRole('radio', { name: 'All active pilots' })).toBeChecked()
  })

  it('leaves templates and requirement settings to the Setup tab', async () => {
    mock()
    renderTab()
    await screen.findByText('Quarterly models')
    expect(screen.queryByRole('heading', { name: 'Templates' })).toBeNull()
    expect(screen.queryByRole('heading', { name: 'Requirement Settings' })).toBeNull()
  })

  it('shows a rolling requirement with its window and each pilot\'s standing', async () => {
    mock({ requirements: [{ ...REQ, period_type: 'rolling', recurring: false, span_length: 90, span_unit: 'days' }] })
    server.use(http.get('/api/requirements/status', () => HttpResponse.json({
      score: null, inactive_count: 0,
      requirements: [{
        requirement_id: 4, name: 'Quarterly models', period_type: 'rolling', target_minutes: 15, target_flights: null,
        model_mode: 'all', current_period: null, pending_periods: [],
        rolling: {
          window_start: '2026-08-23', window_end: '2026-11-20',
          pilots: [{
            pilot_id: 1, pilot_name: 'Pat Pilot', status: 'current', totals: { '*': { minutes: 20, flights: 1 } },
            met_by_model: { '*': true }, lapse_date: '2026-12-03', excused_until: null, excluded_no_takeoff: 0, unreviewed_in_window: 0,
          }],
        },
      }],
    })))
    renderTab()
    const row = (await screen.findByText('Quarterly models')).closest('li')
    expect(within(row).getByText('Rolling 90 days')).toBeInTheDocument()
    expect(await within(row).findByText('1 current, 0 lapsed')).toBeInTheDocument()
    expect(within(row).getByText('lapses on Dec 3, 2026')).toBeInTheDocument()
  })

  it('saves a requirement as a template', async () => {
    const calls = mock()
    const { user } = renderTab()
    await user.click(await screen.findByRole('button', { name: 'Save Quarterly models as a template' }))
    const dialog = screen.getByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('Template name'), { target: { value: 'Each model' } })
    await user.click(within(dialog).getByRole('button', { name: 'Save template' }))
    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0]).toMatchObject({ method: 'POST', url: '/api/requirements/templates' })
    expect(calls[0].body.name).toBe('Each model')
    expect(calls[0].body.settings).toMatchObject({ name: 'Quarterly models', model_mode: 'each', models: ['X10', 'X2E'] })
    expect(calls[0].body.settings).not.toHaveProperty('start_date')
    expect(calls[0].body.settings).not.toHaveProperty('pilot_ids')
    expect(calls[0].body.settings).not.toHaveProperty('end_date')
  })

  it('disables Night when the unit location is not set', async () => {
    mock({ settings: [{ key: 'org_default_lat', value: '' }, { key: 'org_default_lon', value: '' }] })
    const { user } = renderTab()
    await screen.findByText('Quarterly models')
    await user.click(screen.getByRole('button', { name: 'New requirement' }))
    await waitFor(() => expect(screen.getByRole('radio', { name: /Night/ })).toBeDisabled())
  })

  it('switches a requirement off after confirming, then refreshes the list', async () => {
    const calls = mock()
    let listed = 0
    server.use(http.get('/api/requirements', () => { listed += 1; return HttpResponse.json([REQ, OFF]) }))
    const { user } = renderTab()
    await user.click(await screen.findByRole('button', { name: 'Switch off Quarterly models' }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText(/stops tracking progress/)).toBeInTheDocument()
    expect(within(dialog).getByText(/recorded as excused/)).toBeInTheDocument()
    expect(calls).toHaveLength(0)
    await user.click(within(dialog).getByRole('button', { name: 'Switch off' }))
    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0]).toMatchObject({ method: 'PATCH', url: '/api/requirements/4', body: { is_active: false } })
    expect(await screen.findByText('Requirement switched off')).toBeInTheDocument()
    await waitFor(() => expect(listed).toBe(2))
  })

  it('keeps a requirement on when switching off is cancelled', async () => {
    const calls = mock()
    const { user } = renderTab()
    await user.click(await screen.findByRole('button', { name: 'Switch off Quarterly models' }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }))
    expect(calls).toHaveLength(0)
  })

  it('switches a requirement on in one click', async () => {
    const calls = mock()
    const { user } = renderTab()
    await user.click(await screen.findByRole('button', { name: 'Switch on Old monthly' }))
    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0]).toMatchObject({ method: 'PATCH', url: '/api/requirements/5', body: { is_active: true } })
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(await screen.findByText('Requirement switched on')).toBeInTheDocument()
  })
})
