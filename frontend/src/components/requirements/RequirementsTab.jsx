import { useCallback, useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { BookmarkPlus, Copy, Download, Edit2, Plus, Power, Trash2 } from 'lucide-react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { useConfirm } from '@/hooks/useConfirm'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import RequirementForm from './RequirementForm'
import { SaveTemplateModal } from './TemplatesCard'
import { PendingLines, PeriodCounts, PilotProgressList, RollingCounts, RollingPilotList } from './PeriodProgress'
import { PERIOD_LABELS, targetText } from './RequirementSummary'
import { lapseStarts } from './progress'
import { useRequirementFlags } from './useRequirementFlags'
import { duplicateOf, fromRequirement, fromTemplate, newForm, toDefinition } from './formState'

const ICON_BUTTON = 'p-1.5 text-muted-foreground hover:text-foreground rounded hover:bg-accent'

function settingValue(rows, key) {
  return (Array.isArray(rows) ? rows : []).find(r => r.key === key)?.value
}

function hasLocation(rows) {
  return [settingValue(rows, 'org_default_lat'), settingValue(rows, 'org_default_lon')]
    .every(v => v !== undefined && v !== null && String(v).trim() !== '')
}

/** "days", or "day" for a one-day window. */
function rollingUnit(req) {
  return req.span_length === 1 ? req.span_unit.slice(0, -1) : req.span_unit
}

function periodText(req) {
  if (req.period_type === 'custom') return PERIOD_LABELS.custom
  if (req.period_type === 'rolling') return `Rolling ${req.span_length} ${rollingUnit(req)}`
  return `${PERIOD_LABELS[req.period_type]}, ${req.recurring ? 'recurring' : 'one time'}`
}

function StatusChip({ active }) {
  const tone = active ? 'bg-success-bg text-success' : 'bg-secondary text-muted-foreground border border-border'
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${tone}`}>{active ? 'Active' : 'Inactive'}</span>
}

/** One-click on and off. The label says what the click does, so the state stays readable from the chip. */
function SwitchButton({ req, onSwitch }) {
  const label = req.is_active ? 'Switch off' : 'Switch on'
  return (
    <button type="button" onClick={() => onSwitch(req)} aria-label={`${label} ${req.name}`}
      className="flex items-center gap-1.5 px-2.5 py-1 mr-1 rounded-lg border border-border text-xs font-medium text-foreground hover:bg-accent">
      <Power className="w-3.5 h-3.5" aria-hidden="true" /> {label}
    </button>
  )
}

function EditButtons({ req, manage }) {
  return (
    <>
      <button type="button" onClick={() => manage.onEdit(req)} aria-label={`Edit ${req.name}`} title="Edit" className={ICON_BUTTON}>
        <Edit2 className="w-4 h-4" />
      </button>
      <button type="button" onClick={() => manage.onDuplicate(req)} aria-label={`Duplicate ${req.name}`} title="Duplicate" className={ICON_BUTTON}>
        <Copy className="w-4 h-4" />
      </button>
      <button type="button" onClick={() => manage.onTemplate(req)} aria-label={`Save ${req.name} as a template`} title="Save as template" className={ICON_BUTTON}>
        <BookmarkPlus className="w-4 h-4" />
      </button>
    </>
  )
}

function PeriodLine({ current }) {
  if (!current) return <p className="text-xs text-muted-foreground">No period is open</p>
  return <PeriodCounts current={current} />
}

/** A rolling requirement's standing: the counts and each pilot's status with its date. */
function RollingProgress({ status, flags }) {
  return (
    <div className="mt-2.5 pt-2.5 border-t border-border space-y-1.5">
      <RollingCounts rolling={status.rolling} />
      <RollingPilotList req={status} lapsedSince={lapseStarts(flags, status.requirement_id)} />
    </div>
  )
}

/** The current period of an active requirement, or a rolling one's window, as the dashboard tile shows it. */
function RequirementProgress({ status, flags }) {
  if (!status) return null
  if (status.rolling) return <RollingProgress status={status} flags={flags} />
  return (
    <div className="mt-2.5 pt-2.5 border-t border-border space-y-1.5">
      <PeriodLine current={status.current_period} />
      <PilotProgressList req={status} />
      <PendingLines periods={status.pending_periods} />
    </div>
  )
}

/** `manage` holds the manager actions, or is null for someone who may only view. */
function RequirementRow({ req, status, flags, manage, onDownload }) {
  return (
    <li className="px-3 py-2.5 bg-muted/30 rounded-lg">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <div className="flex-1 min-w-48">
          <p className="flex items-center gap-2 text-sm font-medium text-foreground">
            <span className="truncate">{req.name}</span>
            <StatusChip active={req.is_active} />
          </p>
          <p className="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
            <span>{periodText(req)}</span>
            <span>{targetText(req.target_minutes, req.target_flights)}</span>
          </p>
        </div>
        <div className="flex items-center">
          {manage && <SwitchButton req={req} onSwitch={manage.onSwitch} />}
          {manage && <EditButtons req={req} manage={manage} />}
          {onDownload && (
            <button type="button" onClick={() => onDownload(req)} aria-label={`Download ${req.name} results as CSV`} title="Download CSV" className={ICON_BUTTON}>
              <Download className="w-4 h-4" />
            </button>
          )}
          {manage && (
            <button type="button" onClick={() => manage.onDelete(req)} aria-label={`Delete ${req.name}`} title="Delete"
              className="p-1.5 text-danger rounded hover:bg-danger-bg">
              <Trash2 className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
      <RequirementProgress status={status} flags={flags} />
    </li>
  )
}

function emptyListText(canManage) {
  if (canManage) return 'No requirements yet. Use New requirement to assign your first one, for example 1 hour every month.'
  return 'No flight requirements yet.'
}

function RequirementList({ requirements, statuses, flags, loaded, manage, onNew, onDownload }) {
  return (
    <section aria-labelledby="req-list-title" className="bg-card border border-border rounded-xl p-6">
      <div className="flex items-center justify-between gap-3 mb-4">
        <h2 id="req-list-title" className="text-lg font-semibold text-foreground">Requirements</h2>
        {manage && (
          <button type="button" onClick={onNew}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-medium hover:opacity-90">
            <Plus className="w-3.5 h-3.5" aria-hidden="true" /> New requirement
          </button>
        )}
      </div>
      {loaded && requirements.length === 0 && (
        <p className="text-sm text-muted-foreground px-3 py-4 bg-muted/30 rounded-lg text-center">{emptyListText(Boolean(manage))}</p>
      )}
      <ul className="space-y-2">
        {requirements.map(req => (
          <RequirementRow key={req.id} req={req} status={statuses[req.id]} flags={flags} manage={manage} onDownload={onDownload} />
        ))}
      </ul>
    </section>
  )
}

/** Loads what the builder needs once, for a manager only: fleet models,
 *  purposes, pilots, the unit location and the settings. */
function useBuilderData(enabled) {
  const [data, setData] = useState({ models: null, modelsError: false, purposes: [], pilots: [], locationSet: false, settings: null })
  useEffect(() => {
    if (!enabled) return
    const merge = (patch) => setData(d => ({ ...d, ...patch }))
    api.get('/requirements/models').then(models => merge({ models })).catch(() => merge({ modelsError: true }))
    api.get('/flights/purposes/list').then(purposes => merge({ purposes })).catch(() => {})
    api.get('/pilots/options').then(pilots => merge({ pilots })).catch(() => {})
    api.get('/settings').then(rows => merge({ locationSet: hasLocation(rows) })).catch(() => {})
    api.get('/requirements/settings').then(settings => merge({ settings })).catch(() => {})
  }, [enabled])
  return data
}

/** A template the Setup tab sent here to start a new requirement from, taken
 *  once: the location state is cleared so a reload does not open it again. */
function useTemplateFromSetup(open) {
  const location = useLocation()
  const navigate = useNavigate()
  const template = location.state?.template
  useEffect(() => {
    if (!template) return
    open('New requirement', fromTemplate(template))
    navigate(`${location.pathname}${location.search}`, { replace: true, state: null })
  }, [template, open, navigate, location.pathname, location.search])
}

/** The Flight Requirements tab of the Compliance page: the requirement list
 *  with each one's progress for everyone with requirements.view; the builder,
 *  Switch on/off and Save as template with requirements.manage. Templates and
 *  settings are on the Setup tab. */
export default function RequirementsTab() {
  const { can } = useAuth()
  const canManage = can('requirements.manage')
  const toast = useToast()
  const [confirmProps, requestConfirm] = useConfirm()
  const [requirements, setRequirements] = useState([])
  const [statuses, setStatuses] = useState({})
  const [loaded, setLoaded] = useState(false)
  const [editing, setEditing] = useState(null)
  const [templateSource, setTemplateSource] = useState(null)
  const data = useBuilderData(canManage)
  const flags = useRequirementFlags(true)

  const loadRequirements = useCallback(() => api.get('/requirements')
    .then(rows => { setRequirements(rows); setLoaded(true) })
    .catch(err => toast.error(err.message)), [toast])
  const loadStatuses = useCallback(() => api.get('/requirements/status')
    .then(status => setStatuses(Object.fromEntries(status.requirements.map(r => [r.requirement_id, r]))))
    .catch(err => toast.error(err.message)), [toast])
  const refresh = () => {
    loadRequirements()
    loadStatuses()
  }

  useEffect(() => {
    loadRequirements()
    loadStatuses()
  }, [loadRequirements, loadStatuses])

  // Each opening gets a new key so the form starts from its own initial state.
  const open = useCallback((title, initial, id = null) => setEditing({ key: Date.now(), title, initial, id }), [])
  useTemplateFromSetup(open)

  const submit = async (body) => {
    if (editing.id) await api.patch(`/requirements/${editing.id}`, body)
    else await api.post('/requirements', body)
    toast.success('Requirement saved')
    setEditing(null)
    refresh()
  }

  const setActive = (req, isActive) => api.patch(`/requirements/${req.id}`, { is_active: isActive })
    .then(() => { toast.success(isActive ? 'Requirement switched on' : 'Requirement switched off'); refresh() })
    .catch(err => toast.error(err.message))

  const switchActive = (req) => {
    if (!req.is_active) return setActive(req, true)
    return requestConfirm({
      title: 'Switch off requirement',
      message: `Switch off "${req.name}"? It stops tracking progress, leaves the dashboard and sends no emails. The months it stays off are recorded as excused. You can switch it on again at any time.`,
      confirmLabel: 'Switch off',
      onConfirm: () => setActive(req, false),
    })
  }

  const remove = (req) => requestConfirm({
    title: 'Delete requirement',
    message: `Delete "${req.name}"? A requirement with saved results cannot be deleted; switch it off instead.`,
    confirmLabel: 'Delete',
    onConfirm: () => api.delete(`/requirements/${req.id}`)
      .then(() => { toast.success('Requirement deleted'); refresh() })
      .catch(err => toast.error(err.message)),
  })

  const download = (req) => api.download(`/export/requirements/${req.id}/csv`)
    .catch(err => toast.error(err.message))

  const saveTemplate = (name) => api.post('/requirements/templates', {
    name, settings: toDefinition(fromRequirement(templateSource)),
  }).then(() => { toast.success('Template saved'); return true })
    .catch(err => { toast.error(err.message); return false })

  return (
    <div className="space-y-6 max-w-3xl">
      {editing && (
        <RequirementForm
          key={editing.key}
          title={editing.title}
          initial={editing.initial}
          isNew={!editing.id}
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
        statuses={statuses}
        flags={flags}
        loaded={loaded}
        manage={canManage ? {
          onEdit: req => open(`Edit ${req.name}`, fromRequirement(req), req.id),
          onDuplicate: req => open('New requirement', duplicateOf(req)),
          onTemplate: setTemplateSource,
          onSwitch: switchActive,
          onDelete: remove,
        } : null}
        onNew={() => open('New requirement', newForm())}
        onDownload={can('reports.export') ? download : null}
      />
      {templateSource && (
        <SaveTemplateModal requirement={templateSource} onSave={saveTemplate} onClose={() => setTemplateSource(null)} />
      )}
      <ConfirmDialog {...confirmProps} />
    </div>
  )
}
