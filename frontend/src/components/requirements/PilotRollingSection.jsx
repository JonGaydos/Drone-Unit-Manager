/**
 * The rolling part of the pilot detail "Flight Requirements" card: the
 * pilot's standing on each active rolling requirement, Excuse until a date
 * and Remove excusal (requirements.excuse), and the pilot's lapse history.
 */
import { useId, useState } from 'react'
import { formatDate, todayLocal } from '@/lib/utils'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { RequirementStatusChip } from './RequirementBadges'
import { countText, periodText, progressText, rollingDateText } from './progress'

const SMALL_BUTTON = 'px-2 py-1 text-xs rounded-md border border-border text-foreground hover:bg-accent whitespace-nowrap'
const INPUT = 'w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring'

function RollingNotes({ row }) {
  const notes = []
  if (row.excluded_no_takeoff > 0) notes.push(`${countText(row.excluded_no_takeoff, 'flight')} left out: no takeoff time`)
  if (row.unreviewed_in_window > 0) notes.push(`${countText(row.unreviewed_in_window, 'flight')} awaiting review`)
  return notes.map(note => <p key={note} className="text-xs text-muted-foreground">{note}</p>)
}

function RollingExcuseButton({ row, actions }) {
  if (row.status === 'excused') {
    return (
      <button type="button" onClick={() => actions.onRemove(row)} className={SMALL_BUTTON}
        aria-label={`Remove excusal from ${row.name}`}>
        Remove excusal
      </button>
    )
  }
  return (
    <button type="button" onClick={() => actions.onExcuse(row)} className={SMALL_BUTTON} aria-label={`Excuse ${row.name}`}>
      Excuse
    </button>
  )
}

function RollingRow({ row, since, target, actions }) {
  const date = rollingDateText(row, since)
  return (
    <li className="px-4 py-3 flex flex-wrap items-start gap-x-4 gap-y-2">
      <div className="flex-1 min-w-[12rem] space-y-0.5">
        <p className="text-sm font-medium text-foreground">{row.name}</p>
        <p className="text-xs text-muted-foreground">Window {periodText(row.window_start, row.window_end)}</p>
        <p className="text-sm text-foreground tabular-nums">{progressText(row.totals, row.met_by_model, target)}</p>
        <RollingNotes row={row} />
      </div>
      <div className="flex flex-col items-end gap-0.5">
        <RequirementStatusChip status={row.status} />
        {date && <span className="text-xs text-muted-foreground tabular-nums">{date}</span>}
      </div>
      {actions && <RollingExcuseButton row={row} actions={actions} />}
    </li>
  )
}

/** The start of each open lapse, by requirement id. */
function openLapses(lapses) {
  return Object.fromEntries(lapses.filter(l => !l.recovered_on).map(l => [l.requirement_id, l.lapsed_on]))
}

/** The pilot's standing on each rolling requirement; `actions` holds onExcuse and onRemove, or is null. */
export function RollingSection({ rows, lapses, targets, actions }) {
  const id = useId()
  if (rows.length === 0) return null
  const since = openLapses(lapses)
  return (
    <section aria-labelledby={id} className="border-b border-border">
      <h4 id={id} className="px-4 pt-3 text-xs font-medium text-muted-foreground">Rolling</h4>
      <ul className="divide-y divide-border/50">
        {rows.map(row => (
          <RollingRow key={row.requirement_id} row={row} since={since[row.requirement_id]}
            target={targets[row.requirement_id] || {}} actions={actions} />
        ))}
      </ul>
    </section>
  )
}

function LapseDeleteButton({ lapse, onDelete }) {
  if (!lapse.recovered_on) return null
  return (
    <button type="button" onClick={() => onDelete(lapse)} className={SMALL_BUTTON}
      aria-label={`Delete lapse ${lapse.name}, ${formatDate(lapse.lapsed_on)}`}>
      Delete
    </button>
  )
}

/** Every lapse the pilot has had, newest first, with the day it ended.
 *  `onDelete` (admins) adds Delete to closed lapses. */
export function LapseHistory({ lapses, onDelete = null }) {
  if (lapses.length === 0) return null
  return (
    <div className="overflow-x-auto border-b border-border">
      <table aria-label="Lapse history" className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/30">
            <th className="text-left px-4 py-2 text-foreground font-medium">Requirement</th>
            <th className="text-left px-4 py-2 text-foreground font-medium">Lapsed on</th>
            <th className="text-left px-4 py-2 text-foreground font-medium">Current again on</th>
            {onDelete && <th className="px-4 py-2"><span className="sr-only">Actions</span></th>}
          </tr>
        </thead>
        <tbody>
          {lapses.map(lapse => (
            <tr key={lapse.lapse_id} className="border-b border-border/50 last:border-b-0">
              <td className="px-4 py-2 text-foreground">{lapse.name}</td>
              <td className="px-4 py-2 text-foreground whitespace-nowrap tabular-nums">{formatDate(lapse.lapsed_on)}</td>
              <td className="px-4 py-2 whitespace-nowrap tabular-nums">
                {lapse.recovered_on
                  ? <span className="text-foreground">{formatDate(lapse.recovered_on)}</span>
                  : <span className="text-danger">Still lapsed</span>}
              </td>
              {onDelete && <td className="px-4 py-2 text-right"><LapseDeleteButton lapse={lapse} onDelete={onDelete} /></td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Excuse the pilot from a rolling requirement through a chosen day. `onSubmit(until, reason)` rejects with the error to show. */
export function RollingExcuseModal({ row, onSubmit, onClose }) {
  const [until, setUntil] = useState('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const untilId = useId()
  const reasonId = useId()

  const submit = async (e) => {
    e.preventDefault()
    if (!until) {
      setError('Choose the date the excusal lasts until')
      return
    }
    setSaving(true)
    setError('')
    try {
      await onSubmit(until, reason.trim())
    } catch (err) {
      setError(err.message)
      setSaving(false)
    }
  }

  return (
    <Modal open onClose={onClose} title="Excuse from requirement" className="max-w-md">
      <form onSubmit={submit} noValidate className="space-y-3">
        <p className="text-sm text-foreground">{row.name}</p>
        <div>
          <label htmlFor={untilId} className="block text-sm font-medium text-foreground mb-1">Excused until</label>
          <input id={untilId} type="date" value={until} min={todayLocal()} required aria-describedby={`${untilId}-hint`}
            onChange={e => setUntil(e.target.value)} className={INPUT} />
          <p id={`${untilId}-hint`} className="text-xs text-muted-foreground mt-1">
            While excused the pilot is neither current nor lapsed. The excusal ends after this day.
          </p>
        </div>
        <div>
          <label htmlFor={reasonId} className="block text-sm font-medium text-foreground mb-1">Reason (optional)</label>
          <textarea id={reasonId} value={reason} maxLength={500} onChange={e => setReason(e.target.value)}
            className={`${INPUT} h-20 resize-none`} />
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
