/**
 * "Past missed periods" on the Flight Requirements tab: saved periods of
 * periodic requirements that a pilot missed or had excused, across the unit,
 * newest first. Everyone with requirements.view sees the list; Excuse and
 * Un-excuse need requirements.excuse. Rolling requirements keep their lapses
 * on the pilot page.
 */
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { RequirementStatusChip } from './RequirementBadges'
import { ExcuseButton, ExcuseModal } from './PilotRequirementsCard'
import { excusalText, periodText, progressText } from './progress'

const HEAD = 'text-left px-4 py-2 text-foreground font-medium'

function MissedRow({ row, actions }) {
  return (
    <tr className="border-b border-border/50 align-top">
      <td className="px-4 py-2 text-foreground">{row.name}</td>
      <td className="px-4 py-2 text-foreground">
        <Link to={`/pilots/${row.pilot_id}`} className="text-primary hover:underline">{row.pilot_name}</Link>
      </td>
      <td className="px-4 py-2 text-foreground whitespace-nowrap">{periodText(row.period_start, row.period_end)}</td>
      <td className="px-4 py-2 text-foreground tabular-nums">{progressText(row.totals, null, row.target_snapshot || {})}</td>
      <td className="px-4 py-2">
        <RequirementStatusChip status={row.status} />
        {row.excused && <p className="text-xs text-muted-foreground mt-1">{excusalText(row)}</p>}
      </td>
      {actions && <td className="px-4 py-2 text-right"><ExcuseButton row={row} {...actions} /></td>}
    </tr>
  )
}

function MissedTable({ rows, actionsFor }) {
  return (
    <div className="overflow-x-auto">
      <table aria-label="Past missed periods" className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/30">
            <th className={HEAD}>Requirement</th>
            <th className={HEAD}>Pilot</th>
            <th className={HEAD}>Period</th>
            <th className={HEAD}>Result</th>
            <th className={HEAD}>Status</th>
            {actionsFor && <th className="px-4 py-2"><span className="sr-only">Actions</span></th>}
          </tr>
        </thead>
        <tbody>
          {rows.map(row => <MissedRow key={row.result_id} row={row} actions={actionsFor?.(row)} />)}
        </tbody>
      </table>
    </div>
  )
}

export default function MissedPeriods({ requirements }) {
  const { can } = useAuth()
  const toast = useToast()
  const [rows, setRows] = useState(null)
  const [requirementId, setRequirementId] = useState('')
  const [excusing, setExcusing] = useState(null)
  const canExcuse = can('requirements.excuse')

  const query = requirementId ? `?requirement_id=${requirementId}` : ''
  const load = useCallback(() => api.get(`/requirements/history${query}`)
    .then(setRows)
    .catch(err => toast.error(err.message)), [query, toast])
  useEffect(() => { load() }, [load])

  const send = (period, pilotId, excused, reason) => api.post(`/requirements/${period.requirementId}/excuse`, {
    pilot_id: pilotId, period_start: period.start, excused, ...(reason ? { reason } : {}),
  })
  const excuse = async (reason) => {
    await send(excusing.period, excusing.pilotId, true, reason)
    setExcusing(null)
    toast.success('Pilot excused for this period')
    load()
  }
  const unexcuse = (period, pilotId) => send(period, pilotId, false)
    .then(() => { toast.success('Excusal removed'); load() })
    .catch(err => toast.error(err.message))

  // ExcuseButton hands back the period only, so each row binds its pilot.
  const actionsFor = row => ({
    onExcuse: period => setExcusing({ period, pilotId: row.pilot_id }),
    onUnexcuse: period => unexcuse(period, row.pilot_id),
  })

  return (
    <section aria-labelledby="missed-title" className="bg-card border border-border rounded-xl p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h2 id="missed-title" className="text-lg font-semibold text-foreground">Past missed periods</h2>
        <select aria-label="Requirement filter" value={requirementId} onChange={e => setRequirementId(e.target.value)}
          className="px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm">
          <option value="">All requirements</option>
          {requirements.filter(req => req.period_type !== 'rolling').map(req => <option key={req.id} value={req.id}>{req.name}</option>)}
        </select>
      </div>
      {rows?.length === 0 && (
        <p className="text-sm text-muted-foreground px-3 py-4 bg-muted/30 rounded-lg text-center">No missed periods.</p>
      )}
      {rows?.length > 0 && <MissedTable rows={rows} actionsFor={canExcuse ? actionsFor : null} />}
      {excusing && <ExcuseModal period={excusing.period} onSubmit={excuse} onClose={() => setExcusing(null)} />}
    </section>
  )
}
