/**
 * Dashboard "This Period" tile: for each active requirement, the days left,
 * how many assigned pilots have met it and each pilot's progress, plus the
 * pilots with an open miss. Renders nothing without requirements.view.
 */
import { useEffect, useId, useState } from 'react'
import { Link } from 'react-router-dom'
import { CalendarClock } from 'lucide-react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { PendingLines, PeriodCounts, PilotProgressList } from './PeriodProgress'
import { useRequirementFlags } from './useRequirementFlags'
import { countText } from './progress'

function scoreText(score) {
  return score == null ? 'No results yet' : `Requirements score ${Math.round(score * 100)}%`
}

function RequirementBlock({ req }) {
  return (
    <li aria-label={req.name} className="px-4 py-3 space-y-1.5">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-sm font-medium text-foreground truncate">{req.name}</p>
        {req.current_period && <PeriodCounts current={req.current_period} />}
      </div>
      <PilotProgressList req={req} />
      <PendingLines periods={req.pending_periods} />
    </li>
  )
}

/** The pilots with an open miss, by the name the flags carry. */
function OpenMisses({ flags }) {
  const ids = Object.keys(flags)
  if (ids.length === 0) return null
  return (
    <p className="px-4 py-2 border-t border-border text-xs text-muted-foreground">
      <span className="font-medium text-danger">Open misses:</span>{' '}
      {ids.map((id, i) => (
        <span key={id}>
          {i > 0 && ', '}
          <Link to={`/pilots/${id}`} title={flags[id].map(f => f.name).join(', ')} className="text-foreground hover:underline">
            {flags[id][0].pilot_name}
          </Link>
        </span>
      ))}
    </p>
  )
}

/** With no active requirement but some switched off, says so, so a requirement
 *  switched off by mistake is not mistaken for none; managers get a link to fix it. */
function SwitchedOff({ count }) {
  const canManage = useAuth().can('requirements.manage')
  const text = `${countText(count, 'flight requirement')} switched off`
  return (
    <p className="p-4 text-center text-xs text-muted-foreground">
      {canManage ? <Link to="/requirements" className="text-primary hover:underline">{text}</Link> : text}
    </p>
  )
}

function emptyText(status) {
  return status.requirements.length === 0 ? 'No active flight requirements' : 'No requirement period is open'
}

function TileBody({ status, failed }) {
  if (failed) return <p className="p-4 text-center text-xs text-muted-foreground">Could not load requirement progress</p>
  if (!status) return <p className="p-4 text-center text-xs text-muted-foreground">Loading…</p>
  if (status.requirements.length === 0 && status.inactive_count > 0) return <SwitchedOff count={status.inactive_count} />
  const shown = status.requirements.filter(r => r.current_period || r.pending_periods.length > 0)
  if (shown.length === 0) return <p className="p-4 text-center text-xs text-muted-foreground">{emptyText(status)}</p>
  return (
    <ul className="divide-y divide-border max-h-[28rem] overflow-y-auto">
      {shown.map(req => <RequirementBlock key={req.requirement_id} req={req} />)}
    </ul>
  )
}

export default function ThisPeriodTile({ className = '' }) {
  const [status, setStatus] = useState(null)
  const [failed, setFailed] = useState(false)
  const allowed = useAuth().can('requirements.view')
  const flags = useRequirementFlags(allowed)
  const titleId = useId()

  useEffect(() => {
    if (!allowed) return undefined
    let alive = true
    api.get('/requirements/status')
      .then(found => { if (alive) setStatus(found) })
      .catch(() => { if (alive) setFailed(true) })
    return () => { alive = false }
  }, [allowed])

  if (!allowed) return null
  return (
    <section aria-labelledby={titleId} className={`bg-card border border-border rounded-xl overflow-hidden ${className}`}>
      <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-border">
        <h3 id={titleId} className="text-sm font-semibold text-foreground flex items-center gap-1.5">
          <CalendarClock className="w-4 h-4 text-primary" aria-hidden="true" /> This Period
        </h3>
        {status && (
          <span className="text-xs text-muted-foreground tabular-nums" title="Share of saved results met in the last 12 months">
            {scoreText(status.score)}
          </span>
        )}
      </div>
      <TileBody status={status} failed={failed} />
      {status && <OpenMisses flags={flags} />}
    </section>
  )
}
