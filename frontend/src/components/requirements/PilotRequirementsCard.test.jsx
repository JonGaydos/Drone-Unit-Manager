import { describe, it, expect, vi } from 'vitest'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
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

function mock({ current = [CURRENT], pending = [], history = HISTORY, flags = {}, rolling = [], lapses = [] } = {}) {
  server.use(
    http.get('/api/requirements/pilots/:id', () => HttpResponse.json({ pilot_id: 7, current, pending, history, rolling, lapses })),
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
    expect(within(current).getByText('25m/1h')).toBeInTheDocument()
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
    expect(within(table).getByText('40m/1h')).toBeInTheDocument()
    expect(within(table).getByText('Missed')).toBeInTheDocument()
    expect(within(table).getByText('Excused automatically: Added after the period started')).toBeInTheDocument()
    expect(within(table).getByText('Excused: On leave')).toBeInTheDocument()
  })

  it('shows the Missed requirement badge while a miss is flagged', async () => {
    mock({ flags: { 7: [{ kind: 'missed', result_id: 21, requirement_id: 1, name: 'Monthly hour', period_start: '2026-09-01', period_end: '2026-09-30' }] } })
    render()
    expect(await screen.findByText('Missed requirement')).toBeInTheDocument()
  })

  it('excuses a pilot for a period with a reason, reloads and tells the page', async () => {
    let sent = null
    let reads = 0
    const changed = vi.fn()
    mock()
    server.use(http.get('/api/requirements/pilots/:id', () => {
      reads += 1
      return HttpResponse.json({ pilot_id: 7, current: [CURRENT], pending: [], history: HISTORY })
    }))
    server.use(http.post('/api/requirements/:id/excuse', async ({ request, params }) => {
      sent = { id: params.id, body: await request.json() }
      return HttpResponse.json({ ok: true })
    }))
    const { user } = renderWithProviders(<PilotRequirementsCard pilotId="7" onChange={changed} />, { role: 'supervisor' })
    const table = await screen.findByRole('table', { name: 'Requirement history' })
    expect(reads).toBe(1)
    await user.click(within(table).getByRole('button', { name: /^Excuse Monthly hour, Sep 1, 2026/ }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('Reason (optional)'), 'Medical leave')
    await user.click(within(dialog).getByRole('button', { name: 'Excuse' }))
    await waitFor(() => expect(sent).not.toBeNull())
    expect(sent).toEqual({ id: '1', body: { pilot_id: 7, period_start: '2026-09-01', excused: true, reason: 'Medical leave' } })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(reads).toBe(2))
    expect(changed).toHaveBeenCalledTimes(1)
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

  it('tells the page after an un-excusal too', async () => {
    const changed = vi.fn()
    mock()
    server.use(http.post('/api/requirements/:id/excuse', () => HttpResponse.json({ ok: true })))
    const { user } = renderWithProviders(<PilotRequirementsCard pilotId="7" onChange={changed} />, { role: 'supervisor' })
    const table = await screen.findByRole('table', { name: 'Requirement history' })
    await user.click(within(table).getByRole('button', { name: /^Un-excuse Monthly hour, Jul 1, 2026/ }))
    await waitFor(() => expect(changed).toHaveBeenCalledTimes(1))
  })

  it('hides Excuse and Un-excuse without requirements.excuse', async () => {
    mock()
    render('pilot')
    await screen.findByRole('table', { name: 'Requirement history' })
    expect(screen.queryByRole('button', { name: /xcuse/ })).toBeNull()
  })

  it('downloads this pilot\'s history of a requirement as CSV with reports.export, and hides it without', async () => {
    let asked = null
    mock()
    server.use(http.get('/api/export/requirements/:id/csv', ({ request, params }) => {
      asked = { id: params.id, pilot: new URL(request.url).searchParams.get('pilot_id') }
      return new HttpResponse('Requirement\n', { headers: { 'Content-Type': 'text/csv' } })
    }))
    globalThis.URL.createObjectURL ??= () => 'blob:csv'
    globalThis.URL.revokeObjectURL ??= () => {}
    const { user, unmount } = render('supervisor')
    const button = await screen.findByRole('button', { name: 'Download Monthly hour history as CSV' })
    expect(button).toHaveTextContent('Download CSV')
    expect(screen.queryByText(/all pilots/)).toBeNull()
    await user.click(button)
    await waitFor(() => expect(asked).toEqual({ id: '1', pilot: '7' }))
    unmount()
    mock()
    render('supervisor', { 'reports.export': 'no' })
    await screen.findByRole('table', { name: 'Requirement history' })
    expect(screen.queryByRole('button', { name: /as CSV/ })).toBeNull()
  })

  it('hides Un-excuse on a period saved while the requirement was switched off', async () => {
    const off = {
      ...HISTORY[1], result_id: 18, period_start: '2026-06-01', period_end: '2026-06-30',
      excused_reason: 'Requirement was switched off', switched_off: true,
    }
    mock({ history: [...HISTORY, off] })
    render()
    const table = await screen.findByRole('table', { name: 'Requirement history' })
    expect(within(table).getByRole('button', { name: /^Un-excuse Monthly hour, Jul 1, 2026/ })).toBeInTheDocument()
    expect(within(table).queryByRole('button', { name: /^Un-excuse Monthly hour, Jun 1, 2026/ })).toBeNull()
  })

  it('lets an admin recalculate a saved period after confirming, then reloads', async () => {
    let sent = null
    let reads = 0
    mock()
    server.use(http.get('/api/requirements/pilots/:id', () => {
      reads += 1
      return HttpResponse.json({ pilot_id: 7, current: [CURRENT], pending: [], history: HISTORY })
    }))
    server.use(http.post('/api/requirements/:id/recalculate', async ({ request, params }) => {
      sent = { id: params.id, body: await request.json() }
      return HttpResponse.json({ recalculated: 3 })
    }))
    const { user } = render('admin')
    const table = await screen.findByRole('table', { name: 'Requirement history' })
    await user.click(within(table).getByRole('button', { name: 'Recalculate Monthly hour, Sep 1, 2026 to Sep 30, 2026' }))
    const dialog = await screen.findByRole('dialog')
    expect(sent).toBeNull()
    await user.click(within(dialog).getByRole('button', { name: 'Recalculate' }))
    await waitFor(() => expect(sent).toEqual({ id: '1', body: { period_start: '2026-09-01' } }))
    await waitFor(() => expect(reads).toBe(2))
  })

  it('hides Recalculate from everyone but admins', async () => {
    mock()
    render('supervisor')
    await screen.findByRole('table', { name: 'Requirement history' })
    expect(screen.queryByRole('button', { name: /^Recalculate/ })).toBeNull()
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
  describe('rolling requirements', () => {
    const ROLLING = {
      requirement_id: 2, name: 'Ninety-day hour', pilot_id: 7, pilot_name: 'Pat Pilot', status: 'current',
      totals: { '*': { minutes: 75, flights: 2 } }, met_by_model: { '*': true }, lapse_date: '2026-12-03',
      excused_until: null, excluded_no_takeoff: 0, unreviewed_in_window: 0,
      window_start: '2026-08-23', window_end: '2026-11-20',
    }
    const LAPSES = [
      { lapse_id: 4, requirement_id: 2, name: 'Ninety-day hour', lapsed_on: '2026-11-02', recovered_on: null },
      { lapse_id: 3, requirement_id: 2, name: 'Ninety-day hour', lapsed_on: '2026-06-10', recovered_on: '2026-06-21' },
    ]

    it('shows the window and the date the pilot would lapse', async () => {
      mock({ current: [], history: [], rolling: [ROLLING] })
      render()
      const section = await screen.findByRole('region', { name: 'Rolling' })
      expect(within(section).getByText('Ninety-day hour')).toBeInTheDocument()
      expect(within(section).getByText(/Aug 23, 2026 to Nov 20, 2026/)).toBeInTheDocument()
      expect(within(section).getByText('Current')).toBeInTheDocument()
      expect(within(section).getByText('lapses on Dec 3, 2026')).toBeInTheDocument()
    })

    it('shows a lapsed pilot since the open lapse began', async () => {
      mock({ current: [], history: [], rolling: [{ ...ROLLING, status: 'lapsed', lapse_date: null }], lapses: LAPSES })
      render()
      const section = await screen.findByRole('region', { name: 'Rolling' })
      expect(within(section).getByText('Lapsed')).toBeInTheDocument()
      expect(within(section).getByText('since Nov 2, 2026')).toBeInTheDocument()
    })

    it('lists the lapse history', async () => {
      mock({ current: [], history: [], rolling: [ROLLING], lapses: LAPSES })
      render()
      const table = await screen.findByRole('table', { name: 'Lapse history' })
      const rows = within(table).getAllByRole('row')
      expect(rows).toHaveLength(3)
      expect(rows[1]).toHaveTextContent('Ninety-day hourNov 2, 2026Still lapsed')
      expect(rows[2]).toHaveTextContent('Ninety-day hourJun 10, 2026Jun 21, 2026')
    })

    it('lets an admin delete a closed lapse after confirming', async () => {
      let deleted = null
      mock({ current: [], history: [], rolling: [ROLLING], lapses: LAPSES })
      server.use(http.delete('/api/requirements/:id/lapses/:lapseId', ({ params }) => {
        deleted = { id: params.id, lapseId: params.lapseId }
        return HttpResponse.json({ ok: true })
      }))
      const { user } = render('admin')
      const table = await screen.findByRole('table', { name: 'Lapse history' })
      await user.click(within(table).getByRole('button', { name: 'Delete lapse Ninety-day hour, Jun 10, 2026' }))
      const dialog = await screen.findByRole('dialog')
      expect(deleted).toBeNull()
      await user.click(within(dialog).getByRole('button', { name: 'Delete' }))
      await waitFor(() => expect(deleted).toEqual({ id: '2', lapseId: '3' }))
    })

    it('offers no Delete on an open lapse', async () => {
      mock({ current: [], history: [], rolling: [ROLLING], lapses: LAPSES })
      render('admin')
      const table = await screen.findByRole('table', { name: 'Lapse history' })
      expect(within(table).queryByRole('button', { name: /Nov 2, 2026/ })).toBeNull()
    })

    it('offers no lapse Delete to a supervisor', async () => {
      mock({ current: [], history: [], rolling: [ROLLING], lapses: LAPSES })
      render('supervisor')
      const table = await screen.findByRole('table', { name: 'Lapse history' })
      expect(within(table).queryByRole('button', { name: /^Delete lapse/ })).toBeNull()
    })

    it('shows the Lapsed requirement badge while a lapse is open', async () => {
      mock({
        current: [], history: [], rolling: [ROLLING],
        flags: { 7: [{ kind: 'lapsed', lapse_id: 4, requirement_id: 2, name: 'Ninety-day hour', period_start: '2026-11-02', period_end: null, pilot_name: 'Pat Pilot' }] },
      })
      render()
      expect(await screen.findByText('Lapsed requirement')).toBeInTheDocument()
      expect(screen.queryByText('Missed requirement')).toBeNull()
    })

    it('excuses a pilot until a date with a reason', async () => {
      let sent = null
      mock({ current: [], history: [], rolling: [ROLLING] })
      server.use(http.post('/api/requirements/:id/excuse', async ({ request, params }) => {
        sent = { id: params.id, body: await request.json() }
        return HttpResponse.json({ ok: true })
      }))
      const { user } = render()
      const section = await screen.findByRole('region', { name: 'Rolling' })
      await user.click(within(section).getByRole('button', { name: 'Excuse Ninety-day hour' }))
      const dialog = await screen.findByRole('dialog')
      await user.click(within(dialog).getByRole('button', { name: 'Excuse' }))
      expect(within(dialog).getByRole('alert')).toHaveTextContent('Choose the date the excusal lasts until')
      expect(sent).toBeNull()
      fireEvent.change(within(dialog).getByLabelText('Excused until'), { target: { value: '2099-01-31' } })
      await user.type(within(dialog).getByLabelText('Reason (optional)'), 'Medical leave')
      await user.click(within(dialog).getByRole('button', { name: 'Excuse' }))
      await waitFor(() => expect(sent).toEqual({ id: '2', body: { pilot_id: 7, excused_until: '2099-01-31', reason: 'Medical leave' } }))
    })

    it('shows an excused pilot until the date and removes the excusal', async () => {
      let sent = null
      mock({ current: [], history: [], rolling: [{ ...ROLLING, status: 'excused', lapse_date: null, excused_until: '2027-01-31' }] })
      server.use(http.post('/api/requirements/:id/excuse', async ({ request }) => {
        sent = await request.json()
        return HttpResponse.json({ ok: true })
      }))
      const { user } = render()
      const section = await screen.findByRole('region', { name: 'Rolling' })
      expect(within(section).getByText('until Jan 31, 2027')).toBeInTheDocument()
      await user.click(within(section).getByRole('button', { name: 'Remove excusal from Ninety-day hour' }))
      await waitFor(() => expect(sent).toEqual({ pilot_id: 7, excused_until: null }))
    })

    it('hides the rolling excuse buttons without requirements.excuse', async () => {
      mock({ current: [], history: [], rolling: [ROLLING] })
      render('pilot')
      await screen.findByRole('region', { name: 'Rolling' })
      expect(screen.queryByRole('button', { name: /xcus/ })).toBeNull()
    })
  })
})
