/**
 * Progress of one requirement from /api/requirements/status, shared by the
 * dashboard "This Period" tile and the Flight Requirements tab: the current
 * period's days left and met count, each pilot's progress, and the ended
 * periods still in review; for a rolling requirement, the current and lapsed
 * counts and each pilot's standing with its date.
 */
import { Link } from 'react-router-dom'
import { formatDate } from '@/lib/utils'
import { RequirementStatusChip } from './RequirementBadges'
import { countText, daysLeftText, metCount, progressText, rollingCounts, rollingDateText } from './progress'

/** `date` is the rolling standing's date ("lapses on Dec 3, 2026"), shown after the chip. */
function PilotLine({ pilot, target, date = '' }) {
  return (
    <li className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs">
      <Link to={`/pilots/${pilot.pilot_id}`} className="text-foreground hover:underline truncate max-w-[40%]">{pilot.pilot_name}</Link>
      <span className="flex-1 min-w-0 truncate text-muted-foreground tabular-nums">
        {progressText(pilot.totals, pilot.met_by_model, target)}
      </span>
      <RequirementStatusChip status={pilot.status} />
      {date && <span className="text-muted-foreground whitespace-nowrap tabular-nums">{date}</span>}
    </li>
  )
}

/** "43 days left · 2/5 met" for the current period. */
export function PeriodCounts({ current, className = '' }) {
  return (
    <p className={`text-xs text-muted-foreground whitespace-nowrap tabular-nums ${className}`}>
      <span>{daysLeftText(current.days_left)}</span>
      {' · '}
      <span>{metCount(current.pilots)}/{current.pilots.length} met</span>
    </p>
  )
}

/** Each assigned pilot's progress in the current period; `req` carries the target. */
export function PilotProgressList({ req }) {
  const pilots = req.current_period?.pilots || []
  if (pilots.length === 0) return null
  return (
    <ul className="space-y-1">
      {pilots.map(p => <PilotLine key={p.pilot_id} pilot={p} target={req} />)}
    </ul>
  )
}

/** "Previous period: 2 pilots pending review until Dec 14, 2026", for each ended period still in grace time. */
export function PendingLines({ periods }) {
  const lines = periods
    .map(p => ({ start: p.start, until: p.review_until, count: p.pilots.filter(x => x.status === 'pending_review').length }))
    .filter(p => p.count > 0)
  return lines.map(p => (
    <p key={p.start} className="text-xs text-warning">
      Previous period: {countText(p.count, 'pilot')} pending review until {formatDate(p.until)}
    </p>
  ))
}

/** "3 current, 1 lapsed" for a rolling requirement's window. */
export function RollingCounts({ rolling, className = '' }) {
  return (
    <p className={`text-xs text-muted-foreground whitespace-nowrap tabular-nums ${className}`}>
      {rollingCounts(rolling.pilots)}
    </p>
  )
}

/** Each assigned pilot's standing on a rolling requirement; `lapsedSince` maps a
 *  pilot id to the start of their open lapse. */
export function RollingPilotList({ req, lapsedSince = {} }) {
  const pilots = req.rolling?.pilots || []
  if (pilots.length === 0) return null
  return (
    <ul className="space-y-1">
      {pilots.map(p => (
        <PilotLine key={p.pilot_id} pilot={p} target={req} date={rollingDateText(p, lapsedSince[p.pilot_id])} />
      ))}
    </ul>
  )
}
