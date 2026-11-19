import { describe, it, expect } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import PilotRequirementsCard from './PilotRequirementsCard'

const PERIOD = { start: '2026-11-01', end: '2026-11-30', days_left: 12, review_until: '2026-12-14' }

const CURRENT = {
  requirement_id: 1, name: 'Monthly hour', pilot_id: 7, pilot_name: 'Pat Pilot', status: 'on_track',
  totals: { '*': { minutes: 25, flights: 2 } }, met_by_model: { '*': false },
  excluded_no_takeoff: 2, unreviewed_in_period: 3, excused: false, excused_reason: null, period: PERIOD,
}

const HISTORY = [
  {
    result_id: 21, requirement_id: 1, name: 'Monthly hour', period_start: '2026-09-01', period_end: '2026-09-30',
    status: 'missed', totals: { '*': { minutes: 40, flights: 3 } }, target_snapshot: { target_minutes: 60 },
    excused: false, excused_by_id: null, excused_reason: null, saved_at: '2026-10-15T06:00:00',
  },
  {
    result_id: 20, requirement_id: 1, name: 'Monthly hour', period_start: '2026-08-01', period_end: '2026-08-31',
    status: 'excused', totals: { '*': { minutes: 0, flights: 0 } }, target_snapshot: { target_minutes: 60 },
    excused: true, excused_by_id: null, excused_reason: 'Added after the period started', saved_at: '2026-09-15T06:00:00',
  },
  {
    result_id: 19, requirement_id: 1, name: 'Monthly hour', period_start: '2026-07-01', period_end: '2026-07-31',
    status: 'excused', totals: { '*': { minutes: 0, flights: 0 } }, target_snapshot: { target_minutes: 60 },
    excused: true, excused_by_id: 2, excused_reason: 'On leave', saved_at: '2026-08-15T06:00:00',
  },
]

function mock({ current = [CURRENT], pending = [], history = HISTORY, flags = {} } = {}) {
  server.use(
    http.get('/api/requirements/pilots/:id', () => HttpResponse.json({ pilot_id: 7, current, pending, history })),
    http.get('/api/requirements', () => HttpResponse.json([{ id: 1, name: 'Monthly hour', target_minutes: 60, target_flights: null }])),
    http.get('/api/requirements/flags', () => HttpResponse.json(flags)),
  )
}

const render = (role = 'supervisor', permissions) =>
  renderWithProviders(<PilotRequirementsCard pilotId="7" />, { role, permissions })

describe('PilotRequirementsCard', () => {
  it('shows current progress with the flights left out and awaiting review', async () => {
    mock()
    render()
    const current = await screen.findByRole('region', { name: 'This period' })
    expect(within(current).getByText('Monthly hour')).toBeInTheDocument()
    expect(within(current).getByText('25/60m')).toBeInTheDocument()
    expect(within(current).getByText('2 flights left out: no takeoff time')).toBeInTheDocument()
    expect(within(current).getByText('3 flights awaiting review')).toBeInTheDocument()
    expect(within(current).getByText('On track')).toBeInTheDocument()
  })

  it('leaves out the left-out and awaiting-review lines when both are zero', async () => {
    mock({ current: [{ ...CURRENT, excluded_no_takeoff: 0, unreviewed_in_period: 0 }] })
    render()
    await screen.findByRole('region', { name: 'This period' })
    expect(screen.queryByText(/left out/)).toBeNull()
    expect(screen.queryByText(/awaiting review/)).toBeNull()
  })

  it('lists saved periods in a history table, labelling automatic and manual excusals', async () => {
    mock()
    render()
    const table = await screen.findByRole('table', { name: 'Requirement history' })
    expect(within(table).getByText('40/60m')).toBeInTheDocument()
    expect(within(table).getByText('Missed')).toBeInTheDocument()
    expect(within(table).getByText('Excused automatically: Added after the period started')).toBeInTheDocument()
    expect(within(table).getByText('Excused: On leave')).toBeInTheDocument()
  })

  it('shows the Missed requirement badge while a miss is flagged', async () => {
    mock({ flags: { 7: [{ result_id: 21, requirement_id: 1, name: 'Monthly hour', period_start: '2026-09-01', period_end: '2026-09-30' }] } })
    render()
    expect(await screen.findByText('Missed requirement')).toBeInTheDocument()
  })

  it('excuses a pilot for a period with a reason and reloads', async () => {
    let sent = null
    mock()
    server.use(http.post('/api/requirements/:id/excuse', async ({ request, params }) => {
      sent = { id: params.id, body: await request.json() }
      return HttpResponse.json({ ok: true })
    }))
    const { user } = render()
    const table = await screen.findByRole('table', { name: 'Requirement history' })
    await user.click(within(table).getByRole('button', { name: /^Excuse Monthly hour, Sep 1, 2026/ }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('Reason (optional)'), 'Medical leave')
    await user.click(within(dialog).getByRole('button', { name: 'Excuse' }))
    await waitFor(() => expect(sent).not.toBeNull())
    expect(sent).toEqual({ id: '1', body: { pilot_id: 7, period_start: '2026-09-01', excused: true, reason: 'Medical leave' } })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('shows the server message when an excusal is refused', async () => {
    mock()
    server.use(http.post('/api/requirements/:id/excuse', () =>
      HttpResponse.json({ detail: 'That period is closed and has no saved result for this pilot' }, { status: 422 })))
    const { user } = render()
    const current = await screen.findByRole('region', { name: 'This period' })
    await user.click(within(current).getByRole('button', { name: /^Excuse Monthly hour/ }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Excuse' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('That period is closed and has no saved result for this pilot')
  })

  it('un-excuses an excused period without a reason', async () => {
    let sent = null
    mock()
    server.use(http.post('/api/requirements/:id/excuse', async ({ request }) => {
      sent = await request.json()
      return HttpResponse.json({ ok: true })
    }))
    const { user } = render()
    const table = await screen.findByRole('table', { name: 'Requirement history' })
    await user.click(within(table).getByRole('button', { name: /^Un-excuse Monthly hour, Jul 1, 2026/ }))
    await waitFor(() => expect(sent).toEqual({ pilot_id: 7, period_start: '2026-07-01', excused: false }))
  })

  it('hides Excuse and Un-excuse without requirements.excuse', async () => {
    mock()
    render('pilot')
    await screen.findByRole('table', { name: 'Requirement history' })
    expect(screen.queryByRole('button', { name: /xcuse/ })).toBeNull()
  })

  it('downloads a requirement CSV with reports.export and hides it without', async () => {
    mock()
    const { unmount } = render('supervisor')
    expect(await screen.findByRole('button', { name: 'Download Monthly hour results as CSV' })).toBeInTheDocument()
    unmount()
    mock()
    render('supervisor', { 'reports.export': 'no' })
    await screen.findByRole('table', { name: 'Requirement history' })
    expect(screen.queryByRole('button', { name: /as CSV/ })).toBeNull()
  })

  it('renders nothing when the pilot has no requirements and no history', async () => {
    let asked = false
    mock({ current: [], history: [] })
    server.use(http.get('/api/requirements/pilots/:id', () => {
      asked = true
      return HttpResponse.json({ pilot_id: 7, current: [], pending: [], history: [] })
    }))
    render()
    await waitFor(() => expect(asked).toBe(true))
    expect(screen.queryByText('Flight Requirements')).toBeNull()
  })
})
