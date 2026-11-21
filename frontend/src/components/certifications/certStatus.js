import { Ban, CircleCheck, CircleDashed, CircleDot, CircleMinus, CircleX, Clock, RefreshCw, TriangleAlert } from 'lucide-react'
import { CERT_STATUS_COLORS } from '@/lib/constants'
import { certDisplayStatus, daysUntil, formatDate } from '@/lib/utils'

// Cells show the derived state: an expiry inside the window reads
// "expiring soon" in amber, a passed one "expired" in red.
export const CELL_COLORS = { ...CERT_STATUS_COLORS, expiring: 'bg-warning-bg text-warning' }
const CELL_LABELS = { expiring: 'expiring soon' }

export const STATUS_ICONS = {
  not_issued: CircleMinus,
  not_eligible: Ban,
  not_started: CircleDashed,
  in_progress: CircleDot,
  pending: Clock,
  complete: CircleCheck,
  active: CircleCheck,
  expired: CircleX,
  renewed: RefreshCw,
  expiring: TriangleAlert,
}

export const CERT_CATEGORIES = [
  ['faa', 'FAA'], ['nist', 'NIST'], ['equipment', 'Equipment'],
  ['insurance', 'Insurance'], ['training', 'Training'], ['custom', 'Custom'],
]

export const DEFAULT_FILTERS = { status: 'all', category: 'all', search: '', hideEmpty: false }

/** A status as people read it: the unit's custom label, else the built-in one. */
export function statusText(status, labels = {}) {
  return labels[status] || CELL_LABELS[status] || status.replaceAll('_', ' ')
}

export function statusColor(status) {
  return CELL_COLORS[status] || CELL_COLORS.not_started
}

export function statusIcon(status) {
  return STATUS_ICONS[status] || CircleDashed
}

function dateText(cert) {
  if (!cert?.expiration_date) return 'no expiration date'
  const verb = daysUntil(cert.expiration_date) < 0 ? 'expired' : 'expires'
  return `${verb} ${formatDate(cert.expiration_date)}`
}

function capitalize(text) {
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/**
 * Everything a view needs to show one pilot and type pair. The matrix API
 * fills an empty pair with a placeholder whose id is null.
 */
export function certCell(row, ct, labels) {
  const cert = row.certs?.[ct.id]
  const status = certDisplayStatus(cert)
  const text = statusText(status, labels)
  const date = dateText(cert)
  const stored = cert && status !== cert.status ? `status: ${statusText(cert.status, labels)}` : ''
  return {
    cert,
    status,
    text,
    shortDate: cert?.expiration_date ? formatDate(cert.expiration_date) : '',
    label: `${row.pilot_name}, ${ct.name}: ${text}, ${date}`,
    title: [capitalize(date), stored].filter(Boolean).join('; '),
  }
}

/** Whether clicking a cell opens a modal: assign or edit, or a record's documents. */
export function canOpenCert(cert, { canManage, canSeeFiles }) {
  return canManage || (Boolean(cert?.id) && canSeeFiles)
}

export function filterCertTypes(certTypes, category) {
  const active = certTypes.filter(c => c.is_active)
  if (category === 'all') return active
  return active.filter(c => c.category === category)
}

function rowPasses(row, query, filters) {
  const certs = Object.values(row.certs || {})
  if (query && !row.pilot_name?.toLowerCase().includes(query)) return false
  // Status: pilots with at least one cert in that state.
  if (filters.status !== 'all' && !certs.some(c => certDisplayStatus(c) === filters.status)) return false
  // Hide empty: placeholders have a null id, so look for a real record.
  return !filters.hideEmpty || certs.some(c => c?.id != null)
}

export function filterMatrix(rows, filters) {
  const query = filters.search.toLowerCase().trim()
  return rows.filter(row => rowPasses(row, query, filters))
}

/** The reorder payload for moving an active cert type one place, or null at an edge. */
export function reorderedTypes(certTypes, ctId, direction) {
  const active = certTypes.filter(c => c.is_active)
  const idx = active.findIndex(c => c.id === ctId)
  const target = direction === 'left' ? idx - 1 : idx + 1
  if (idx < 0 || target < 0 || target >= active.length) return null
  const reordered = [...active]
  reordered[idx] = active[target]
  reordered[target] = active[idx]
  return reordered.map((ct, i) => ({ id: ct.id, sort_order: i }))
}

export const URGENCY_GROUPS = [
  { key: 'expired', title: 'Expired', status: 'expired', tone: 'text-danger' },
  { key: 'within30', title: 'Expiring within 30 days', status: 'expiring', tone: 'text-warning' },
  { key: 'within60', title: 'Expiring within 60 days', status: 'expiring', tone: 'text-warning' },
  { key: 'within90', title: 'Expiring within 90 days', status: 'expiring', tone: 'text-warning' },
  { key: 'current', title: 'Current', status: 'complete', tone: 'text-success' },
]

const CURRENT_STATUSES = new Set(['complete', 'active'])
const URGENCY_STATUSES = new Set(['expired', 'expiring', ...CURRENT_STATUSES])

/** Whether a status filter can match anything in By urgency. */
export function urgencyShowsStatus(status) {
  return status === 'all' || URGENCY_STATUSES.has(status)
}

function urgencyGroup(cell) {
  if (cell.status === 'expired') return 'expired'
  if (cell.status !== 'expiring') return CURRENT_STATUSES.has(cell.status) ? 'current' : null
  const days = daysUntil(cell.cert.expiration_date)
  if (days <= 30) return 'within30'
  if (days <= 60) return 'within60'
  return 'within90'
}

function urgencyItem(row, ct, status, labels) {
  const cell = certCell(row, ct, labels)
  if (cell.cert?.id == null) return null
  if (status !== 'all' && cell.status !== status) return null
  const group = urgencyGroup(cell)
  return group && { ...cell, row, ct, group }
}

function byDateThenPilot(a, b) {
  const dateA = a.cert.expiration_date || '9999-12-31'
  const dateB = b.cert.expiration_date || '9999-12-31'
  return dateA.localeCompare(dateB) || a.row.pilot_name.localeCompare(b.row.pilot_name)
}

/** Real records sorted into the urgency groups, soonest first within each. */
export function groupByUrgency(rows, certTypes, status, labels) {
  const groups = Object.fromEntries(URGENCY_GROUPS.map(g => [g.key, []]))
  rows
    .flatMap(row => certTypes.map(ct => urgencyItem(row, ct, status, labels)))
    .filter(Boolean)
    .forEach(item => groups[item.group].push(item))
  return Object.fromEntries(Object.entries(groups).map(([key, list]) => [key, list.toSorted(byDateThenPilot)]))
}
