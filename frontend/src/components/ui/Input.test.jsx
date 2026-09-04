import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Input } from './Input'

describe('Input', () => {
  it('renders with a label associated to the control', () => {
    render(<Input label="Call Sign" />)
    // Label is associated via htmlFor derived from the label text.
    const input = screen.getByLabelText('Call Sign')
    expect(input).toBeInTheDocument()
    expect(input.tagName).toBe('INPUT')
  })

  it('derives the id from the label (kebab-case)', () => {
    render(<Input label="Drone Serial" />)
    expect(screen.getByLabelText('Drone Serial')).toHaveAttribute('id', 'drone-serial')
  })

  it('honors an explicit id over the label-derived one', () => {
    render(<Input label="Name" id="custom-id" />)
    expect(screen.getByLabelText('Name')).toHaveAttribute('id', 'custom-id')
  })

  it('fires onChange while typing', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Input label="Notes" onChange={onChange} />)
    await user.type(screen.getByLabelText('Notes'), 'abc')
    expect(onChange).toHaveBeenCalledTimes(3)
  })

  it('passes through type and placeholder', () => {
    render(<Input label="Pass" type="password" placeholder="secret" />)
    const input = screen.getByLabelText('Pass')
    expect(input).toHaveAttribute('type', 'password')
    expect(input).toHaveAttribute('placeholder', 'secret')
  })

  it('forwards a ref to the underlying input', () => {
    const ref = { current: null }
    render(<Input label="R" ref={ref} />)
    expect(ref.current).toBeInstanceOf(HTMLInputElement)
  })
})
