import { useState } from 'react'
import { Check, Edit2, FilePlus, Trash2, X } from 'lucide-react'
import { Modal } from '@/components/ui/Modal'

const INPUT = 'w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring'
const ICON_BUTTON = 'p-1.5 text-muted-foreground hover:text-foreground rounded hover:bg-accent'

function RenameForm({ template, onRename, onDone }) {
  const [name, setName] = useState(template.name)
  const save = async (e) => {
    e.preventDefault()
    if (await onRename(template, name.trim())) onDone()
  }
  return (
    <form onSubmit={save} className="flex flex-1 items-center gap-2 min-w-0">
      <input aria-label={`New name for ${template.name}`} value={name} onChange={e => setName(e.target.value)}
        required maxLength={200} className={`${INPUT} py-1.5`} />
      <button type="submit" aria-label="Save name" title="Save name" disabled={!name.trim()} className={ICON_BUTTON}>
        <Check className="w-4 h-4" />
      </button>
      <button type="button" aria-label="Cancel rename" title="Cancel" onClick={onDone} className={ICON_BUTTON}>
        <X className="w-4 h-4" />
      </button>
    </form>
  )
}

function TemplateRow({ template, onUse, onRename, onDelete }) {
  const [renaming, setRenaming] = useState(false)
  if (renaming) {
    return (
      <li className="flex items-center gap-2 px-3 py-2 bg-muted/30 rounded-lg">
        <RenameForm template={template} onRename={onRename} onDone={() => setRenaming(false)} />
      </li>
    )
  }
  return (
    <li className="flex items-center gap-2 px-3 py-2 bg-muted/30 rounded-lg">
      <span className="flex-1 min-w-0 truncate text-sm font-medium text-foreground">{template.name}</span>
      <button type="button" onClick={() => onUse(template)} aria-label={`New from template ${template.name}`}
        className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-foreground rounded-lg border border-border hover:bg-accent">
        <FilePlus className="w-3.5 h-3.5" aria-hidden="true" /> New from template
      </button>
      <button type="button" onClick={() => setRenaming(true)} aria-label={`Rename ${template.name}`} title="Rename" className={ICON_BUTTON}>
        <Edit2 className="w-4 h-4" />
      </button>
      <button type="button" onClick={() => onDelete(template)} aria-label={`Delete template ${template.name}`} title="Delete"
        className="p-1.5 text-danger rounded hover:bg-danger-bg">
        <Trash2 className="w-4 h-4" />
      </button>
    </li>
  )
}

/** Saved requirement settings to start new requirements from. */
export function TemplatesCard({ templates, onUse, onRename, onDelete }) {
  return (
    <section aria-labelledby="req-templates-title" className="bg-card border border-border rounded-xl p-6">
      <h2 id="req-templates-title" className="text-lg font-semibold text-foreground mb-1">Templates</h2>
      <p className="text-sm text-muted-foreground mb-4">
        A template keeps every setting except the dates and pilots. Changing or deleting one never changes requirements made from it.
      </p>
      {templates.length === 0 ? (
        <p className="text-sm text-muted-foreground px-3 py-4 bg-muted/30 rounded-lg text-center">
          No templates yet. Use Save as template on a requirement to reuse its settings.
        </p>
      ) : (
        <ul className="space-y-2">
          {templates.map(t => (
            <TemplateRow key={t.id} template={t} onUse={onUse} onRename={onRename} onDelete={onDelete} />
          ))}
        </ul>
      )}
    </section>
  )
}

/** Name a requirement's settings as a template. `onSave(name)` resolves to whether it saved. */
export function SaveTemplateModal({ requirement, onSave, onClose }) {
  const [name, setName] = useState(requirement.name)
  const [saving, setSaving] = useState(false)
  const save = async (e) => {
    e.preventDefault()
    setSaving(true)
    const saved = await onSave(name.trim())
    setSaving(false)
    if (saved) onClose()
  }
  return (
    <Modal open onClose={onClose} title="Save as template" className="max-w-md">
      <form onSubmit={save} className="space-y-3">
        <div>
          <label htmlFor="req-template-name" className="block text-sm font-medium text-foreground mb-1">Template name</label>
          <input id="req-template-name" value={name} onChange={e => setName(e.target.value)} required maxLength={200} className={INPUT} />
        </div>
        <p className="text-xs text-muted-foreground">The template keeps every setting except the dates and pilots.</p>
        <div className="flex gap-2 pt-2">
          <button type="submit" disabled={saving || !name.trim()}
            className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50">
            Save template
          </button>
          <button type="button" onClick={onClose} className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90">
            Cancel
          </button>
        </div>
      </form>
    </Modal>
  )
}
