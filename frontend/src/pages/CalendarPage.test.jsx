import { describe, it, expect } from 'vitest'
import { screen, within, fireEvent, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import CalendarPage from './CalendarPage'

// @fullcalendar/react is globally stubbed to <div data-testid="fullcalendar-stub" />.
// Because the stub never fires datesSet, the page does NOT fetch /calendar on
// mount in the test environment; it renders chrome (title, category toggles,
// the stub) and the create-event modal. Save: POST /calendar/events.

describe('CalendarPage', () => {
  it('renders without crashing under the fullcalendar stub', async () => {
    renderWithProviders(<CalendarPage />, { role: 'admin' })
    expect(await screen.findByRole('heading', { name: 'Calendar' })).toBeInTheDocument()
    expect(screen.getByTestId('fullcalendar-stub')).toBeInTheDocument()
  })

  it('renders the category legend toggles', async () => {
    renderWithProviders(<CalendarPage />, { role: 'admin' })
    expect(await screen.findByText('Training')).toBeInTheDocument()
    expect(screen.getByText('Missions')).toBeInTheDocument()
    expect(screen.getByText('Flights')).toBeInTheDocument()
  })

  it('does not crash when /calendar would return empty data', async () => {
    // The stub does not call datesSet, but mock the endpoint anyway so any
    // (future) fetch resolves cleanly instead of erroring on an unhandled req.
    server.use(http.get('/api/calendar', () => HttpResponse.json({ events: [], flight_counts: {} })))
    renderWithProviders(<CalendarPage />, { role: 'admin' })
    expect(await screen.findByTestId('fullcalendar-stub')).toBeInTheDocument()
  })

  it('opens the add-event modal and saves via POST /calendar/events', async () => {
    let body = null
    server.use(
      http.get('/api/calendar', () => HttpResponse.json({ events: [], flight_counts: {} })),
      http.post('/api/calendar/events', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ id: 99 })
      }),
    )
    const { user } = renderWithProviders(<CalendarPage />, { role: 'admin' })
    await screen.findByRole('heading', { name: 'Calendar' })

    await user.click(screen.getByRole('button', { name: 'Add event / leave' }))
    const dialog = await screen.findByRole('dialog')
    // Set controlled inputs via fireEvent.change (userEvent.type proved flaky on
    // the modal's title/date inputs in jsdom).
    fireEvent.change(within(dialog).getByLabelText('Title'), { target: { value: 'Range Day' } })
    fireEvent.change(within(dialog).getByLabelText('Start date'), { target: { value: '2026-07-01' } })
    await user.click(within(dialog).getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(body).not.toBeNull())
    expect(body).toMatchObject({ title: 'Range Day', category: 'event', start_date: '2026-07-01' })
  })

  it('refuses an end date before the start date or a blank title without saving', async () => {
    let posted = false
    server.use(http.post('/api/calendar/events', () => { posted = true; return HttpResponse.json({ id: 1 }) }))
    const { user } = renderWithProviders(<CalendarPage />, { role: 'admin' })
    await screen.findByRole('heading', { name: 'Calendar' })
    await user.click(screen.getByRole('button', { name: 'Add event / leave' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('Title'), { target: { value: '   ' } })
    fireEvent.change(within(dialog).getByLabelText('Start date'), { target: { value: '2026-11-25' } })
    await user.click(within(dialog).getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Required: Title')).toBeInTheDocument()
    fireEvent.change(within(dialog).getByLabelText('Title'), { target: { value: 'Backwards' } })
    const end = within(dialog).getByLabelText('End date (optional)')
    expect(end).toHaveAttribute('min', '2026-11-25')
    fireEvent.change(end, { target: { value: '2026-11-01' } })
    // The min attribute stops a browser submit; the handler checks as well.
    fireEvent.submit(dialog.querySelector('form'))
    expect(await screen.findByText('End date cannot be before the start date')).toBeInTheDocument()
    expect(posted).toBe(false)
  })
})
