// Unified status color maps - imported across all pages
// Use with: STATUS_COLORS[status] || STATUS_COLORS._default

export const STATUS_COLORS = {
  // General statuses
  active: 'bg-emerald-500/15 text-emerald-400',
  inactive: 'bg-zinc-500/15 text-zinc-400',
  available: 'bg-emerald-500/15 text-emerald-400',

  // Completion / review
  completed: 'bg-emerald-500/15 text-emerald-400',
  complete: 'bg-emerald-500/15 text-emerald-400',
  reviewed: 'bg-emerald-500/15 text-emerald-400',
  pending: 'bg-amber-500/15 text-amber-400',
  needs_review: 'bg-amber-500/15 text-amber-400',
  in_progress: 'bg-blue-500/15 text-blue-400',
  planned: 'bg-blue-500/15 text-blue-400',
  cancelled: 'bg-red-500/15 text-red-400',

  // Equipment statuses
  maintenance: 'bg-amber-500/15 text-amber-400',
  retired: 'bg-red-500/15 text-red-400',
  damaged: 'bg-red-500/15 text-red-400',
  charging: 'bg-blue-500/15 text-blue-400',

  // Fallback
  _default: 'bg-zinc-500/15 text-zinc-400',
}

export const CERT_STATUS_COLORS = {
  not_issued: 'bg-zinc-500/15 text-zinc-400',
  not_eligible: 'bg-zinc-500/15 text-zinc-400',
  not_started: 'bg-zinc-500/15 text-zinc-400',
  in_progress: 'bg-blue-500/15 text-blue-400',
  pending: 'bg-amber-500/15 text-amber-400',
  complete: 'bg-emerald-500/15 text-emerald-400',
  active: 'bg-emerald-500/15 text-emerald-400',
  expired: 'bg-red-500/15 text-red-400',
}

export const OUTCOME_COLORS = {
  completed: 'bg-emerald-500/15 text-emerald-400',
  incomplete: 'bg-amber-500/15 text-amber-400',
  failed: 'bg-red-500/15 text-red-400',
}

export const MISSION_STATUS_COLORS = {
  planned: 'bg-blue-500/15 text-blue-400',
  in_progress: 'bg-amber-500/15 text-amber-400',
  completed: 'bg-emerald-500/15 text-emerald-400',
  cancelled: 'bg-red-500/15 text-red-400',
}

export const FREQUENCY_COLORS = {
  monthly: 'bg-blue-500/15 text-blue-400',
  quarterly: 'bg-violet-500/15 text-violet-400',
  yearly: 'bg-amber-500/15 text-amber-400',
}
