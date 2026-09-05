/**
 * Accessible modal dialog with backdrop overlay, focus trap, and keyboard dismissal.
 */
import { useEffect, useRef, useCallback, useId } from 'react'
import { cn } from '@/lib/utils'
import { X } from 'lucide-react'

/**
 * Modal dialog component with backdrop, focus trap, and Escape key support.
 * Locks body scroll while open and auto-focuses the first focusable element.
 * @param {Object} props
 * @param {boolean} props.open - Whether the modal is visible.
 * @param {Function} props.onClose - Callback when the modal is dismissed.
 * @param {string} [props.title] - Optional title displayed in the header.
 * @param {React.ReactNode} props.children - Modal body content.
 * @param {string} [props.className] - Additional CSS classes for the modal container.
 */
function Modal({ open, onClose, title, children, className }) {
  const overlayRef = useRef(null)
  const modalRef = useRef(null)
  const titleId = useId()

  // Callers almost always pass an inline arrow for onClose, so its identity
  // changes on every render of the parent. Read it through a ref instead of
  // depending on it: without this the focus effect below tore down and re-ran on
  // every keystroke, stealing focus back to the close button mid-typing.
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    onCloseRef.current = onClose
  }, [onClose])

  const stableOnClose = useCallback(() => {
    onCloseRef.current?.()
  }, [])

  useEffect(() => {
    if (!open) return

    // Remember the element focused before the modal opened so focus can be
    // restored to it on close.
    const previouslyFocused = document.activeElement

    // Returns the visible, enabled focusable elements inside the modal.
    const getFocusable = () => {
      if (!modalRef.current) return []
      const nodes = modalRef.current.querySelectorAll(
        'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])'
      )
      return Array.from(nodes).filter(
        (el) => !el.hidden && el.offsetParent !== null
      )
    }

    const handleEscape = (e) => {
      if (e.key === 'Escape') stableOnClose()
    }

    // Focus trap
    const handleTab = (e) => {
      if (e.key !== 'Tab') return
      const focusable = getFocusable()
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable.at(-1)
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleEscape)
    document.addEventListener('keydown', handleTab)
    document.body.style.overflow = 'hidden'

    // Focus first focusable element
    requestAnimationFrame(() => {
      const focusable = getFocusable()
      focusable[0]?.focus()
    })

    return () => {
      document.removeEventListener('keydown', handleEscape)
      document.removeEventListener('keydown', handleTab)
      document.body.style.overflow = ''
      // Restore focus to the element that had it before the modal opened.
      if (previouslyFocused && typeof previouslyFocused.focus === 'function') {
        previouslyFocused.focus()
      }
    }
  }, [open, stableOnClose])

  if (!open) return null

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-md animate-[fadeIn_150ms_ease]"
    >
      <button className="absolute inset-0 bg-transparent cursor-default" onClick={stableOnClose} aria-label="Close dialog" />
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        className={cn(
          'relative w-full max-w-lg mx-4 rounded-xl border border-border bg-card text-foreground shadow-lg',
          'animate-[slideUp_200ms_ease]',
          className
        )}
      >
        <div className="flex items-center justify-between p-6 pb-0">
          {title && (
            <h2 id={titleId} className="text-lg font-semibold text-foreground">{title}</h2>
          )}
          <button
            onClick={stableOnClose}
            aria-label="Close dialog"
            className="ml-auto rounded-lg p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors cursor-pointer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="p-6">{children}</div>
      </div>
    </div>
  )
}

export { Modal }
