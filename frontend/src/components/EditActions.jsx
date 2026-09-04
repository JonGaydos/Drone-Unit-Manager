import { Save, X, Loader2 } from 'lucide-react'

/**
 * Save/Cancel button pair for the fleet detail pages' inline edit forms.
 */
export default function EditActions({ saving, onSave, onCancel }) {
  return (
    <div className="flex gap-2">
      <button onClick={onSave} disabled={saving}
        className="flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50">
        {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Save
      </button>
      <button onClick={onCancel}
        className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90">
        <X className="w-4 h-4" /> Cancel
      </button>
    </div>
  )
}
