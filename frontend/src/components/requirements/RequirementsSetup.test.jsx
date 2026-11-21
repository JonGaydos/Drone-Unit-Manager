import { describe, it, expect } from 'vitest'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { useLocation } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import RequirementsSetup from './RequirementsSetup'

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

function mock() {
  const calls = []
  const record = (method) => async ({ request }) => {
    const body = method === 'DELETE' ? null : await request.json()
    calls.push({ method, url: new URL(request.url).pathname, body })
    return HttpResponse.json({ ok: true, ...(body || {}) })
  }
  server.use(
    http.get('/api/requirements/templates', () => HttpResponse.json([TEMPLATE])),
    http.get('/api/requirements/settings', () => HttpResponse.json({ grace_days: 14, fiscal_year_start_month: 10, emails_enabled: false })),
    http.patch('/api/requirements/templates/:id', record('PATCH')),
    http.delete('/api/requirements/templates/:id', record('DELETE')),
    http.put('/api/requirements/settings', record('PUT')),
  )
  return calls
}

function LocationProbe() {
  const location = useLocation()
  return <p data-testid="location">{location.pathname + location.search}|{location.state?.template?.name ?? ''}</p>
}

function renderSetup() {
  return renderWithProviders(<><RequirementsSetup /><LocationProbe /></>, { role: 'supervisor', route: '/compliance?tab=setup' })
}

describe('RequirementsSetup', () => {
  it('sends a template to the Flight Requirements tab to start a new requirement', async () => {
    mock()
    const { user } = renderSetup()
    await user.click(await screen.findByRole('button', { name: 'New from template Night hour' }))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/compliance?tab=requirements|Night hour'))
  })

  it('renames and deletes a template', async () => {
    const calls = mock()
    const { user } = renderSetup()
    await user.click(await screen.findByRole('button', { name: 'Rename Night hour' }))
    const input = screen.getByLabelText('New name for Night hour')
    fireEvent.change(input, { target: { value: 'Two week night' } })
    await user.click(screen.getByRole('button', { name: 'Save name' }))
    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0]).toMatchObject({ method: 'PATCH', url: '/api/requirements/templates/7', body: { name: 'Two week night' } })
    await user.click(screen.getByRole('button', { name: 'Delete template Night hour' }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(calls).toHaveLength(2))
    expect(calls[1]).toMatchObject({ method: 'DELETE', url: '/api/requirements/templates/7' })
  })

  it('saves the requirement settings', async () => {
    const calls = mock()
    const { user } = renderSetup()
    const grace = await screen.findByLabelText('Grace days')
    await waitFor(() => expect(grace).toHaveValue(14))
    fireEvent.change(grace, { target: { value: '10' } })
    await user.selectOptions(screen.getByLabelText('Fiscal year starts in'), '7')
    await user.click(screen.getByRole('button', { name: 'Save settings' }))
    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0]).toMatchObject({ method: 'PUT', url: '/api/requirements/settings', body: { grace_days: 10, fiscal_year_start_month: 7, emails_enabled: false } })
  })

  it('leaves requirement emails off until the box is checked, then saves it', async () => {
    const calls = mock()
    const { user } = renderSetup()
    const box = await screen.findByLabelText('Send requirement emails')
    await waitFor(() => expect(screen.getByLabelText('Grace days')).toHaveValue(14))
    expect(box).not.toBeChecked()
    expect(screen.getByText(/assignment, a reminder before the period ends and a missed requirement/)).toBeInTheDocument()
    expect(screen.getByText(/SMTP must be set up/)).toBeInTheDocument()
    await user.click(box)
    await user.click(screen.getByRole('button', { name: 'Save settings' }))
    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0].body).toMatchObject({ emails_enabled: true })
  })

})
