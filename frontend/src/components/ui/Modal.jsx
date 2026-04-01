/**
 * Accessible modal dialog with backdrop overlay, focus trap, and keyboard dismissal.
 */
import { useEffect, useRef, useCallback } from 'react'
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

  const stableOnClose = useCallback(() => {
    onClose?.()
  }, [onClose])

  useEffect(() => {
    if (!open) return

    const handleEscape = (e) => {
      if (e.key === 'Escape') stableOnClose()
    }

    // Focus trap
    const handleTab = (e) => {
      if (e.key !== 'Tab' || !modalRef.current) return
      const focusable = modalRef.current.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      )
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
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
      if (modalRef.current) {
        const focusable = modalRef.current.querySelector(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        )
        focusable?.focus()
      }
    })

    return () => {
      document.removeEventListener('keydown', handleEscape)
      document.removeEventListener('keydown', handleTab)
      document.body.style.overflow = ''
    }
  }, [open, stableOnClose])

  if (!open) return null

  const handleOverlayClick = (e) => {
    if (e.target === overlayRef.current) stableOnClose()
  }

  return (
    <div
      ref={overlayRef}
      onClick={handleOverlayClick}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-md animate-[fadeIn_150ms_ease]"
    >
      <div
        ref={modalRef}
        className={cn(
          'relative w-full max-w-lg mx-4 rounded-xl border border-border bg-card text-foreground shadow-lg',
          'animate-[slideUp_200ms_ease]',
          className
        )}
      >
        <div className="flex items-center justify-between p-6 pb-0">
          {title && (
            <h2 className="text-lg font-semibold text-foreground">{title}</h2>
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
