/**
 * Reusable confirmation dialog built on top of the Modal component.
 */
import { Modal } from './Modal'

/**
 * Confirmation dialog with Cancel and Confirm buttons.
 * @param {Object} props
 * @param {boolean} props.open - Whether the dialog is visible.
 * @param {Function} props.onClose - Callback when the dialog is dismissed.
 * @param {Function} props.onConfirm - Callback when the confirm button is clicked.
 * @param {string} [props.title='Confirm Action'] - Dialog title.
 * @param {string} props.message - Descriptive message shown in the dialog body.
 * @param {string} [props.confirmLabel='Confirm'] - Label for the confirm button.
 * @param {'danger'|'primary'} [props.confirmVariant='danger'] - Button color variant.
 */
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
