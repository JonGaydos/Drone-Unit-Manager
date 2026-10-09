/**
 * Modal wrapper around the DocumentUpload panel, for attaching documents to
 * entities that have no detail page (e.g. maintenance records and schedules).
 */
import DocumentUpload from '@/components/DocumentUpload'
import { Modal } from '@/components/ui/Modal'

/**
 * @param {Object} props
 * @param {string} props.entityType - Parent entity type (e.g. "maintenance", "maintenance_schedule").
 * @param {number|string} props.entityId - Parent entity ID.
 * @param {string} [props.title] - Context shown in the modal header.
 * @param {Function} props.onClose - Called when the modal is dismissed.
 */
export function DocumentsModal({ entityType, entityId, title, onClose }) {
  return (
    <Modal open onClose={onClose} title="Documents">
      {title && <p className="text-sm text-muted-foreground truncate -mt-4 mb-4">{title}</p>}
      <DocumentUpload entityType={entityType} entityId={entityId} />
    </Modal>
  )
}
