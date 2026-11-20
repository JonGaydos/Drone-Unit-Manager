import { describe, it, expect } from 'vitest'
import { screen, within } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import FlightRequirementsPage from './FlightRequirementsPage'

const BASE = {
  description: null, recurring: true, window_start_day: null, window_end_day: null, span_length: null,
  span_unit: null, every_months: null, target_flights: null, model_mode: 'all', models: [], time_mode: 'any',
  window_start_time: null, window_end_time: null, purposes: [], pilot_ids: [], reminder_days: 7,
  start_date: '2026-10-01', end_date: null, active_changed_at: null, created_at: '2026-10-01T00:00:00',
  updated_at: '2026-10-01T00:00:00', current_period: null,
}
const ON = { ...BASE, id: 4, name: 'Monthly hour', period_type: 'calendar_month', target_minutes: 60, is_active: true }
const OFF = { ...BASE, id: 5, name: 'Old quarterly', period_type: 'calendar_quarter', target_minutes: 15, is_active: false }

const progress = (id, name, status, minutes) => ({
  pilot_id: id, pilot_name: name, status, totals: { '*': { minutes, flights: 1 } }, met_by_model: {},
  excluded_no_takeoff: 0, unreviewed_in_period: 0, excused: false, excused_reason: null,
})
const STATUS = {
  score: null,
  inactive_count: 1,
  requirements: [{
    requirement_id: 4, name: 'Monthly hour', target_minutes: 60, target_flights: null, model_mode: 'all',
    current_period: {
      start: '2026-11-01', end: '2026-11-30', days_left: 10, review_until: '2026-12-14',
      pilots: [progress(1, 'Pat Pilot', 'met', 75), progress(2, 'Sam Flyer', 'on_track', 20)],
    },
    pending_periods: [],
  }],
}

function mock() {
  const asked = new Set()
  const seen = (path, body) => () => { asked.add(path); return HttpResponse.json(body) }
  server.use(
    http.get('/api/requirements', seen('requirements', [ON, OFF])),
    http.get('/api/requirements/status', seen('status', STATUS)),
    http.get('/api/requirements/templates', seen('templates', [])),
    http.get('/api/requirements/models', seen('models', [])),
    http.get('/api/requirements/settings', seen('settings', { grace_days: 14, fiscal_year_start_month: 10, emails_enabled: false })),
  )
  return asked
}

function renderPage(options) {
  return renderWithProviders(
    <Routes>
      <Route path="/requirements" element={<FlightRequirementsPage />} />
      <Route path="/" element={<p>Dashboard page</p>} />
    </Routes>,
    { route: '/requirements', ...options },
  )
}

describe('FlightRequirementsPage', () => {
  it('shows a viewer the list and each requirement\'s progress without manage controls', async () => {
    const asked = mock()
    renderPage({ role: 'viewer' })
    expect(await screen.findByRole('heading', { level: 1, name: 'Flight Requirements' })).toBeInTheDocument()
    const row = (await screen.findByText('Monthly hour')).closest('li')
    expect(await within(row).findByText('10 days left')).toBeInTheDocument()
    expect(within(row).getByText('1/2 met')).toBeInTheDocument()
    expect(within(row).getByRole('link', { name: 'Pat Pilot' })).toHaveAttribute('href', '/pilots/1')
    expect(within(row).getByRole('link', { name: 'Sam Flyer' })).toBeInTheDocument()
    expect(screen.getByText('Old quarterly').closest('li')).toHaveTextContent('Inactive')

    for (const name of [/New requirement/, /^Edit /, /^Duplicate /, /as a template/, /^Delete /, /^Switch (on|off) /]) {
      expect(screen.queryByRole('button', { name })).toBeNull()
    }
    expect(screen.getByRole('button', { name: 'Download Monthly hour results as CSV' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Templates' })).toBeNull()
    expect(screen.queryByRole('heading', { name: 'Requirement Settings' })).toBeNull()
    expect(asked.has('templates')).toBe(false)
    expect(asked.has('models')).toBe(false)
  })

  it('gives a supervisor the manage controls, templates and settings', async () => {
    mock()
    renderPage({ role: 'supervisor' })
    await screen.findByText('Monthly hour')
    expect(screen.getByRole('button', { name: 'New requirement' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Edit Monthly hour' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Switch off Monthly hour' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Switch on Old quarterly' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete Old quarterly' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Templates' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Requirement Settings' })).toBeInTheDocument()
  })

  it('hides the CSV download without reports.export', async () => {
    mock()
    renderPage({ role: 'viewer', permissions: { 'reports.export': 'no' } })
    await screen.findByText('Monthly hour')
    expect(screen.queryByRole('button', { name: /as CSV/ })).toBeNull()
  })

  it('sends a user without requirements.view to the dashboard', async () => {
    mock()
    renderPage({ role: 'supervisor', permissions: { 'requirements.view': 'no' } })
    expect(await screen.findByText('Dashboard page')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Flight Requirements' })).toBeNull()
  })
})
