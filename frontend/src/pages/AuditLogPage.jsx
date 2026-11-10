import { Fragment, useState, useEffect } from 'react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { ChevronLeft, ChevronRight, ChevronDown, ChevronUp, Filter, ScrollText, Download } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

// Every entity type and action the backend records, so any entry can be filtered.
const ENTITY_TYPES = [
  '', 'alert', 'api_token', 'attachment', 'auth', 'backup', 'battery', 'battery_reading',
  'calendar_event', 'certification_type', 'checklist_completion', 'checklist_template',
  'component', 'controller', 'currency', 'currency_rule', 'dock', 'document', 'equipment',
  'flight', 'flight_plan', 'flight_purpose', 'folder', 'incident', 'maintenance',
  'maintenance_schedule', 'media_file', 'mission_log', 'mission_log_pilot', 'notification',
  'notification_log', 'notification_preference', 'operating_authority', 'other_equipment', 'photo',
  'photo_flight', 'photo_incident', 'photo_pilot', 'pilot', 'pilot_certification',
  'pilot_equipment_qual', 'role_permission', 'role_permissions', 'saved_report', 'sensor',
  'setting', 'system', 'training_log', 'training_log_pilot', 'user', 'vehicle',
  'vehicle_registration',
]

const ACTIONS = [
  '', 'alert_check', 'approve', 'backup', 'battery_repair', 'bulk_approve', 'bulk_delete',
  'bulk_update', 'cancel', 'checkin', 'checkout', 'cleanup', 'complete', 'create', 'deactivate',
  'delete', 'deny', 'digest', 'disconnect', 'dismiss', 'dismiss_all', 'enrich_flights',
  'enrich_run', 'export', 'hold', 'import', 'link', 'login', 'login_blocked', 'login_failed',
  'logout', 'merge', 'password_change', 'password_reset', 'purge', 'reactivate', 'read',
  'release_hold', 'reset', 'restore', 'restore_held_item', 'retire', 'send_reminders', 'send_test',
  'setup', 'sync', 'sync_deep', 'sync_run', 'telemetry_sync', 'unapprove', 'unlink', 'update',
  'upload', 'view',
]

// Roughly what the 200px details column fits at this font size. Only used to
// decide whether a row is worth expanding, never to cut text.
const DETAILS_VISIBLE_CHARS = 30

const ACTION_COLORS = {
  create: 'bg-emerald-500/15 text-emerald-400',
  update: 'bg-blue-500/15 text-blue-400',
  delete: 'bg-red-500/15 text-red-400',
  deactivate: 'bg-amber-500/15 text-amber-400',
  retire: 'bg-amber-500/15 text-amber-400',
  login: 'bg-violet-500/15 text-violet-400',
  login_failed: 'bg-red-500/15 text-red-400',
  password_change: 'bg-violet-500/15 text-violet-400',
  sync: 'bg-cyan-500/15 text-cyan-400',
  bulk_approve: 'bg-emerald-500/15 text-emerald-400',
  bulk_update: 'bg-blue-500/15 text-blue-400',
}

// Changes arrive as {old, new} pairs, plain values, or bulk and machine
// summaries with counts and ids. Show every one as text without erroring.
function isChangeMap(changes) {
  return changes !== null && typeof changes === 'object' && !Array.isArray(changes)
}

function changeText(value) {
  if (value === null || value === undefined || value === '') return '(empty)'
  return typeof value === 'object' ? JSON.stringify(value) : String(value)
}

function isPair(change) {
  return isChangeMap(change) && ('old' in change || 'new' in change)
}

function ChangeLine({ field, change }) {
  return (
    <div className="flex items-start gap-2">
      <span className="font-medium text-foreground min-w-[120px]">{field}:</span>
      {isPair(change) ? (
        <>
          <span className="text-red-400 line-through">{changeText(change.old)}</span>
          <span className="text-muted-foreground">-&gt;</span>
          <span className="text-emerald-400">{changeText(change.new)}</span>
        </>
      ) : (
        <span className="text-emerald-400 break-all">{changeText(change)}</span>
      )}
    </div>
  )
}

function expandTitle(hasChanges, detailsClipped) {
  if (hasChanges) return 'View changes'
  return detailsClipped ? 'View full details' : 'View details'
}

function entityLink(entityType, entityId) {
  if (!entityId) return null
  switch (entityType) {
    case 'flight': return `/flights/${entityId}`
    case 'pilot': return `/pilots/${entityId}`
    case 'vehicle': return `/fleet/vehicles/${entityId}`
    default: return null
  }
}

function formatTimestamp(iso) {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

export default function AuditLogPage() {
  const { can } = useAuth()
  const canView = can('audit.view')
  const navigate = useNavigate()
  const [logs, setLogs] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [perPage] = useState(50)
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState(null)

  // Filters
  const [entityType, setEntityType] = useState('')
  const [action, setAction] = useState('')
  const [userId, setUserId] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [showFilters, setShowFilters] = useState(false)
  const [logUsers, setLogUsers] = useState([])
  const hasFilters = Boolean(entityType || action || userId || dateFrom || dateTo)

  // The filters as query parameters, shared by the list and the CSV export.
  const filterParams = () => {
    const params = new URLSearchParams()
    if (entityType) params.set('entity_type', entityType)
    if (action) params.set('action', action)
    if (userId) params.set('user_id', userId)
    if (dateFrom) params.set('date_from', dateFrom)
    if (dateTo) params.set('date_to', dateTo)
    return params
  }

  useEffect(() => {
    if (!canView) return
    setLoading(true)
    const params = filterParams()
    params.set('page', page)
    params.set('per_page', perPage)

    api.get(`/audit?${params.toString()}`)
      .then(data => {
        setLogs(data.logs)
        setTotal(data.total)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [canView, page, perPage, entityType, action, userId, dateFrom, dateTo]) // eslint-disable-line react-hooks/exhaustive-deps

  // The user filter's choices: everyone who has an entry in the log.
  useEffect(() => {
    if (!canView || !showFilters) return
    api.get('/audit/users').then(rows => { if (Array.isArray(rows)) setLogUsers(rows) }).catch(() => {})
  }, [canView, showFilters])

  const clearFilters = () => {
    setEntityType(''); setAction(''); setUserId(''); setDateFrom(''); setDateTo(''); setPage(1)
  }

  const exportCsv = () => {
    const query = filterParams().toString()
    api.download(`/export/audit/csv${query ? `?${query}` : ''}`)
  }

  if (!canView) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-muted-foreground">You do not have access to the audit log.</p>
      </div>
    )
  }

  const totalPages = Math.ceil(total / perPage) || 1

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <ScrollText className="w-6 h-6 text-primary" />
          <div>
            <h2 className="text-xl font-semibold text-foreground">Activity Audit Log</h2>
            <p className="text-sm text-muted-foreground">{total} total entries</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {can('reports.export') && (
            <button
              onClick={exportCsv}
              className="flex items-center gap-2 px-3 py-2 bg-secondary border border-border rounded-lg text-sm text-foreground hover:bg-accent/30 transition-colors"
            >
              <Download className="w-4 h-4" /> Export CSV
            </button>
          )}
          <button
            onClick={() => setShowFilters(!showFilters)}
            className="flex items-center gap-2 px-3 py-2 bg-secondary border border-border rounded-lg text-sm text-foreground hover:bg-accent/30 transition-colors"
          >
            <Filter className="w-4 h-4" />
            Filters
          {hasFilters && (
            <span className="w-2 h-2 rounded-full bg-primary" />
          )}
        </button>
        </div>
      </div>

      {/* Filters */}
      {showFilters && (
        <div className="bg-card border border-border rounded-xl p-4 flex flex-wrap gap-4">
          <div>
            <label htmlFor="entity-type" className="block text-xs font-medium text-muted-foreground mb-1">Entity Type</label>
            <select id="entity-type"
              value={entityType}
              onChange={e => { setEntityType(e.target.value); setPage(1) }}
              className="px-3 py-1.5 bg-secondary border border-border rounded-lg text-sm text-foreground"
            >
              <option value="">All</option>
              {ENTITY_TYPES.filter(Boolean).map(t => (
                <option key={t} value={t}>{t.replaceAll('_', ' ')}</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="action" className="block text-xs font-medium text-muted-foreground mb-1">Action</label>
            <select id="action"
              value={action}
              onChange={e => { setAction(e.target.value); setPage(1) }}
              className="px-3 py-1.5 bg-secondary border border-border rounded-lg text-sm text-foreground"
            >
              <option value="">All</option>
              {ACTIONS.filter(Boolean).map(a => (
                <option key={a} value={a}>{a.replaceAll('_', ' ')}</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="audit-user" className="block text-xs font-medium text-muted-foreground mb-1">User</label>
            <select id="audit-user"
              value={userId}
              onChange={e => { setUserId(e.target.value); setPage(1) }}
              className="max-w-64 truncate px-3 py-1.5 bg-secondary border border-border rounded-lg text-sm text-foreground"
            >
              <option value="">All</option>
              {logUsers.map(u => (
                <option key={u.user_id} value={u.user_id}>
                  {u.user_name || u.user_username}{u.user_username && u.user_name ? ` (${u.user_username})` : ''}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="audit-date-from" className="block text-xs font-medium text-muted-foreground mb-1">From</label>
            <input id="audit-date-from" type="date"
              value={dateFrom}
              max={dateTo || undefined}
              onChange={e => { setDateFrom(e.target.value); setPage(1) }}
              className="px-3 py-1.5 bg-secondary border border-border rounded-lg text-sm text-foreground"
            />
          </div>
          <div>
            <label htmlFor="audit-date-to" className="block text-xs font-medium text-muted-foreground mb-1">To</label>
            <input id="audit-date-to" type="date"
              value={dateTo}
              min={dateFrom || undefined}
              onChange={e => { setDateTo(e.target.value); setPage(1) }}
              className="px-3 py-1.5 bg-secondary border border-border rounded-lg text-sm text-foreground"
            />
          </div>
          {hasFilters && (
            <div className="flex items-end">
              <button
                onClick={clearFilters}
                className="px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground"
              >
                Clear filters
              </button>
            </div>
          )}
        </div>
      )}

      {/* Table */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        {loading && (
          <div className="flex items-center justify-center h-32">
            <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          </div>
        )}
        {!loading && logs.length === 0 && (
          <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
            No audit log entries found.
          </div>
        )}
        {!loading && logs.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/30">
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Timestamp</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">User</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Action</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Entity Type</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Entity</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Details</th>
                  <th className="w-10"></th>
                </tr>
              </thead>
              <tbody>
                {logs.map(log => {
                  const link = entityLink(log.entity_type, log.entity_id)
                  const hasChanges = isChangeMap(log.changes) && Object.keys(log.changes).length > 0
                  const isExpanded = expandedId === log.id

                  const entries = hasChanges ? Object.entries(log.changes) : []
                  // The details column is fixed width and truncates. Nothing in
                  // the DOM can say whether it actually clipped without
                  // measuring, so this is roughly what the column fits, rounded
                  // down: a row that expands to the text it already showed is
                  // harmless, a truncated row with no way to read it is not.
                  const detailsClipped = (log.details || '').length > DETAILS_VISIBLE_CHARS
                  const expandable = hasChanges || detailsClipped || Boolean(log.ip_address)

                  return (
                    <Fragment key={log.id}>
                    <tr className="border-b border-border/50 hover:bg-muted/20">
                      <td className="px-4 py-2.5 text-muted-foreground whitespace-nowrap text-xs">
                        {formatTimestamp(log.created_at)}
                      </td>
                      <td className="px-4 py-2.5 text-foreground">
                        {log.user_name || '-'}
                        {log.user_username && (
                          <span className="ml-1 text-xs text-muted-foreground">({log.user_username})</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5">
                        <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${ACTION_COLORS[log.action] || 'bg-muted text-muted-foreground'}`}>
                          {log.action?.replaceAll('_', ' ')}
                        </span>
                        {log.imported && (
                          <span className="ml-1 inline-block px-2 py-0.5 rounded-full text-xs bg-muted text-muted-foreground">
                            Imported
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-muted-foreground capitalize">
                        {log.entity_type?.replaceAll('_', ' ') || '-'}
                      </td>
                      <td className="px-4 py-2.5">
                        {link ? (
                          <button
                            onClick={() => navigate(link)}
                            className="text-primary hover:underline text-left"
                          >
                            {log.entity_name || `#${log.entity_id}`}
                          </button>
                        ) : (
                          <span className="text-foreground">{log.entity_name || (log.entity_id ? `#${log.entity_id}` : '-')}</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-muted-foreground max-w-[200px] truncate" title={log.details || undefined}>
                        {log.details || '-'}
                      </td>
                      <td className="px-2 py-2.5">
                        {expandable && (
                          <button
                            onClick={() => setExpandedId(isExpanded ? null : log.id)}
                            className="p-1 text-muted-foreground hover:text-foreground rounded"
                            title={expandTitle(hasChanges, detailsClipped)}
                          >
                            {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                          </button>
                        )}
                      </td>
                    </tr>
                    {isExpanded && expandable && (
                      <tr className="bg-muted/10">
                        <td colSpan={7} className="px-4 py-3">
                          <div className="text-xs space-y-1.5">
                            {detailsClipped && (
                              <p className="text-foreground whitespace-pre-wrap break-words mb-2">{log.details}</p>
                            )}
                            {log.ip_address && (
                              <p className="text-muted-foreground mb-2">
                                IP address: <span className="text-foreground break-all">{log.ip_address}</span>
                              </p>
                            )}
                            {hasChanges && <p className="font-medium text-muted-foreground mb-2">Changes:</p>}
                            {entries.map(([field, change]) => (
                              <ChangeLine key={field} field={field} change={change} />
                            ))}
                          </div>
                        </td>
                      </tr>
                    )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {total > perPage && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-border">
            <p className="text-xs text-muted-foreground">
              Showing {(page - 1) * perPage + 1}-{Math.min(page * perPage, total)} of {total}
            </p>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="p-1.5 text-muted-foreground hover:text-foreground disabled:opacity-30 rounded hover:bg-accent/30"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="text-xs text-muted-foreground px-2">
                Page {page} of {totalPages}
              </span>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="p-1.5 text-muted-foreground hover:text-foreground disabled:opacity-30 rounded hover:bg-accent/30"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
