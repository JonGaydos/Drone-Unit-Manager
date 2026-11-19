import { describe, it, expect } from 'vitest'
import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import ThisPeriodTile from './ThisPeriodTile'

const pilot = (id, name, status, totals, metByModel) => ({
  pilot_id: id, pilot_name: name, status, totals, met_by_model: metByModel,
  excluded_no_takeoff: 0, unreviewed_in_period: 0, excused: status === 'excused',
  excused_reason: status === 'excused' ? 'On leave' : null,
})

const STATUS = {
  score: 0.8,
  requirements: [{
    requirement_id: 1, name: 'Quarterly models', target_minutes: 15, target_flights: null, model_mode: 'each',
    current_period: {
      start: '2026-10-01', end: '2026-12-31', days_left: 43, review_until: '2027-01-14',
      pilots: [
        pilot(3, 'Pat Pilot', 'on_track', { X10: { minutes: 12, flights: 1 }, X2E: { minutes: 15, flights: 1 } }, { X10: false, X2E: true }),
        pilot(4, 'Sam Flyer', 'met', { X10: { minutes: 20, flights: 2 }, X2E: { minutes: 16, flights: 1 } }, { X10: true, X2E: true }),
        pilot(5, 'Lee Rotor', 'excused', { X10: { minutes: 0, flights: 0 }, X2E: { minutes: 0, flights: 0 } }, { X10: false, X2E: false }),
      ],
    },
    pending_periods: [{
      start: '2026-07-01', end: '2026-09-30', days_left: 0, review_until: '2026-11-25',
      pilots: [pilot(3, 'Pat Pilot', 'pending_review', { X10: { minutes: 3, flights: 1 } }, { X10: false })],
    }],
  }],
}

function mock({ status = STATUS, flags = {} } = {}) {
  server.use(
    http.get('/api/requirements/status', () => HttpResponse.json(status)),
    http.get('/api/requirements/flags', () => HttpResponse.json(flags)),
  )
}

describe('ThisPeriodTile', () => {
  it('shows days left, met over assigned and each pilot progress per requirement', async () => {
    mock()
    renderWithProviders(<ThisPeriodTile />, { role: 'pilot' })
    const req = await screen.findByRole('listitem', { name: 'Quarterly models' })
    expect(within(req).getByText('43 days left')).toBeInTheDocument()
    expect(within(req).getByText('1/3 met')).toBeInTheDocument()
    expect(within(req).getByText('X10 12m/15m, X2E done')).toBeInTheDocument()
    expect(within(req).getByRole('link', { name: 'Pat Pilot' })).toHaveAttribute('href', '/pilots/3')
    expect(within(req).getByText('Excused')).toBeInTheDocument()
  })

  it('says how many pilots of an ended period are still in review', async () => {
    mock()
    renderWithProviders(<ThisPeriodTile />, { role: 'pilot' })
    expect(await screen.findByText(/1 pilot pending review until Nov 25, 2026/)).toBeInTheDocument()
  })

  it('shows the Requirements score, or that there are no results yet', async () => {
    mock()
    const { unmount } = renderWithProviders(<ThisPeriodTile />, { role: 'pilot' })
    expect(await screen.findByText('Requirements score 80%')).toBeInTheDocument()
    unmount()
    mock({ status: { ...STATUS, score: null } })
    renderWithProviders(<ThisPeriodTile />, { role: 'pilot' })
    expect(await screen.findByText('No results yet')).toBeInTheDocument()
  })

  it('names the pilots with an open miss', async () => {
    mock({ flags: { 3: [{ result_id: 9, requirement_id: 1, name: 'Quarterly models', period_start: '2026-04-01', period_end: '2026-06-30' }] } })
    renderWithProviders(<ThisPeriodTile />, { role: 'pilot' })
    const line = await screen.findByText(/Open misses/)
    expect(within(line.closest('p')).getByRole('link', { name: 'Pat Pilot' })).toHaveAttribute('href', '/pilots/3')
  })

  it('names a flagged pilot who is no longer assigned by number', async () => {
    mock({ flags: { 12: [{ result_id: 9, requirement_id: 1, name: 'Old', period_start: '2026-04-01', period_end: '2026-06-30' }] } })
    renderWithProviders(<ThisPeriodTile />, { role: 'pilot' })
    expect(await screen.findByRole('link', { name: 'Pilot 12' })).toHaveAttribute('href', '/pilots/12')
  })

  it('shows an empty state when there are no active requirements', async () => {
    mock({ status: { score: null, requirements: [] } })
    renderWithProviders(<ThisPeriodTile />, { role: 'pilot' })
    expect(await screen.findByText('No active flight requirements')).toBeInTheDocument()
    expect(screen.queryByText(/Open misses/)).toBeNull()
  })
})
