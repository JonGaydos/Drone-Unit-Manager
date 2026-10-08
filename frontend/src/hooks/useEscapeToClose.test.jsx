import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { useEscapeToClose } from './useEscapeToClose'

function Popup({ onClose }) {
  useEscapeToClose(onClose)
  return <div role="dialog" aria-modal="true">popup</div>
}

describe('useEscapeToClose', () => {
  it('closes on Escape and ignores other keys', () => {
    const onClose = vi.fn()
    render(<Popup onClose={onClose} />)
    fireEvent.keyDown(document, { key: 'Enter' })
    expect(onClose).not.toHaveBeenCalled()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('stops listening once the popup is gone', () => {
    const onClose = vi.fn()
    const { unmount } = render(<Popup onClose={onClose} />)
    unmount()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).not.toHaveBeenCalled()
  })
})
