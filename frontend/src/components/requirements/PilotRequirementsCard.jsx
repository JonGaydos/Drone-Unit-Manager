/**
 * Pilot detail "Flight Requirements" card: the pilot's progress in each
 * active requirement's current period and in periods still in review, their
 * standing on each rolling requirement and their lapses, the saved history, Excuse and Un-excuse (requirements.excuse), Recalculate on a
 * saved period (admins) and the pilot's history of each requirement as CSV
 * (reports.export). Renders nothing without requirements.view, or until the
 * pilot has something to show.
 */
import { useEffect, useId, useState } from 'react'
import { Download, Target } from 'lucide-react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { formatDate } from '@/lib/utils'
import { useConfirm } from '@/hooks/useConfirm'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { RequirementFlagBadges, RequirementStatusChip } from './RequirementBadges'
import { LapseHistory, RollingExcuseModal, RollingSection } from './PilotRollingSection'
import { useRequirementFlags } from './useRequirementFlags'
import { countText, daysLeftText, excusalText, excuseAction, periodText, progressText } from './progress'

const SMALL_BUTTON = 'px-2 py-1 text-xs rounded-md border border-border text-foreground hover:bg-accent whitespace-nowrap'

/** What an excusal needs from a progress or history row. */
function periodOf(row) {
  if (row.period) return { requirementId: row.requirement_id, name: row.name, start: row.period.start, end: row.period.end }
  return { requirementId: row.requirement_id, name: row.name, start: row.period_start, end: row.period_end }
}

function ExcuseButton({ row, onExcuse, onUnexcuse }) {
  const action = excuseAction(row)
  if (!action) return null
  const period = periodOf(row)
  const verb = action === 'excuse' ? 'Excuse' : 'Un-excuse'
  const run = action === 'excuse' ? onExcuse : onUnexcuse
  return (
    <button type="button" onClick={() => run(period)} className={SMALL_BUTTON}
      aria-label={`${verb} ${period.name}, ${periodText(period.start, period.end)}`}>
      {verb}
    </button>
  )
}

function ProgressNotes({ row }) {
  const notes = []
  if (row.excluded_no_takeoff > 0) notes.push(`${countText(row.excluded_no_takeoff, 'flight')} left out: no takeoff time`)
  if (row.unreviewed_in_period > 0) notes.push(`${countText(row.unreviewed_in_period, 'flight')} awaiting review`)
  const excusal = excusalText(row)
  if (excusal) notes.push(excusal)
  return notes.map(note => <p key={note} className="text-xs text-muted-foreground">{note}</p>)
}

function ProgressRow({ row, when, target, actions }) {
  return (
    <li className="px-4 py-3 flex flex-wrap items-start gap-x-4 gap-y-2">
      <div className="flex-1 min-w-[12rem] space-y-0.5">
        <p className="text-sm font-medium text-foreground">{row.name}</p>
        <p className="text-xs text-muted-foreground">{periodText(row.period.start, row.period.end)} · {when(row.period)}</p>
        <p className="text-sm text-foreground tabular-nums">{progressText(row.totals, row.met_by_model, target)}</p>
        <ProgressNotes row={row} />
      </div>
      <RequirementStatusChip status={row.status} />
      {actions && <ExcuseButton row={row} {...actions} />}
    </li>
  )
}

function ProgressSection({ title, rows, when, targets, actions }) {
  const id = useId()
  if (rows.length === 0) return null
  return (
    <section aria-labelledby={id} className="border-b border-border">
      <h4 id={id} className="px-4 pt-3 text-xs font-medium text-muted-foreground">{title}</h4>
      <ul className="divide-y divide-border/50">
        {rows.map(row => (
          <ProgressRow key={`${row.requirement_id}-${row.period.start}`} row={row} when={when}
            target={targets[row.requirement_id] || {}} actions={actions} />
        ))}
      </ul>
    </section>
  )
}

function RecalculateButton({ row, onRecalculate }) {
  const period = periodOf(row)
  return (
    <button type="button" onClick={() => onRecalculate(period)} className={SMALL_BUTTON}
      aria-label={`Recalculate ${period.name}, ${periodText(period.start, period.end)}`}>
      Recalculate
    </button>
  )
}

function HistoryActions({ row, actions, recalculable, onRecalculate }) {
  return (
    <div className="flex justify-end gap-2">
      {actions && <ExcuseButton row={row} {...actions} />}
      {recalculable && <RecalculateButton row={row} onRecalculate={onRecalculate} />}
    </div>
  )
}

/** Saved periods; `recalculable` adds Recalculate (admins). */
function HistoryTable({ rows, actions, recalculable, onRecalculate }) {
  if (rows.length === 0) return null
  const withActions = Boolean(actions || recalculable)
  return (
    <div className="overflow-x-auto">
      <table aria-label="Requirement history" className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/30">
            <th className="text-left px-4 py-2 text-foreground font-medium">Requirement</th>
            <th className="text-left px-4 py-2 text-foreground font-medium">Period</th>
            <th className="text-left px-4 py-2 text-foreground font-medium">Flown</th>
            <th className="text-left px-4 py-2 text-foreground font-medium">Result</th>
            {withActions && <th className="px-4 py-2"><span className="sr-only">Actions</span></th>}
          </tr>
        </thead>
        <tbody>
          {rows.map(row => (
            <tr key={row.result_id} className="border-b border-border/50 align-top">
              <td className="px-4 py-2 text-foreground">{row.name}</td>
              <td className="px-4 py-2 text-foreground whitespace-nowrap">{periodText(row.period_start, row.period_end)}</td>
              <td className="px-4 py-2 text-foreground tabular-nums">{progressText(row.totals, null, row.target_snapshot || {})}</td>
              <td className="px-4 py-2">
                <RequirementStatusChip status={row.status} />
                {row.excused && <p className="text-xs text-muted-foreground mt-1">{excusalText(row)}</p>}
              </td>
              {withActions && (
                <td className="px-4 py-2">
                  <HistoryActions row={row} actions={actions} recalculable={recalculable} onRecalculate={onRecalculate} />
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** One download per requirement in the card: this pilot's saved results for it. */
function CsvLinks({ requirements, onDownload }) {
  return (
    <ul className="px-4 py-3 border-t border-border flex flex-wrap items-center gap-x-4 gap-y-2">
      {requirements.map(req => (
        <li key={req.id} className="flex items-center gap-2 text-xs text-muted-foreground">
          {requirements.length > 1 && <span>{req.name}</span>}
          <button type="button" onClick={() => onDownload(req.id)} className={`${SMALL_BUTTON} inline-flex items-center gap-1`}
            aria-label={`Download ${req.name} history as CSV`}>
            <Download className="w-3.5 h-3.5" aria-hidden="true" /> Download CSV
          </button>
        </li>
      ))}
    </ul>
  )
}

function ExcuseModal({ period, onSubmit, onClose }) {
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const reasonId = useId()

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      await onSubmit(reason.trim())
    } catch (err) {
      setError(err.message)
      setSaving(false)
    }
  }

  return (
    <Modal open onClose={onClose} title="Excuse from requirement" className="max-w-md">
      <form onSubmit={submit} className="space-y-3">
        <p className="text-sm text-foreground">{period.name}, {periodText(period.start, period.end)}</p>
        <div>
          <label htmlFor={reasonId} className="block text-sm font-medium text-foreground mb-1">Reason (optional)</label>
          <textarea id={reasonId} value={reason} maxLength={500} onChange={e => setReason(e.target.value)}
            className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm h-20 resize-none focus:outline-none focus:ring-2 focus:ring-ring" />
        </div>
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={saving}>Excuse</Button>
        </div>
      </form>
    </Modal>
  )
}

/** Each requirement the card mentions, once, in order of appearance. */
function requirementsIn(data) {
  const seen = new Map()
  for (const row of [...data.current, ...data.pending, ...data.rolling, ...data.lapses, ...data.history]) {
    if (!seen.has(row.requirement_id)) seen.set(row.requirement_id, { id: row.requirement_id, name: row.name })
  }
  return [...seen.values()]
}

function useTargets(allowed) {
  const [targets, setTargets] = useState({})
  useEffect(() => {
    if (!allowed) return undefined
    let alive = true
    api.get('/requirements')
      .then(list => { if (alive) setTargets(Object.fromEntries(list.map(req => [req.id, req]))) })
      .catch(() => {})
    return () => { alive = false }
  }, [allowed])
  return targets
}

const inReview = period => `In review until ${formatDate(period.review_until)}`
const daysLeft = period => daysLeftText(period.days_left)

export default function PilotRequirementsCard({ pilotId, onChange }) {
  const { can, isAdmin } = useAuth()
  const toast = useToast()
  const [confirmProps, requestConfirm] = useConfirm()
  const titleId = useId()
  const [data, setData] = useState(null)
  const [version, setVersion] = useState(0)
  const [excusing, setExcusing] = useState(null)
  const [excusingRolling, setExcusingRolling] = useState(null)
  const allowed = can('requirements.view')
  const targets = useTargets(allowed)
  const flags = useRequirementFlags(allowed, version)

  useEffect(() => {
    if (!allowed) return undefined
    let alive = true
    api.get(`/requirements/pilots/${pilotId}`)
      .then(found => { if (alive) setData({ rolling: [], lapses: [], ...found }) })
      .catch(() => { if (alive) setData(null) })
    return () => { alive = false }
  }, [allowed, pilotId, version])

  if (!allowed || !data) return null
  const requirements = requirementsIn(data)
  if (requirements.length === 0) return null

  // Re-read the card, and let the page re-read what an excusal changes (Needs Attention).
  const reload = () => {
    setVersion(v => v + 1)
    onChange?.()
  }
  const send = (period, excused, reason) => api.post(`/requirements/${period.requirementId}/excuse`, {
    pilot_id: Number(pilotId), period_start: period.start, excused, ...(reason ? { reason } : {}),
  })
  const excuse = async (reason) => {
    await send(excusing, true, reason)
    setExcusing(null)
    toast.success('Pilot excused for this period')
    reload()
  }
  const unexcuse = period => send(period, false)
    .then(() => { toast.success('Excusal removed'); reload() })
    .catch(err => toast.error(err.message))
  const download = id => api.download(`/export/requirements/${id}/csv?pilot_id=${pilotId}`)
    .catch(err => toast.error(err.message))
  const sendRolling = (row, until, reason) => api.post(`/requirements/${row.requirement_id}/excuse`, {
    pilot_id: Number(pilotId), excused_until: until, ...(reason ? { reason } : {}),
  })
  const excuseRolling = async (until, reason) => {
    await sendRolling(excusingRolling, until, reason)
    setExcusingRolling(null)
    toast.success(`Pilot excused until ${formatDate(until)}`)
    reload()
  }
  const removeRolling = row => sendRolling(row, null)
    .then(() => { toast.success('Excusal removed'); reload() })
    .catch(err => toast.error(err.message))
  const canExcuse = can('requirements.excuse')
  const actions = canExcuse ? { onExcuse: setExcusing, onUnexcuse: unexcuse } : null
  const rollingActions = canExcuse ? { onExcuse: setExcusingRolling, onRemove: removeRolling } : null
  const recalculate = period => requestConfirm({
    title: 'Recalculate period',
    message: `Recalculate ${period.name}, ${periodText(period.start, period.end)}, for every pilot from today's flights and target? Excusals are kept.`,
    confirmLabel: 'Recalculate',
    onConfirm: () => api.post(`/requirements/${period.requirementId}/recalculate`, { period_start: period.start })
      .then(() => { toast.success('Period recalculated'); reload() })
      .catch(err => toast.error(err.message)),
  })

  return (
    <section aria-labelledby={titleId} className="bg-card border border-border rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-border flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Target className="w-4 h-4 text-primary" aria-hidden="true" />
          <h3 id={titleId} className="font-semibold text-foreground">Flight Requirements</h3>
        </div>
        <div className="flex flex-wrap justify-end gap-1.5"><RequirementFlagBadges flags={flags[pilotId]} /></div>
      </div>
      <ProgressSection title="This period" rows={data.current} when={daysLeft} targets={targets} actions={actions} />
      <ProgressSection title="In review" rows={data.pending} when={inReview} targets={targets} actions={actions} />
      <RollingSection rows={data.rolling} lapses={data.lapses} targets={targets} actions={rollingActions} />
      <LapseHistory lapses={data.lapses} />
      <HistoryTable rows={data.history} actions={actions} recalculable={isAdmin} onRecalculate={recalculate} />
      {can('reports.export') && <CsvLinks requirements={requirements} onDownload={download} />}
      {excusing && <ExcuseModal period={excusing} onSubmit={excuse} onClose={() => setExcusing(null)} />}
      {excusingRolling && (
        <RollingExcuseModal row={excusingRolling} onSubmit={excuseRolling} onClose={() => setExcusingRolling(null)} />
      )}
      <ConfirmDialog {...confirmProps} />
    </section>
  )
}
