import { formatDate } from '@/lib/utils'
import { periodText, STATUS_LABELS } from './progress'

const CHIP = 'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap'

const STATUS_TONES = {
  met: 'bg-success-bg text-success',
  on_track: 'bg-primary/10 text-primary',
  pending_review: 'bg-warning-bg text-warning',
  missed: 'bg-danger-bg text-danger',
  excused: 'bg-secondary text-muted-foreground border border-border',
  current: 'bg-success-bg text-success',
  lapsed: 'bg-danger-bg text-danger',
  not_yet_due: 'bg-secondary text-muted-foreground border border-border',
}

/** A pilot's status in one requirement period, or on a rolling requirement. */
export function RequirementStatusChip({ status }) {
  return <span className={`${CHIP} ${STATUS_TONES[status] || STATUS_TONES.excused}`}>{STATUS_LABELS[status] || status}</span>
}

function flagTitle(flag) {
  if (flag.kind === 'lapsed') return `${flag.name}, lapsed since ${formatDate(flag.period_start)}`
  return `${flag.name}, ${periodText(flag.period_start, flag.period_end)}`
}

/** "Missed requirement" while a pilot has an open miss and "Lapsed requirement"
 *  while one is lapsed; each title names the requirements. */
export function RequirementFlagBadges({ flags, className = '' }) {
  if (!flags?.length) return null
  const lapses = flags.filter(f => f.kind === 'lapsed')
  const misses = flags.filter(f => f.kind !== 'lapsed')
  return (
    <>
      {misses.length > 0 && (
        <span title={misses.map(flagTitle).join('; ')} className={`${CHIP} bg-danger-bg text-danger ${className}`}>Missed requirement</span>
      )}
      {lapses.length > 0 && (
        <span title={lapses.map(flagTitle).join('; ')} className={`${CHIP} bg-danger-bg text-danger ${className}`}>Lapsed requirement</span>
      )}
    </>
  )
}
