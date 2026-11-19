import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import FleetModelPicker from './FleetModelPicker'

const MODELS = [
  { name: 'X10', aircraft: 4, retired: 0 },
  { name: 'X2E', aircraft: 2, retired: 1 },
  { name: 'Old1', aircraft: 0, retired: 3 },
]

function setup(value = []) {
  const onChange = vi.fn()
  render(<FleetModelPicker models={MODELS} value={value} onChange={onChange} />)
  return { onChange, user: userEvent.setup() }
}

describe('FleetModelPicker', () => {
  it('presses All aircraft when nothing is selected', () => {
    setup([])
    expect(screen.getByRole('button', { name: 'All aircraft' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'X10 (4)' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('selects a model', async () => {
    const { onChange, user } = setup([])
    await user.click(screen.getByRole('button', { name: 'X10 (4)' }))
    expect(onChange).toHaveBeenCalledWith(['X10'])
  })

  it('adds to an existing selection', async () => {
    const { onChange, user } = setup(['X10'])
    await user.click(screen.getByRole('button', { name: 'X2E (2)' }))
    expect(onChange).toHaveBeenCalledWith(['X10', 'X2E'])
  })

  it('returns to All aircraft when the last model is turned off', async () => {
    const { onChange, user } = setup(['X10'])
    await user.click(screen.getByRole('button', { name: 'X10 (4)' }))
    expect(onChange).toHaveBeenCalledWith([])
  })

  it('clears the list when All aircraft is turned on', async () => {
    const { onChange, user } = setup(['X10', 'X2E'])
    await user.click(screen.getByRole('button', { name: 'All aircraft' }))
    expect(onChange).toHaveBeenCalledWith([])
  })

  it('hides a model with no active aircraft until it is selected', () => {
    const { unmount } = render(<FleetModelPicker models={MODELS} value={[]} onChange={() => {}} />)
    expect(screen.queryByText(/Old1/)).toBeNull()
    unmount()
    render(<FleetModelPicker models={MODELS} value={['Old1']} onChange={() => {}} />)
    expect(screen.getByRole('button', { name: /Old1 \(no active aircraft\)/ })).toHaveAttribute('aria-pressed', 'true')
  })

  it('marks a selected name that is not in the fleet', () => {
    render(<FleetModelPicker models={MODELS} value={['x11']} onChange={() => {}} />)
    expect(screen.getByRole('button', { name: /x11 \(Not in fleet\)/ })).toHaveAttribute('aria-pressed', 'true')
  })

  it('matches a selected name to the fleet ignoring case and spacing', () => {
    render(<FleetModelPicker models={MODELS} value={[' x10 ']} onChange={() => {}} />)
    expect(screen.getByRole('button', { name: 'X10 (4)' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.queryByText(/Not in fleet/)).toBeNull()
  })

  it('removes a model selected under a different case by its stored name', async () => {
    const { onChange, user } = setup(['x10', 'X2E'])
    await user.click(screen.getByRole('button', { name: 'X10 (4)' }))
    expect(onChange).toHaveBeenCalledWith(['X2E'])
  })
})
