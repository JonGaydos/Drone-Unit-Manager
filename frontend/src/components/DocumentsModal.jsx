/**
 * Modal wrapper around the DocumentUpload panel, for attaching documents to
 * entities that have no detail page (e.g. maintenance records and schedules).
 */
import { X } from 'lucide-react'
import DocumentUpload from '@/components/DocumentUpload'

/**
 * @param {Object} props
 * @param {string} props.entityType - Parent entity type (e.g. "maintenance", "maintenance_schedule").
 * @param {number|string} props.entityId - Parent entity ID.
 * @param {string} [props.title] - Context shown in the modal header.
 * @param {Function} props.onClose - Called when the modal is dismissed.
 */
export function DocumentsModal({ entityType, entityId, title, onClose }) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <button className="absolute inset-0 bg-transparent cursor-default" onClick={onClose} aria-label="Close dialog" />
      <div className="relative bg-popover border border-border rounded-xl p-6 w-full max-w-lg shadow-xl">
        <div className="flex items-start justify-between mb-4 gap-4">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold text-foreground">Documents</h2>
            {title && <p className="text-sm text-muted-foreground truncate">{title}</p>}
          </div>
          <button onClick={onClose} className="p-1 text-muted-foreground hover:text-foreground shrink-0" aria-label="Close">
            <X className="w-4 h-4" />
          </button>
        </div>
        <DocumentUpload entityType={entityType} entityId={entityId} />
      </div>
    </div>
  )
}
