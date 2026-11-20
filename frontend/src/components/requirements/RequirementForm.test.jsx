import { describe, it, expect, vi } from 'vitest'
import { render, screen, within, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import RequirementForm from './RequirementForm'
import { newForm } from './formState'

const MODELS = [
  { name: 'X10', aircraft: 4, retired: 0 },
  { name: 'X2E', aircraft: 2, retired: 0 },
]
const PURPOSES = [
  { id: 1, name: 'Patrol', is_active: true, sort_order: 0 },
  { id: 2, name: 'Training', is_active: true, sort_order: 1 },
]
const PILOTS = [
  { id: 1, full_name: 'Pat Pilot', badge_number: 'B-1', status: 'active' },
  { id: 2, full_name: 'Sam Flyer', badge_number: 'B-2', status: 'inactive' },
]

function setup(props = {}) {
  const onSubmit = vi.fn(() => Promise.resolve())
  const onCancel = vi.fn()
  render(
    <RequirementForm
      title="New requirement"
      initial={{ ...newForm(), start_date: '2026-10-01' }}
      models={MODELS}
      purposes={PURPOSES}
      pilots={PILOTS}
      locationSet
      fiscalStartMonth={10}
      onSubmit={onSubmit}
      onCancel={onCancel}
      {...props}
    />,
  )
  return { onSubmit, onCancel, user: userEvent.setup() }
}

const PAST_WARNING = 'This requirement starts in the past. Periods that already ended will be counted, flagged and emailed.'

describe('RequirementForm', () => {
  it('warns, without blocking, when the first period has already ended', async () => {
    const { onSubmit, user } = setup({ initial: { ...newForm(), name: 'Old', target_mins: '30', start_date: '2020-01-01' } })
    expect(screen.getByText(PAST_WARNING)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Save requirement' }))
    await waitFor(() => expect(onSubmit).toHaveBeenCalled())
    fireEvent.change(screen.getByLabelText('Starts'), { target: { value: '2099-01-01' } })
    expect(screen.queryByText(PAST_WARNING)).not.toBeInTheDocument()
  })

  it('sends the body the API takes', async () => {
    const { onSubmit, user } = setup()
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Quarterly models' } })
    await user.selectOptions(screen.getByLabelText('Period'), 'calendar_quarter')
    fireEvent.change(screen.getByLabelText('Minutes'), { target: { value: '15' } })
    await user.click(screen.getByRole('button', { name: 'X10 (4)' }))
    await user.click(screen.getByRole('button', { name: 'X2E (2)' }))
    await user.click(screen.getByRole('button', { name: 'Each separately' }))
    await user.click(screen.getByRole('button', { name: 'Patrol' }))
    await user.click(screen.getByRole('button', { name: 'Save requirement' }))
    await waitFor(() => expect(onSubmit).toHaveBeenCalled())
    expect(onSubmit.mock.calls[0][0]).toEqual({
      name: 'Quarterly models', description: null, period_type: 'calendar_quarter', recurring: true,
      window_start_day: null, window_end_day: null, span_length: null, span_unit: null, every_months: null,
      target_minutes: 15, target_flights: null, model_mode: 'each', models: ['X10', 'X2E'], time_mode: 'any',
      window_start_time: null, window_end_time: null, purposes: ['Patrol'], reminder_days: 7, is_active: true,
      start_date: '2026-10-01', end_date: null, pilot_ids: [],
    })
  })

  it('shows the live summary', async () => {
    const { user } = setup()
    await user.selectOptions(screen.getByLabelText('Period'), 'calendar_quarter')
    fireEvent.change(screen.getByLabelText('Minutes'), { target: { value: '15' } })
    expect(screen.getByText('Every quarter, all active pilots must fly 15 min on any aircraft, starting Q4 2026, no end date.')).toBeInTheDocument()
  })

  it('shows only the fields of the chosen period type', async () => {
    const { user } = setup()
    expect(screen.queryByLabelText('Start day')).toBeNull()
    await user.selectOptions(screen.getByLabelText('Period'), 'monthly_window')
    expect(screen.getByLabelText('Start day')).toBeInTheDocument()
    expect(screen.getByLabelText('End day')).toBeInTheDocument()
    expect(screen.queryByLabelText('Length')).toBeNull()
    await user.selectOptions(screen.getByLabelText('Period'), 'span')
    expect(screen.queryByLabelText('Start day')).toBeNull()
    expect(screen.getByLabelText('Length')).toBeInTheDocument()
    expect(screen.getByLabelText('Unit')).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Period'), 'every_n_months')
    expect(screen.queryByLabelText('Length')).toBeNull()
    expect(screen.getByLabelText('Every (months)')).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Period'), 'custom')
    expect(screen.queryByRole('radio', { name: 'Recurring' })).toBeNull()
    expect(screen.getByLabelText('Ends')).toBeInTheDocument()
  })

  it('disables Night with the reason when the unit location is not set', () => {
    setup({ locationSet: false })
    const night = screen.getByRole('radio', { name: /Night/ })
    expect(night).toBeDisabled()
    expect(night).toHaveAccessibleDescription(/Set the unit default location/)
  })

  it('enables Night when the unit location is set', () => {
    setup()
    expect(screen.getByRole('radio', { name: /Night/ })).toBeEnabled()
  })

  it('shows clock times only for a clock window', async () => {
    const { user } = setup()
    expect(screen.queryByLabelText('From')).toBeNull()
    await user.click(screen.getByRole('radio', { name: 'Clock window' }))
    expect(screen.getByLabelText('From')).toBeInTheDocument()
    expect(screen.getByLabelText('To')).toBeInTheDocument()
  })

  it('shows Combined or Each separately once two models are selected', async () => {
    const { user } = setup()
    await user.click(screen.getByRole('button', { name: 'X10 (4)' }))
    expect(screen.queryByRole('button', { name: 'Combined' })).toBeNull()
    await user.click(screen.getByRole('button', { name: 'X2E (2)' }))
    expect(screen.getByRole('button', { name: 'Combined' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Each separately' })).toBeInTheDocument()
  })

  it('lists pilots to choose when Applies to is Selected pilots', async () => {
    const { onSubmit, user } = setup()
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Two' } })
    fireEvent.change(screen.getByLabelText('Flights'), { target: { value: '2' } })
    expect(screen.queryByRole('checkbox', { name: /Pat Pilot/ })).toBeNull()
    await user.click(screen.getByRole('radio', { name: 'Selected pilots' }))
    const pilots = screen.getByRole('group', { name: 'Pilots' })
    expect(within(pilots).getByRole('checkbox', { name: 'Sam Flyer (inactive)' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Save requirement' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Select at least one pilot')
    await user.click(within(pilots).getByRole('checkbox', { name: 'Pat Pilot' }))
    await user.click(screen.getByRole('button', { name: 'Save requirement' }))
    await waitFor(() => expect(onSubmit).toHaveBeenCalled())
    expect(onSubmit.mock.calls[0][0].pilot_ids).toEqual([1])
  })

  it('shows the error the save returns', async () => {
    const onSubmit = vi.fn(() => Promise.reject(new Error('A clock window needs a start and an end time')))
    const { user } = setup({ onSubmit, initial: { ...newForm(), name: 'X', target_flights: '1' } })
    await user.click(screen.getByRole('button', { name: 'Save requirement' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('A clock window needs a start and an end time')
  })

  it('presses a saved purpose that differs from the list only in case, once', async () => {
    const { onSubmit, user } = setup({ initial: { ...newForm(), name: 'P', target_flights: '1', purposes: ['patrol'] } })
    const fieldset = screen.getByRole('group', { name: 'Flight purposes' })
    expect(within(fieldset).getByRole('button', { name: 'Patrol' })).toHaveAttribute('aria-pressed', 'true')
    expect(within(fieldset).queryByRole('button', { name: 'patrol' })).toBeNull()
    await user.click(within(fieldset).getByRole('button', { name: 'Patrol' }))
    await user.click(screen.getByRole('button', { name: 'Save requirement' }))
    await waitFor(() => expect(onSubmit).toHaveBeenCalled())
    expect(onSubmit.mock.calls[0][0].purposes).toEqual([])
  })

  it('puts the Active switch first, with Name and Description, away from the Reminder', () => {
    setup()
    const active = screen.getByRole('switch', { name: 'Requirement is active' })
    expect(active).toHaveAttribute('aria-checked', 'true')
    expect(active).toHaveAccessibleDescription(
      'Inactive requirements are kept but do not track progress, show on the dashboard or send emails.')
    const firstSection = screen.getByLabelText('Name').closest('[data-form-section]')
    expect(firstSection).toContainElement(active)
    expect(firstSection).toContainElement(screen.getByLabelText('Description (optional)'))
    expect(firstSection).not.toContainElement(screen.getByLabelText('Period'))
    const reminderSection = screen.getByLabelText('Reminder (days before the period ends)').closest('[data-form-section]')
    expect(reminderSection).not.toContainElement(active)
    expect(screen.queryByRole('checkbox', { name: 'Active' })).toBeNull()
  })

  it('saves a requirement switched off from the Active switch', async () => {
    const { onSubmit, user } = setup({ initial: { ...newForm(), name: 'Off', target_flights: '1', start_date: '2026-10-01' } })
    const active = screen.getByRole('switch', { name: 'Requirement is active' })
    await user.click(active)
    expect(active).toHaveAttribute('aria-checked', 'false')
    await user.click(screen.getByRole('button', { name: 'Save requirement' }))
    await waitFor(() => expect(onSubmit).toHaveBeenCalled())
    expect(onSubmit.mock.calls[0][0].is_active).toBe(false)
  })
})
