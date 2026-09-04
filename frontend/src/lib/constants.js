/**
 * Unified color constants for status badges, outcomes, and frequencies.
 * Each value is a Tailwind CSS class string for background and text color.
 * Usage: STATUS_COLORS[status] || STATUS_COLORS._default
 */

/**
 * General-purpose status color map for entities like pilots, vehicles, and flights.
 * @type {Record<string, string>}
 */
export const STATUS_COLORS = {
  // General statuses
  active: 'bg-success-bg text-success',
  inactive: 'bg-zinc-500/15 text-zinc-400',
  available: 'bg-success-bg text-success',

  // Completion / review
  completed: 'bg-success-bg text-success',
  complete: 'bg-success-bg text-success',
  reviewed: 'bg-success-bg text-success',
  pending: 'bg-warning-bg text-warning',
  needs_review: 'bg-warning-bg text-warning',
  in_progress: 'bg-info-bg text-info',
  planned: 'bg-info-bg text-info',
  cancelled: 'bg-danger-bg text-danger',

  // Equipment statuses
  maintenance: 'bg-warning-bg text-warning',
  retired: 'bg-danger-bg text-danger',
  damaged: 'bg-danger-bg text-danger',
  charging: 'bg-info-bg text-info',

  // Fallback
  _default: 'bg-zinc-500/15 text-zinc-400',
}

/** @type {Record<string, string>} Color map for certification lifecycle statuses. */
export const CERT_STATUS_COLORS = {
  not_issued: 'bg-zinc-500/15 text-zinc-400',
  not_eligible: 'bg-zinc-500/15 text-zinc-400',
  not_started: 'bg-zinc-500/15 text-zinc-400',
  in_progress: 'bg-info-bg text-info',
  pending: 'bg-warning-bg text-warning',
  complete: 'bg-success-bg text-success',
  active: 'bg-success-bg text-success',
  expired: 'bg-danger-bg text-danger',
  renewed: 'bg-indigo-500/15 text-indigo-400',
}

/** @type {Record<string, string>} Color map for flight/mission outcome statuses. */
export const OUTCOME_COLORS = {
  completed: 'bg-success-bg text-success',
  incomplete: 'bg-warning-bg text-warning',
  failed: 'bg-danger-bg text-danger',
}

/** @type {Record<string, string>} Color map for mission planning statuses. */
export const MISSION_STATUS_COLORS = {
  planned: 'bg-info-bg text-info',
  in_progress: 'bg-warning-bg text-warning',
  completed: 'bg-success-bg text-success',
  cancelled: 'bg-danger-bg text-danger',
}

/** @type {{value: string, label: string}[]} Document classification options for upload/edit forms. */
export const DOC_TYPES = [
  { value: 'general', label: 'General' },
  { value: 'part_107', label: 'Part 107' },
  { value: 'faa_registration', label: 'FAA Registration' },
  { value: 'faa_authorization', label: 'FAA Authorization' },
  { value: 'insurance', label: 'Insurance' },
  { value: 'nist_cert', label: 'NIST Certificate' },
  { value: 'maintenance', label: 'Maintenance Record' },
  { value: 'training', label: 'Training Certificate' },
  { value: 'form', label: 'Form' },
  { value: 'other', label: 'Other' },
]

/** @type {Record<string, string>} Color map for schedule frequencies and one-time tasks. */
export const FREQUENCY_COLORS = {
  monthly: 'bg-blue-500/15 text-blue-400',
  quarterly: 'bg-violet-500/15 text-violet-400',
  yearly: 'bg-amber-500/15 text-amber-400',
  two_years: 'bg-teal-500/15 text-teal-400',
  three_years: 'bg-cyan-500/15 text-cyan-400',
  one_time: 'bg-rose-500/15 text-rose-400',
}

/** @type {Record<string, string>} Display labels for schedule frequencies. */
export const FREQUENCY_LABELS = {
  monthly: 'monthly',
  quarterly: 'quarterly',
  yearly: 'yearly',
  two_years: 'every 2 years',
  three_years: 'every 3 years',
  one_time: 'one-time',
}
