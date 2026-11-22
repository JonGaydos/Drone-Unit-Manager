import { describe, it, expect } from 'vitest'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import MissedPeriods from './MissedPeriods'

const row = (over) => ({
  result_id: 1, requirement_id: 1, name: 'Monthly hour', pilot_id: 7, pilot_name: 'Pat Pilot',
  period_start: '2026-10-01', period_end: '2026-10-31', status: 'missed',
  totals: { '*': { minutes: 40, flights: 3 } }, target_snapshot: { target_minutes: 60 },
  excused: false, excused_by_id: null, excused_reason: null, saved_at: '2026-11-15T06:00:00', switched_off: false,
  ...over,
})
const MISSED = row({})
const EXCUSED = row({
  result_id: 2, pilot_id: 8, pilot_name: 'Sam Smith', status: 'excused', excused: true, excused_by_id: 2,
  excused_reason: 'On leave',
})
const OFF = row({
  result_id: 3, pilot_id: 9, pilot_name: 'Olu Off', status: 'excused', excused: true, excused_by_id: null,
  excused_reason: 'Requirement switched off', switched_off: true,
})
const REQUIREMENTS = [{ id: 1, name: 'Monthly hour' }, { id: 2, name: 'Night hour' }]
const ROLLING = { id: 3, name: 'Rolling ninety', period_type: 'rolling' }

function mock(rows = [MISSED, EXCUSED, OFF]) {
  const calls = { history: [], posts: [] }
  server.use(
    http.get('/api/requirements/history', ({ request }) => {
      calls.history.push(new URL(request.url).searchParams.get('requirement_id'))
      return HttpResponse.json(rows)
    }),
    http.post('/api/requirements/:id/excuse', async ({ request, params }) => {
      calls.posts.push({ id: params.id, body: await request.json() })
      return HttpResponse.json({ ok: true })
    }),
  )
  return calls
}

const render = (role = 'supervisor') => renderWithProviders(<MissedPeriods requirements={REQUIREMENTS} />, { role })

describe('MissedPeriods', () => {
  it('lists missed and excused periods with a link to each pilot', async () => {
    mock()
    render()
    const table = await screen.findByRole('table', { name: 'Past missed periods' })
    for (const name of ['Requirement', 'Pilot', 'Period', 'Result', 'Status']) {
      expect(within(table).getByRole('columnheader', { name })).toBeInTheDocument()
    }
    expect(within(table).getByRole('link', { name: 'Pat Pilot' })).toHaveAttribute('href', '/pilots/7')
    expect(within(table).getAllByText('40m/1h')).toHaveLength(3)
    expect(within(table).getByText('Excused: On leave')).toBeInTheDocument()
  })

  it('excuses a missed row with a reason and reloads the list', async () => {
    const calls = mock()
    const { user } = render()
    await user.click(await screen.findByRole('button', { name: /^Excuse Monthly hour/ }))
    await user.type(await screen.findByLabelText('Reason (optional)'), 'Injury')
    fireEvent.submit(screen.getByRole('button', { name: 'Excuse', exact: true }).closest('form'))
    await waitFor(() => expect(calls.posts).toEqual([
      { id: '1', body: { pilot_id: 7, period_start: '2026-10-01', excused: true, reason: 'Injury' } }]))
    await waitFor(() => expect(calls.history).toHaveLength(2))
  })

  it('un-excuses an excused row, and offers nothing on a switched-off one', async () => {
    const calls = mock()
    const { user } = render()
    const buttons = await screen.findAllByRole('button', { name: /xcuse Monthly hour/ })
    expect(buttons.map(b => b.textContent)).toEqual(['Excuse', 'Un-excuse'])
    const switchedOff = screen.getByRole('link', { name: 'Olu Off' }).closest('tr')
    expect(within(switchedOff).queryByRole('button')).not.toBeInTheDocument()
    await user.click(buttons[1])
    await waitFor(() => expect(calls.posts).toEqual([
      { id: '1', body: { pilot_id: 8, period_start: '2026-10-01', excused: false } }]))
  })

  it('shows no Excuse or Un-excuse without requirements.excuse', async () => {
    mock()
    render('viewer')
    await screen.findByRole('table', { name: 'Past missed periods' })
    expect(screen.queryByRole('button', { name: /Excuse/ })).not.toBeInTheDocument()
  })

  it('says so when there are none', async () => {
    mock([])
    render()
    expect(await screen.findByText('No missed periods.')).toBeInTheDocument()
  })

  it('refetches for the chosen requirement', async () => {
    const calls = mock()
    const { user } = render()
    await screen.findByRole('table', { name: 'Past missed periods' })
    await user.selectOptions(screen.getByLabelText('Requirement filter'), 'Night hour')
    await waitFor(() => expect(calls.history).toEqual([null, '2']))
  })

  it('does not offer a rolling requirement in the filter', async () => {
    mock()
    renderWithProviders(<MissedPeriods requirements={[...REQUIREMENTS, ROLLING]} />, { role: 'supervisor' })
    await screen.findByRole('table', { name: 'Past missed periods' })
    const options = within(screen.getByLabelText('Requirement filter')).getAllByRole('option').map(o => o.textContent)
    expect(options).toEqual(['All requirements', 'Monthly hour', 'Night hour'])
  })
})
