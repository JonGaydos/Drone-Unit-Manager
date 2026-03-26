import { Modal } from './Modal'

export function ConfirmDialog({ open, onClose, onConfirm, title, message, confirmLabel = 'Confirm', confirmVariant = 'danger' }) {
  const variants = {
    danger: 'bg-destructive text-destructive-foreground hover:opacity-90',
    primary: 'bg-primary text-primary-foreground hover:opacity-90',
  }

  return (
    <Modal open={open} onClose={onClose} title={title || 'Confirm Action'}>
      <p className="text-sm text-muted-foreground mb-6">{message}</p>
      <div className="flex gap-2 justify-end">
        <button
          onClick={onClose}
          className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90"
        >
          Cancel
        </button>
        <button
          onClick={() => { onConfirm(); onClose() }}
          className={`px-4 py-2 rounded-lg text-sm font-medium ${variants[confirmVariant] || variants.danger}`}
        >
          {confirmLabel}
        </button>
      </div>
    </Modal>
  )
}
