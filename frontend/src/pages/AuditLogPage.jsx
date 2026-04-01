import { useState, useEffect } from 'react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { ChevronLeft, ChevronRight, ChevronDown, ChevronUp, Filter, ScrollText, Download } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

const ENTITY_TYPES = [
  '', 'flight', 'pilot', 'vehicle', 'certification_type', 'pilot_certification',
  'maintenance', 'mission_log', 'training_log', 'user', 'auth', 'system',
]

const ACTIONS = [
  '', 'create', 'update', 'delete', 'deactivate', 'retire', 'login', 'login_failed',
  'password_change', 'sync', 'bulk_approve', 'bulk_update',
]

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
  const { isAdmin } = useAuth()
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
  const [showFilters, setShowFilters] = useState(false)

  useEffect(() => {
    if (!isAdmin) return
    setLoading(true)
    const params = new URLSearchParams()
    params.set('page', page)
    params.set('per_page', perPage)
    if (entityType) params.set('entity_type', entityType)
    if (action) params.set('action', action)

    api.get(`/audit?${params.toString()}`)
      .then(data => {
        setLogs(data.logs)
        setTotal(data.total)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [isAdmin, page, perPage, entityType, action])

  if (!isAdmin) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-muted-foreground">Admin access required to view audit logs.</p>
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
          <button
            onClick={() => api.download('/export/audit/csv')}
            className="flex items-center gap-2 px-3 py-2 bg-secondary border border-border rounded-lg text-sm text-foreground hover:bg-accent/30 transition-colors"
          >
            <Download className="w-4 h-4" /> Export CSV
          </button>
          <button
            onClick={() => setShowFilters(!showFilters)}
            className="flex items-center gap-2 px-3 py-2 bg-secondary border border-border rounded-lg text-sm text-foreground hover:bg-accent/30 transition-colors"
          >
            <Filter className="w-4 h-4" />
            Filters
          {(entityType || action) && (
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
                <option key={t} value={t}>{t.replace('_', ' ')}</option>
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
                <option key={a} value={a}>{a.replace('_', ' ')}</option>
              ))}
            </select>
          </div>
          {(entityType || action) && (
            <div className="flex items-end">
              <button
                onClick={() => { setEntityType(''); setAction(''); setPage(1) }}
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
        {loading ? (
          <div className="flex items-center justify-center h-32">
            <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          </div>
        ) : logs.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
            No audit log entries found.
          </div>
        ) : (
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
                  const hasChanges = log.changes && Object.keys(log.changes).length > 0
                  const isExpanded = expandedId === log.id

                  return (
                    <tr key={log.id} className="border-b border-border/50 hover:bg-muted/20">
                      <td className="px-4 py-2.5 text-muted-foreground whitespace-nowrap text-xs">
                        {formatTimestamp(log.created_at)}
                      </td>
                      <td className="px-4 py-2.5 text-foreground">
                        {log.user_name || '-'}
                      </td>
                      <td className="px-4 py-2.5">
                        <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${ACTION_COLORS[log.action] || 'bg-muted text-muted-foreground'}`}>
                          {log.action?.replace('_', ' ')}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-muted-foreground capitalize">
                        {log.entity_type?.replace('_', ' ') || '-'}
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
                      <td className="px-4 py-2.5 text-muted-foreground max-w-[200px] truncate">
                        {log.details || '-'}
                      </td>
                      <td className="px-2 py-2.5">
                        {hasChanges && (
                          <button
                            onClick={() => setExpandedId(isExpanded ? null : log.id)}
                            className="p-1 text-muted-foreground hover:text-foreground rounded"
                            title="View changes"
                          >
                            {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
                {/* Expanded changes rows */}
                {logs.map(log => {
                  if (expandedId !== log.id || !log.changes) return null
                  const entries = Object.entries(log.changes)
                  return (
                    <tr key={`${log.id}-changes`} className="bg-muted/10">
                      <td colSpan={7} className="px-4 py-3">
                        <div className="text-xs space-y-1.5">
                          <p className="font-medium text-muted-foreground mb-2">Changes:</p>
                          {entries.map(([field, vals]) => (
                            <div key={field} className="flex items-start gap-2">
                              <span className="font-medium text-foreground min-w-[120px]">{field}:</span>
                              <span className="text-red-400 line-through">{vals.old || '(empty)'}</span>
                              <span className="text-muted-foreground">-&gt;</span>
                              <span className="text-emerald-400">{vals.new || '(empty)'}</span>
                            </div>
                          ))}
                        </div>
                      </td>
                    </tr>
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
