import { useCallback, useEffect, useState } from 'react'
import { BookmarkPlus, Copy, Download, Edit2, Plus, Trash2 } from 'lucide-react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { useConfirm } from '@/hooks/useConfirm'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import RequirementForm from './RequirementForm'
import RequirementSettingsCard from './RequirementSettingsCard'
import { SaveTemplateModal, TemplatesCard } from './TemplatesCard'
import { PERIOD_LABELS, targetText } from './RequirementSummary'
import { duplicateOf, fromRequirement, fromTemplate, newForm, toDefinition } from './formState'

const ICON_BUTTON = 'p-1.5 text-muted-foreground hover:text-foreground rounded hover:bg-accent'

function settingValue(rows, key) {
  return (Array.isArray(rows) ? rows : []).find(r => r.key === key)?.value
}

function hasLocation(rows) {
  return [settingValue(rows, 'org_default_lat'), settingValue(rows, 'org_default_lon')]
    .every(v => v !== undefined && v !== null && String(v).trim() !== '')
}

function periodText(req) {
  if (req.period_type === 'custom') return PERIOD_LABELS.custom
  return `${PERIOD_LABELS[req.period_type]}, ${req.recurring ? 'recurring' : 'one time'}`
}

function StatusChip({ active }) {
  const tone = active ? 'bg-success-bg text-success' : 'bg-secondary text-muted-foreground border border-border'
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${tone}`}>{active ? 'Active' : 'Inactive'}</span>
}

function RequirementRow({ req, onEdit, onDuplicate, onTemplate, onDownload, onDelete }) {
  return (
    <li className="flex items-center gap-3 px-3 py-2 bg-muted/30 rounded-lg">
      <div className="flex-1 min-w-0">
        <p className="flex items-center gap-2 text-sm font-medium text-foreground">
          <span className="truncate">{req.name}</span>
          <StatusChip active={req.is_active} />
        </p>
        <p className="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
          <span>{periodText(req)}</span>
          <span>{targetText(req.target_minutes, req.target_flights)}</span>
        </p>
      </div>
      <button type="button" onClick={() => onEdit(req)} aria-label={`Edit ${req.name}`} title="Edit" className={ICON_BUTTON}>
        <Edit2 className="w-4 h-4" />
      </button>
      <button type="button" onClick={() => onDuplicate(req)} aria-label={`Duplicate ${req.name}`} title="Duplicate" className={ICON_BUTTON}>
        <Copy className="w-4 h-4" />
      </button>
      <button type="button" onClick={() => onTemplate(req)} aria-label={`Save ${req.name} as a template`} title="Save as template" className={ICON_BUTTON}>
        <BookmarkPlus className="w-4 h-4" />
      </button>
      {onDownload && (
        <button type="button" onClick={() => onDownload(req)} aria-label={`Download ${req.name} results as CSV`} title="Download CSV" className={ICON_BUTTON}>
          <Download className="w-4 h-4" />
        </button>
      )}
      <button type="button" onClick={() => onDelete(req)} aria-label={`Delete ${req.name}`} title="Delete"
        className="p-1.5 text-danger rounded hover:bg-danger-bg">
        <Trash2 className="w-4 h-4" />
      </button>
    </li>
  )
}

function RequirementList({ requirements, loaded, onNew, ...actions }) {
  return (
    <section aria-labelledby="req-list-title" className="bg-card border border-border rounded-xl p-6">
      <div className="flex items-center justify-between gap-3 mb-1">
        <h3 id="req-list-title" className="text-lg font-semibold text-foreground">Flight Requirements</h3>
        <button type="button" onClick={onNew}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-medium hover:opacity-90">
          <Plus className="w-3.5 h-3.5" aria-hidden="true" /> New requirement
        </button>
      </div>
      <p className="text-sm text-muted-foreground mb-4">
        Assign flight time pilots must log in a period, such as 15 minutes on each model every quarter. Currency rules are separate and do not change.
      </p>
      {loaded && requirements.length === 0 && (
        <p className="text-sm text-muted-foreground px-3 py-4 bg-muted/30 rounded-lg text-center">
          No requirements yet. Use New requirement to assign your first one, for example 1 hour every month.
        </p>
      )}
      <ul className="space-y-2">
        {requirements.map(req => <RequirementRow key={req.id} req={req} {...actions} />)}
      </ul>
    </section>
  )
}

/** Loads what the builder needs once: fleet models, purposes, pilots, the unit location and the settings. */
function useBuilderData() {
  const [data, setData] = useState({ models: null, modelsError: false, purposes: [], pilots: [], locationSet: false, settings: null })
  useEffect(() => {
    const merge = (patch) => setData(d => ({ ...d, ...patch }))
    api.get('/requirements/models').then(models => merge({ models })).catch(() => merge({ modelsError: true }))
    api.get('/flights/purposes/list').then(purposes => merge({ purposes })).catch(() => {})
    api.get('/pilots/options').then(pilots => merge({ pilots })).catch(() => {})
    api.get('/settings').then(rows => merge({ locationSet: hasLocation(rows) })).catch(() => {})
    api.get('/requirements/settings').then(settings => merge({ settings })).catch(() => {})
  }, [])
  return [data, setData]
}

/** Settings, Flight Requirements: the requirement list and builder, templates and settings. */
export default function RequirementsTab() {
  const { can } = useAuth()
  const toast = useToast()
  const [confirmProps, requestConfirm] = useConfirm()
  const [requirements, setRequirements] = useState([])
  const [loaded, setLoaded] = useState(false)
  const [templates, setTemplates] = useState([])
  const [editing, setEditing] = useState(null)
  const [templateSource, setTemplateSource] = useState(null)
  const [data, setData] = useBuilderData()

  const loadRequirements = useCallback(() => api.get('/requirements')
    .then(rows => { setRequirements(rows); setLoaded(true) })
    .catch(err => toast.error(err.message)), [toast])
  const loadTemplates = useCallback(() => api.get('/requirements/templates')
    .then(setTemplates)
    .catch(err => toast.error(err.message)), [toast])

  useEffect(() => {
    loadRequirements()
    loadTemplates()
  }, [loadRequirements, loadTemplates])

  // Each opening gets a new key so the form starts from its own initial state.
  const open = (title, initial, id = null) => setEditing({ key: Date.now(), title, initial, id })

  const submit = async (body) => {
    if (editing.id) await api.patch(`/requirements/${editing.id}`, body)
    else await api.post('/requirements', body)
    toast.success('Requirement saved')
    setEditing(null)
    loadRequirements()
  }

  const remove = (req) => requestConfirm({
    title: 'Delete requirement',
    message: `Delete "${req.name}"? A requirement with saved results cannot be deleted; switch it off instead.`,
    confirmLabel: 'Delete',
    onConfirm: () => api.delete(`/requirements/${req.id}`)
      .then(() => { toast.success('Requirement deleted'); loadRequirements() })
      .catch(err => toast.error(err.message)),
  })

  const download = (req) => api.download(`/export/requirements/${req.id}/csv`)
    .catch(err => toast.error(err.message))

  const saveTemplate = (name) => api.post('/requirements/templates', {
    name, settings: toDefinition(fromRequirement(templateSource)),
  }).then(() => { toast.success('Template saved'); loadTemplates(); return true })
    .catch(err => { toast.error(err.message); return false })

  const renameTemplate = (template, name) => api.patch(`/requirements/templates/${template.id}`, { name })
    .then(() => { loadTemplates(); return true })
    .catch(err => { toast.error(err.message); return false })

  const removeTemplate = (template) => requestConfirm({
    title: 'Delete template',
    message: `Delete the template "${template.name}"? Requirements made from it do not change.`,
    confirmLabel: 'Delete',
    onConfirm: () => api.delete(`/requirements/templates/${template.id}`)
      .then(loadTemplates)
      .catch(err => toast.error(err.message)),
  })

  const saveSettings = (settings) => api.put('/requirements/settings', settings)
    .then(saved => { setData(d => ({ ...d, settings: saved })); toast.success('Requirement settings saved'); return true })
    .catch(err => { toast.error(err.message); return false })

  return (
    <div className="space-y-6 max-w-3xl">
      {editing && (
        <RequirementForm
          key={editing.key}
          title={editing.title}
          initial={editing.initial}
          models={data.models}
          modelsError={data.modelsError}
          purposes={data.purposes}
          pilots={data.pilots}
          locationSet={data.locationSet}
          fiscalStartMonth={data.settings?.fiscal_year_start_month ?? 10}
          onSubmit={submit}
          onCancel={() => setEditing(null)}
        />
      )}
      <RequirementList
        requirements={requirements}
        loaded={loaded}
        onNew={() => open('New requirement', newForm())}
        onEdit={req => open(`Edit ${req.name}`, fromRequirement(req), req.id)}
        onDuplicate={req => open('New requirement', duplicateOf(req))}
        onTemplate={setTemplateSource}
        onDownload={can('reports.export') ? download : null}
        onDelete={remove}
      />
      <TemplatesCard
        templates={templates}
        onUse={t => open('New requirement', fromTemplate(t))}
        onRename={renameTemplate}
        onDelete={removeTemplate}
      />
      <RequirementSettingsCard settings={data.settings} onSave={saveSettings} />
      {templateSource && (
        <SaveTemplateModal requirement={templateSource} onSave={saveTemplate} onClose={() => setTemplateSource(null)} />
      )}
      <ConfirmDialog {...confirmProps} />
    </div>
  )
}
