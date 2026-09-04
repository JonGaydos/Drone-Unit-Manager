import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ConfirmDialog } from './ConfirmDialog'

afterEach(() => {
  document.body.style.overflow = ''
})

describe('ConfirmDialog', () => {
  it('renders the title and message when open', () => {
    render(
      <ConfirmDialog open onClose={() => {}} onConfirm={() => {}} title="Delete pilot" message="This cannot be undone." />,
    )
    expect(screen.getByText('Delete pilot')).toBeInTheDocument()
    expect(screen.getByText('This cannot be undone.')).toBeInTheDocument()
  })

  it('defaults the title to "Confirm Action"', () => {
    render(<ConfirmDialog open onClose={() => {}} onConfirm={() => {}} message="m" />)
    expect(screen.getByText('Confirm Action')).toBeInTheDocument()
  })

  it('confirm button fires onConfirm then onClose', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    const onClose = vi.fn()
    render(
      <ConfirmDialog open onClose={onClose} onConfirm={onConfirm} message="m" confirmLabel="Delete" />,
    )
    await user.click(screen.getByRole('button', { name: 'Delete' }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('cancel button fires onClose only', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    const onClose = vi.fn()
    render(<ConfirmDialog open onClose={onClose} onConfirm={onConfirm} message="m" />)
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalledTimes(1)
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('uses the confirmLabel prop for the confirm button', () => {
    render(
      <ConfirmDialog open onClose={() => {}} onConfirm={() => {}} message="m" confirmLabel="Remove" confirmVariant="primary" />,
    )
    expect(screen.getByRole('button', { name: 'Remove' })).toBeInTheDocument()
  })
})
