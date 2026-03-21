import { useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'
import { X } from 'lucide-react'

function Modal({ open, onClose, title, children, className }) {
  const overlayRef = useRef(null)

  useEffect(() => {
    if (!open) return

    const handleEscape = (e) => {
      if (e.key === 'Escape') onClose?.()
    }
    document.addEventListener('keydown', handleEscape)
    document.body.style.overflow = 'hidden'

    return () => {
      document.removeEventListener('keydown', handleEscape)
      document.body.style.overflow = ''
    }
  }, [open, onClose])

  if (!open) return null

  const handleOverlayClick = (e) => {
    if (e.target === overlayRef.current) onClose?.()
  }

  return (
    <div
      ref={overlayRef}
      onClick={handleOverlayClick}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm animate-in fade-in"
    >
      <div
        className={cn(
          'relative w-full max-w-lg mx-4 rounded-xl border border-border bg-card text-foreground shadow-lg',
          'animate-in zoom-in-95 fade-in duration-200',
          className
        )}
      >
        <div className="flex items-center justify-between p-6 pb-0">
          {title && (
            <h2 className="text-lg font-semibold text-foreground">{title}</h2>
          )}
          <button
            onClick={onClose}
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
