import { describe, it, expect, vi, afterEach, beforeAll, afterAll } from 'vitest'
import { useState } from 'react'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Modal } from './Modal'

afterEach(() => {
  // Component restores body overflow on unmount; guard against leakage.
  document.body.style.overflow = ''
})

describe('Modal', () => {
  it('renders nothing when open=false', () => {
    render(<Modal open={false} onClose={() => {}} title="Hidden">body</Modal>)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByText('Hidden')).not.toBeInTheDocument()
  })

  it('renders title and children when open', () => {
    render(<Modal open onClose={() => {}} title="Edit Pilot"><p>Form body</p></Modal>)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('Edit Pilot')).toBeInTheDocument()
    expect(screen.getByText('Form body')).toBeInTheDocument()
  })

  it('calls onClose when the close button is clicked', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<Modal open onClose={onClose} title="T">x</Modal>)
    // Two elements have aria-label "Close dialog" (overlay + X button); click the X.
    const closeButtons = screen.getAllByRole('button', { name: 'Close dialog' })
    await user.click(closeButtons[closeButtons.length - 1])
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('calls onClose on overlay/backdrop click', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<Modal open onClose={onClose} title="T">x</Modal>)
    const overlay = screen.getAllByRole('button', { name: 'Close dialog' })[0]
    await user.click(overlay)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('calls onClose on Escape key', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<Modal open onClose={onClose} title="T">x</Modal>)
    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('locks body scroll while open and restores it on close', () => {
    const { rerender } = render(<Modal open onClose={() => {}} title="T">x</Modal>)
    expect(document.body.style.overflow).toBe('hidden')
    rerender(<Modal open={false} onClose={() => {}} title="T">x</Modal>)
    expect(document.body.style.overflow).toBe('')
  })

  it('sets aria-modal and labels the dialog by its title', () => {
    render(<Modal open onClose={() => {}} title="Labelled">x</Modal>)
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAccessibleName('Labelled')
  })

  // Regression: a parent that re-renders on every keystroke passes a fresh
  // inline onClose each time. When the focus effect depended on that identity it
  // tore down and re-ran per character; its cleanup returns focus to whatever
  // was focused before the modal opened, so the field lost focus mid-typing.
  //
  // The modal must be opened by a real button for this to reproduce: the element
  // focused beforehand has to be focusable for the cleanup's focus() to take.
  it('keeps focus in the field while typing, even as the parent re-renders', async () => {
    function Host() {
      const [open, setOpen] = useState(false)
      const [value, setValue] = useState('')
      return (
        <>
          <button onClick={() => setOpen(true)}>Add event</button>
          <Modal open={open} onClose={() => setOpen(false)} title="Add event">
            <label htmlFor="ev-title">Title</label>
            <input id="ev-title" value={value} onChange={e => setValue(e.target.value)} />
          </Modal>
        </>
      )
    }
    const user = userEvent.setup()
    render(<Host />)

    await user.click(screen.getByRole('button', { name: 'Add event' }))
    const field = screen.getByLabelText('Title')
    await user.click(field)
    await user.keyboard('Meeting')

    expect(field).toHaveValue('Meeting')
    expect(document.activeElement).toBe(field)
  })

  // The trap is what keeps Tab inside the dialog. Without the wrap, Tab off the
  // last control lands on whatever is behind the overlay, which the user cannot
  // see and cannot get back from without a mouse.
  //
  // The trap filters on offsetParent to skip hidden controls, and jsdom has no
  // layout, so every element reports null and the trap sees nothing. Standing in
  // a parent for the duration of these two makes the filter behave as a browser
  // would; the assertions are about the wrap, not the filter.
  describe('focus trap', () => {
    const descriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetParent')

    beforeAll(() => {
      Object.defineProperty(HTMLElement.prototype, 'offsetParent', {
        configurable: true,
        get() { return this.parentElement },
      })
    })

    afterAll(() => {
      if (descriptor) Object.defineProperty(HTMLElement.prototype, 'offsetParent', descriptor)
      else delete HTMLElement.prototype.offsetParent
    })

    // The modal moves focus to its first control on a rAF. Waiting for that
    // settles the starting point; without it the callback lands mid-test and
    // moves focus out from under the assertion.
    async function renderTrapped() {
      render(
        <Modal open onClose={() => {}} title="Trapped">
          <button>First</button>
          <button>Last</button>
        </Modal>
      )
      // Two buttons carry that label: the overlay, and the header X. The trap
      // only looks inside the dialog, so the X is the one in it.
      const dialog = screen.getByRole('dialog')
      const firstInTrap = within(dialog).getByRole('button', { name: 'Close dialog' })
      await waitFor(() => expect(document.activeElement).toBe(firstInTrap))
      return { firstInTrap }
    }

    it('wraps focus from the last control back to the first on Tab', async () => {
      const user = userEvent.setup()
      const { firstInTrap } = await renderTrapped()

      screen.getByRole('button', { name: 'Last' }).focus()
      await user.tab()

      expect(document.activeElement).toBe(firstInTrap)
    })

    it('wraps focus from the first control back to the last on Shift+Tab', async () => {
      const user = userEvent.setup()
      const { firstInTrap } = await renderTrapped()

      firstInTrap.focus()
      await user.tab({ shift: true })

      expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Last' }))
    })
  })
})
