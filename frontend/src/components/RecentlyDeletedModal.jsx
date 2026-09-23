import { useCallback, useEffect, useState } from 'react'
import { RotateCcw, Trash2, Lock } from 'lucide-react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { Modal } from '@/components/ui/Modal'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { useConfirm } from '@/hooks/useConfirm'
import { formatDateTime } from '@/lib/utils'

/**
 * Deleted photos or documents, which stay on disk until an admin purges them.
 * Supervisors restore; admins purge, except items on legal hold.
 * @param {Object} props
 * @param {'photos'|'documents'} props.kind - Which API collection to list.
 * @param {boolean} props.open - Whether the modal is visible.
 * @param {Function} props.onClose - Called when dismissed.
 * @param {Function} [props.onChanged] - Called after a restore, so the page reloads.
 */
export function RecentlyDeletedModal({ kind, open, onClose, onChanged }) {
  const { isAdmin } = useAuth()
  const toast = useToast()
  // null until the first answer arrives.
  const [items, setItems] = useState(null)
  const [confirmProps, requestConfirm] = useConfirm()

  const load = useCallback(() => {
    api.get(`/${kind}/deleted`)
      .then(setItems)
      .catch(() => setItems([]))
  }, [kind])

  useEffect(() => { if (open) load() }, [open, load])

  const restore = async (item) => {
    try {
      await api.post(`/${kind}/${item.id}/restore`)
      toast.success(`Restored ${item.name}`)
      load()
      onChanged?.()
    } catch (err) {
      toast.error(err.message || 'Could not restore')
    }
  }

  const purge = (item) => {
    requestConfirm({
      title: 'Delete permanently',
      message: `Permanently delete ${item.name}? The file is removed from the server and cannot be recovered.`,
      confirmLabel: 'Delete permanently',
      onConfirm: async () => {
        try {
          await api.delete(`/${kind}/${item.id}/purge`)
          load()
        } catch (err) {
          toast.error(err.message || 'Could not delete')
        }
      },
    })
  }

  return (
    <Modal open={open} onClose={onClose} title="Recently deleted" className="max-w-2xl">
      {items === null && <p className="text-sm text-muted-foreground">Loading...</p>}
      {items?.length === 0 && (
        <p className="text-sm text-muted-foreground">Nothing has been deleted.</p>
      )}
      {items?.length > 0 && (
        <ul className="divide-y divide-border">
          {items.map(item => (
            <li key={item.id} className="flex items-center gap-3 py-2">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-foreground">{item.name}</p>
                <p className="text-xs text-muted-foreground">
                  Deleted {formatDateTime(item.deleted_at)}{item.deleted_by ? ` by ${item.deleted_by}` : ''}
                </p>
              </div>
              {item.legal_hold && (
                <span className="flex items-center gap-1 text-xs text-amber-500">
                  <Lock className="h-3 w-3" /> Legal hold
                </span>
              )}
              <button
                onClick={() => restore(item)}
                className="flex items-center gap-1 rounded-lg bg-secondary px-2 py-1 text-xs text-secondary-foreground hover:opacity-90"
              >
                <RotateCcw className="h-3 w-3" /> Restore
              </button>
              {isAdmin && !item.legal_hold && (
                <button
                  onClick={() => purge(item)}
                  aria-label={`Delete ${item.name} permanently`}
                  className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-destructive hover:bg-destructive/10"
                >
                  <Trash2 className="h-3 w-3" /> Purge
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog {...confirmProps} />
    </Modal>
  )
}
