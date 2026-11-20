import { periodText, STATUS_LABELS } from './progress'

const CHIP = 'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap'

const STATUS_TONES = {
  met: 'bg-success-bg text-success',
  on_track: 'bg-primary/10 text-primary',
  pending_review: 'bg-warning-bg text-warning',
  missed: 'bg-danger-bg text-danger',
  excused: 'bg-secondary text-muted-foreground border border-border',
}

/** A pilot's status in one requirement period. */
export function RequirementStatusChip({ status }) {
  return <span className={`${CHIP} ${STATUS_TONES[status] || STATUS_TONES.excused}`}>{STATUS_LABELS[status] || status}</span>
}

/** "Missed requirement" while a pilot has an open miss; the title names each one. */
export function MissedBadge({ flags, className = '' }) {
  if (!flags?.length) return null
  const title = flags.map(f => `${f.name}, ${periodText(f.period_start, f.period_end)}`).join('; ')
  return <span title={title} className={`${CHIP} bg-danger-bg text-danger ${className}`}>Missed requirement</span>
}
