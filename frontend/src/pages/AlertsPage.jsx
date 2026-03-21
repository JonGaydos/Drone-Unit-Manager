import { useState, useEffect } from 'react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { Bell, CheckCircle, X, Filter, AlertTriangle, Info, AlertOctagon } from 'lucide-react'

const SEVERITY_CONFIG = {
  info: { color: 'bg-blue-500/15 text-blue-400', icon: Info },
  warning: { color: 'bg-amber-500/15 text-amber-400', icon: AlertTriangle },
  critical: { color: 'bg-red-500/15 text-red-400', icon: AlertOctagon },
}

export default function AlertsPage() {
  const [alerts, setAlerts] = useState([])
  const [count, setCount] = useState(0)
  const [severityFilter, setSeverityFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const { isAdmin } = useAuth()

  const load = () => {
    setLoading(true)
    const params = severityFilter ? `?severity=${severityFilter}` : ''
    Promise.all([
      api.get(`/alerts${params}`),
      api.get('/alerts/count'),
    ]).then(([a, c]) => {
      setAlerts(a)
      setCount(typeof c === 'object' ? c.count : c)
    }).catch(console.error).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [severityFilter])

  const handleMarkRead = async (id) => {
    try {
      await api.patch(`/alerts/${id}/read`)
      load()
    } catch (err) {
      alert(err.message)
    }
  }

  const handleDismiss = async (id) => {
    try {
      await api.patch(`/alerts/${id}/dismiss`)
      load()
    } catch (err) {
      alert(err.message)
    }
  }

  const handleDismissAll = async () => {
    if (!confirm('Dismiss all alerts?')) return
    try {
      await api.post('/alerts/dismiss-all')
      load()
    } catch (err) {
      alert(err.message)
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-muted-foreground" />
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              className="px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm"
            >
              <option value="">All Severities</option>
              <option value="info">Info</option>
              <option value="warning">Warning</option>
              <option value="critical">Critical</option>
            </select>
          </div>
          <span className="text-sm text-muted-foreground">{count} total alerts</span>
        </div>
        {alerts.length > 0 && (
          <button
            onClick={handleDismissAll}
            className="flex items-center gap-2 px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm font-medium hover:opacity-90"
          >
            <X className="w-4 h-4" /> Dismiss All
          </button>
        )}
      </div>

      {/* Alert List */}
      <div className="space-y-2">
        {alerts.map(a => {
          const config = SEVERITY_CONFIG[a.severity] || SEVERITY_CONFIG.info
          const SeverityIcon = config.icon

          return (
            <div
              key={a.id}
              className={`bg-card border border-border rounded-xl p-4 transition-colors ${a.is_read ? 'opacity-60' : ''}`}
            >
              <div className="flex items-start gap-3">
                <div className={`p-2 rounded-lg ${config.color} shrink-0`}>
                  <SeverityIcon className="w-4 h-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-semibold text-foreground">{a.title || 'Alert'}</h3>
                        <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${config.color}`}>
                          {a.severity}
                        </span>
                        {!a.is_read && (
                          <span className="inline-flex w-2 h-2 rounded-full bg-primary" />
                        )}
                      </div>
                      <p className="text-sm text-muted-foreground mt-1">{a.message || ''}</p>
                      <p className="text-xs text-muted-foreground mt-1.5">{a.created_at || ''}</p>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      {!a.is_read && (
                        <button
                          onClick={() => handleMarkRead(a.id)}
                          className="p-1.5 text-muted-foreground hover:text-foreground rounded-lg hover:bg-accent"
                          title="Mark as read"
                        >
                          <CheckCircle className="w-4 h-4" />
                        </button>
                      )}
                      <button
                        onClick={() => handleDismiss(a.id)}
                        className="p-1.5 text-muted-foreground hover:text-destructive rounded-lg hover:bg-destructive/10"
                        title="Dismiss"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )
        })}
        {alerts.length === 0 && (
          <div className="bg-card border border-border rounded-xl p-12 text-center">
            <Bell className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
            <p className="text-muted-foreground">No alerts found</p>
          </div>
        )}
      </div>
    </div>
  )
}
