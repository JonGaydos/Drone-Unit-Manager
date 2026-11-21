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
    mock({ flags: { 3: [{ kind: 'missed', result_id: 9, requirement_id: 1, name: 'Quarterly models', period_start: '2026-04-01', period_end: '2026-06-30', pilot_name: 'Pat Pilot' }] } })
    renderWithProviders(<ThisPeriodTile />, { role: 'pilot' })
    const line = await screen.findByText(/Missed requirement/)
    expect(within(line.closest('p')).getByRole('link', { name: 'Pat Pilot' })).toHaveAttribute('href', '/pilots/3')
  })

  it('names a flagged pilot who is no longer assigned by the name the flags carry', async () => {
    mock({ flags: { 12: [{ result_id: 9, requirement_id: 1, name: 'Old', period_start: '2026-04-01', period_end: '2026-06-30', pilot_name: 'Lee Former' }] } })
    renderWithProviders(<ThisPeriodTile />, { role: 'pilot' })
    expect(await screen.findByRole('link', { name: 'Lee Former' })).toHaveAttribute('href', '/pilots/12')
    expect(screen.queryByText('Pilot 12')).toBeNull()
  })

  it('shows an empty state when there are no active requirements', async () => {
    mock({ status: { score: null, requirements: [], inactive_count: 0 } })
    renderWithProviders(<ThisPeriodTile />, { role: 'pilot' })
    expect(await screen.findByText('No active flight requirements')).toBeInTheDocument()
    expect(screen.queryByText(/Missed requirement/)).toBeNull()
  })

  it('says how many requirements are switched off when none is active, with a link for managers', async () => {
    mock({ status: { score: null, requirements: [], inactive_count: 2 } })
    const { unmount } = renderWithProviders(<ThisPeriodTile />, { role: 'supervisor' })
    const link = await screen.findByRole('link', { name: '2 flight requirements switched off' })
    expect(link).toHaveAttribute('href', '/compliance?tab=requirements')
    expect(screen.queryByText('No active flight requirements')).toBeNull()
    unmount()

    mock({ status: { score: null, requirements: [], inactive_count: 1 } })
    renderWithProviders(<ThisPeriodTile />, { role: 'pilot' })
    expect(await screen.findByText('1 flight requirement switched off')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /switched off/ })).toBeNull()
  })
  describe('a rolling requirement', () => {
    const rollingPilot = (id, name, status, extra) => ({
      pilot_id: id, pilot_name: name, status, totals: { '*': { minutes: 30, flights: 1 } }, met_by_model: { '*': false },
      lapse_date: null, excused_until: null, excluded_no_takeoff: 0, unreviewed_in_window: 0, ...extra,
    })
    const ROLLING = {
      requirement_id: 2, name: 'Ninety-day hour', period_type: 'rolling', target_minutes: 60, target_flights: null,
      model_mode: 'all', current_period: null, pending_periods: [],
      rolling: {
        window_start: '2026-08-23', window_end: '2026-11-20',
        pilots: [
          rollingPilot(3, 'Pat Pilot', 'current', { lapse_date: '2026-12-03', totals: { '*': { minutes: 75, flights: 2 } } }),
          rollingPilot(4, 'Sam Flyer', 'lapsed'),
          rollingPilot(5, 'Lee Rotor', 'not_yet_due'),
          rollingPilot(6, 'Kim Wing', 'excused', { excused_until: '2027-01-31' }),
        ],
      },
    }
    const LAPSE = {
      kind: 'lapsed', result_id: null, lapse_id: 3, requirement_id: 2, name: 'Ninety-day hour',
      period_start: '2026-11-02', period_end: null, pilot_name: 'Sam Flyer',
    }

    it('counts current and lapsed pilots and gives each pilot\'s standing', async () => {
      mock({ status: { score: null, requirements: [ROLLING] }, flags: { 4: [LAPSE] } })
      renderWithProviders(<ThisPeriodTile />, { role: 'pilot' })
      const req = await screen.findByRole('listitem', { name: 'Ninety-day hour' })
      expect(within(req).getByText('1 current, 1 lapsed')).toBeInTheDocument()
      expect(within(req).getByText('lapses on Dec 3, 2026')).toBeInTheDocument()
      expect(await within(req).findByText('since Nov 2, 2026')).toBeInTheDocument()
      expect(within(req).getByText('Not yet due')).toBeInTheDocument()
      expect(within(req).getByText('until Jan 31, 2027')).toBeInTheDocument()
      expect(within(req).getByText('Current')).toBeInTheDocument()
      expect(within(req).getByText('Lapsed')).toBeInTheDocument()
    })

    it('labels an open lapse Lapsed requirement', async () => {
      mock({ status: { score: null, requirements: [ROLLING] }, flags: { 4: [LAPSE] } })
      renderWithProviders(<ThisPeriodTile />, { role: 'pilot' })
      const line = await screen.findByText(/Lapsed requirement/)
      expect(within(line.closest('p')).getByRole('link', { name: 'Sam Flyer' })).toHaveAttribute('href', '/pilots/4')
      expect(screen.queryByText(/Missed requirement/)).toBeNull()
    })
  })
})
