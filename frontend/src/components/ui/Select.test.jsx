import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Select } from './Select'

const options = [
  { value: 'pilot', label: 'Pilot' },
  { value: 'admin', label: 'Admin' },
]

describe('Select', () => {
  it('renders a native select with the given options', () => {
    render(<Select label="Role" options={options} value="" onChange={() => {}} />)
    const select = screen.getByLabelText('Role')
    expect(select.tagName).toBe('SELECT')
    expect(screen.getByRole('option', { name: 'Pilot' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Admin' })).toBeInTheDocument()
  })

  it('associates the label with the control', () => {
    render(<Select label="Status" options={options} value="" onChange={() => {}} />)
    expect(screen.getByLabelText('Status')).toHaveAttribute('id', 'status')
  })

  it('fires onChange when an option is selected', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Select label="Role" options={options} value="pilot" onChange={onChange} />)
    await user.selectOptions(screen.getByLabelText('Role'), 'admin')
    expect(onChange).toHaveBeenCalledTimes(1)
  })

  it('renders a disabled placeholder option when provided', () => {
    render(<Select label="Role" options={options} value="" onChange={() => {}} placeholder="Select a role" />)
    const placeholder = screen.getByRole('option', { name: 'Select a role' })
    expect(placeholder).toBeDisabled()
  })

  it('reflects the controlled value', () => {
    render(<Select label="Role" options={options} value="admin" onChange={() => {}} />)
    expect(screen.getByLabelText('Role')).toHaveValue('admin')
  })
})
