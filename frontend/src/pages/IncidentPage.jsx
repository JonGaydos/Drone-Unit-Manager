import { useState, useEffect } from 'react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { sortByName, sortVehicles } from '@/lib/formatters'
import {
  AlertTriangle, Plus, Filter, Search, ChevronDown, ChevronUp,
  X, Loader2, CheckCircle, Eye, Shield,
} from 'lucide-react'

const SEVERITY_COLORS = {
  minor: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  moderate: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  major: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
  critical: 'bg-red-500/15 text-red-400 border-red-500/30',
}

const STATUS_COLORS = {
  open: 'bg-red-500/15 text-red-400 border-red-500/30',
  investigating: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  resolved: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  closed: 'bg-zinc-500/15 text-zinc-400 border-zinc-500/30',
}

const CATEGORIES = [
  { value: 'crash', label: 'Crash' },
  { value: 'near_miss', label: 'Near Miss' },
  { value: 'equipment_failure', label: 'Equipment Failure' },
  { value: 'injury', label: 'Injury' },
  { value: 'airspace_violation', label: 'Airspace Violation' },
  { value: 'other', label: 'Other' },
]

const SEVERITIES = ['minor', 'moderate', 'major', 'critical']
const STATUSES = ['open', 'investigating', 'resolved', 'closed']

function formatCategory(cat) {
  return cat ? cat.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) : ''
}

function IncidentModal({ pilots, vehicles, flights, onSave, onClose }) {
  const [form, setForm] = useState({
    date: new Date().toISOString().slice(0, 10),
    title: '', severity: 'minor', category: 'other', description: '',
    location: '', lat: '', lon: '', flight_id: '', pilot_id: '', vehicle_id: '',
    equipment_grounded: false, damage_description: '', estimated_cost: '', notes: '',
  })
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.title || !form.description) return
    const data = { ...form }
    if (data.pilot_id) data.pilot_id = parseInt(data.pilot_id); else delete data.pilot_id
    if (data.vehicle_id) data.vehicle_id = parseInt(data.vehicle_id); else delete data.vehicle_id
    if (data.flight_id) data.flight_id = parseInt(data.flight_id); else delete data.flight_id
    if (data.lat) data.lat = parseFloat(data.lat); else delete data.lat
    if (data.lon) data.lon = parseFloat(data.lon); else delete data.lon
    if (data.estimated_cost) data.estimated_cost = parseFloat(data.estimated_cost); else delete data.estimated_cost
    Object.keys(data).forEach(k => { if (data[k] === '') delete data[k] })
    setSaving(true)
    try { await onSave(data) } finally { setSaving(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-xl p-6 w-full max-w-2xl shadow-xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-foreground mb-4">Report Incident</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Date *</label>
              <input type="date" value={form.date} onChange={e => setForm({ ...form, date: e.target.value })}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" required />
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Severity *</label>
              <select value={form.severity} onChange={e => setForm({ ...form, severity: e.target.value })}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
                {SEVERITIES.map(s => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Title *</label>
            <input type="text" value={form.title} onChange={e => setForm({ ...form, title: e.target.value })}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" required />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Category *</label>
              <select value={form.category} onChange={e => setForm({ ...form, category: e.target.value })}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
                {CATEGORIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Location</label>
              <input type="text" value={form.location} onChange={e => setForm({ ...form, location: e.target.value })}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Description *</label>
            <textarea value={form.description} onChange={e => setForm({ ...form, description: e.target.value })}
              rows={3} className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm resize-none" required />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Pilot</label>
              <select value={form.pilot_id} onChange={e => setForm({ ...form, pilot_id: e.target.value })}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
                <option value="">Select...</option>
                {sortByName(pilots).map(p => <option key={p.id} value={p.id}>{p.full_name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Vehicle</label>
              <select value={form.vehicle_id} onChange={e => setForm({ ...form, vehicle_id: e.target.value })}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
                <option value="">Select...</option>
                {sortVehicles(vehicles).map(v => <option key={v.id} value={v.id}>{v.manufacturer} {v.model}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Linked Flight</label>
              <select value={form.flight_id} onChange={e => setForm({ ...form, flight_id: e.target.value })}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
                <option value="">None</option>
                {flights.map(f => <option key={f.id} value={f.id}>#{f.id} — {f.date || 'No date'}</option>)}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Damage Description</label>
              <textarea value={form.damage_description} onChange={e => setForm({ ...form, damage_description: e.target.value })}
                rows={2} className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm resize-none" />
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Estimated Cost ($)</label>
              <input type="number" step="0.01" value={form.estimated_cost} onChange={e => setForm({ ...form, estimated_cost: e.target.value })}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <input type="checkbox" id="equip_grounded" checked={form.equipment_grounded}
              onChange={e => setForm({ ...form, equipment_grounded: e.target.checked })}
              className="rounded border-border" />
            <label htmlFor="equip_grounded" className="text-sm text-foreground">Equipment Grounded</label>
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Notes</label>
            <textarea value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })}
              rows={2} className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm resize-none" />
          </div>
          <div className="flex gap-2 pt-2">
            <button type="submit" disabled={saving}
              className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Report Incident'}
            </button>
            <button type="button" onClick={onClose}
              className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm">Cancel</button>
          </div>
        </form>
      </div>
    </div>
  )
}

function ResolveModal({ incident, onSave, onClose }) {
  const [form, setForm] = useState({
    status: 'resolved',
    resolution: incident.resolution || '',
    resolution_date: new Date().toISOString().slice(0, 10),
    corrective_actions: incident.corrective_actions || '',
  })
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSaving(true)
    try { await onSave(incident.id, form) } finally { setSaving(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-xl p-6 w-full max-w-lg shadow-xl" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-foreground mb-4">Resolve Incident</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Status</label>
            <select value={form.status} onChange={e => setForm({ ...form, status: e.target.value })}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
              <option value="investigating">Investigating</option>
              <option value="resolved">Resolved</option>
              <option value="closed">Closed</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Resolution</label>
            <textarea value={form.resolution} onChange={e => setForm({ ...form, resolution: e.target.value })}
              rows={3} className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm resize-none" />
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Corrective Actions</label>
            <textarea value={form.corrective_actions} onChange={e => setForm({ ...form, corrective_actions: e.target.value })}
              rows={3} className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm resize-none" />
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Resolution Date</label>
            <input type="date" value={form.resolution_date} onChange={e => setForm({ ...form, resolution_date: e.target.value })}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
          </div>
          <div className="flex gap-2 pt-2">
            <button type="submit" disabled={saving}
              className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Update'}
            </button>
            <button type="button" onClick={onClose}
              className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm">Cancel</button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function IncidentPage() {
  const [incidents, setIncidents] = useState([])
  const [stats, setStats] = useState(null)
  const [pilots, setPilots] = useState([])
  const [vehicles, setVehicles] = useState([])
  const [flights, setFlights] = useState([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [resolveTarget, setResolveTarget] = useState(null)
  const [expandedId, setExpandedId] = useState(null)
  const [filters, setFilters] = useState({ status: '', severity: '', category: '', date_from: '', date_to: '' })
  const { user, isAdmin } = useAuth()
  const toast = useToast()
  const isSupervisor = user?.role === 'admin' || user?.role === 'supervisor'

  const load = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (filters.status) params.set('status', filters.status)
      if (filters.severity) params.set('severity', filters.severity)
      if (filters.category) params.set('category', filters.category)
      if (filters.date_from) params.set('date_from', filters.date_from)
      if (filters.date_to) params.set('date_to', filters.date_to)
      const qs = params.toString() ? `?${params}` : ''
      const [inc, st, p, v, f] = await Promise.all([
        api.get(`/incidents${qs}`),
        api.get('/incidents/stats'),
        api.get('/pilots'),
        api.get('/vehicles'),
        api.get('/flights?limit=100'),
      ])
      setIncidents(inc)
      setStats(st)
      setPilots(p)
      setVehicles(v)
      setFlights(f)
    } catch (err) {
      toast.error(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [filters.status, filters.severity, filters.category])

  const handleCreate = async (data) => {
    try {
      await api.post('/incidents', data)
      toast.success('Incident reported')
      setShowAdd(false)
      load()
    } catch (err) {
      toast.error(err.message)
    }
  }

  const handleResolve = async (id, data) => {
    try {
      await api.patch(`/incidents/${id}`, data)
      toast.success('Incident updated')
      setResolveTarget(null)
      load()
    } catch (err) {
      toast.error(err.message)
    }
  }

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this incident report?')) return
    try {
      await api.delete(`/incidents/${id}`)
      toast.success('Incident deleted')
      load()
    } catch (err) {
      toast.error(err.message)
    }
  }

  if (loading && incidents.length === 0) {
    return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
  }

  const openCount = stats?.by_status?.open || 0
  const investigatingCount = stats?.by_status?.investigating || 0
  const resolvedCount = stats?.by_status?.resolved || 0
  const totalCount = stats?.total || 0

  return (
    <div className="space-y-4">
      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-card border border-border rounded-xl p-4">
          <p className="text-xs text-muted-foreground uppercase tracking-wider">Open</p>
          <p className="text-2xl font-bold text-red-400 mt-1">{openCount}</p>
        </div>
        <div className="bg-card border border-border rounded-xl p-4">
          <p className="text-xs text-muted-foreground uppercase tracking-wider">Investigating</p>
          <p className="text-2xl font-bold text-amber-400 mt-1">{investigatingCount}</p>
        </div>
        <div className="bg-card border border-border rounded-xl p-4">
          <p className="text-xs text-muted-foreground uppercase tracking-wider">Resolved</p>
          <p className="text-2xl font-bold text-emerald-400 mt-1">{resolvedCount}</p>
        </div>
        <div className="bg-card border border-border rounded-xl p-4">
          <p className="text-xs text-muted-foreground uppercase tracking-wider">Total</p>
          <p className="text-2xl font-bold text-foreground mt-1">{totalCount}</p>
        </div>
      </div>

      {/* Header + Filters */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-muted-foreground" />
            <select value={filters.status} onChange={e => setFilters({ ...filters, status: e.target.value })}
              className="px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
              <option value="">All Statuses</option>
              {STATUSES.map(s => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
            </select>
          </div>
          <select value={filters.severity} onChange={e => setFilters({ ...filters, severity: e.target.value })}
            className="px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
            <option value="">All Severities</option>
            {SEVERITIES.map(s => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
          </select>
          <select value={filters.category} onChange={e => setFilters({ ...filters, category: e.target.value })}
            className="px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
            <option value="">All Categories</option>
            {CATEGORIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
          </select>
        </div>
        <button onClick={() => setShowAdd(true)}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90">
          <Plus className="w-4 h-4" /> Report Incident
        </button>
      </div>

      {/* Incidents Table */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-secondary/50">
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Date</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Title</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Severity</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Category</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Pilot</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Vehicle</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Status</th>
                <th className="text-right px-4 py-3 font-medium text-muted-foreground">Actions</th>
              </tr>
            </thead>
            <tbody>
              {incidents.map(inc => (
                <>
                  <tr key={inc.id} className="border-b border-border hover:bg-secondary/30 cursor-pointer"
                    onClick={() => setExpandedId(expandedId === inc.id ? null : inc.id)}>
                    <td className="px-4 py-3 text-foreground whitespace-nowrap">{inc.date}</td>
                    <td className="px-4 py-3 text-foreground font-medium">{inc.title}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium border ${SEVERITY_COLORS[inc.severity] || ''}`}>
                        {inc.severity}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-foreground">{formatCategory(inc.category)}</td>
                    <td className="px-4 py-3 text-muted-foreground">{inc.pilot_name || '—'}</td>
                    <td className="px-4 py-3 text-muted-foreground">{inc.vehicle_name || '—'}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium border ${STATUS_COLORS[inc.status] || ''}`}>
                        {inc.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right" onClick={e => e.stopPropagation()}>
                      <div className="flex items-center justify-end gap-1">
                        <button onClick={() => setExpandedId(expandedId === inc.id ? null : inc.id)}
                          className="p-1.5 text-muted-foreground hover:text-foreground rounded-lg hover:bg-accent" title="Details">
                          {expandedId === inc.id ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                        </button>
                        {isSupervisor && inc.status !== 'closed' && (
                          <button onClick={() => setResolveTarget(inc)}
                            className="p-1.5 text-muted-foreground hover:text-emerald-400 rounded-lg hover:bg-emerald-500/10" title="Resolve">
                            <CheckCircle className="w-4 h-4" />
                          </button>
                        )}
                        {isSupervisor && (
                          <button onClick={() => handleDelete(inc.id)}
                            className="p-1.5 text-muted-foreground hover:text-destructive rounded-lg hover:bg-destructive/10" title="Delete">
                            <X className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                  {expandedId === inc.id && (
                    <tr key={`${inc.id}-detail`} className="border-b border-border">
                      <td colSpan={8} className="px-4 py-4 bg-secondary/20">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                          <div>
                            <h4 className="font-medium text-foreground mb-2">Description</h4>
                            <p className="text-muted-foreground whitespace-pre-wrap">{inc.description}</p>
                            {inc.location && (
                              <p className="text-muted-foreground mt-2"><span className="text-foreground font-medium">Location:</span> {inc.location}</p>
                            )}
                            {inc.damage_description && (
                              <div className="mt-3">
                                <h4 className="font-medium text-foreground mb-1">Damage</h4>
                                <p className="text-muted-foreground whitespace-pre-wrap">{inc.damage_description}</p>
                              </div>
                            )}
                            {inc.estimated_cost != null && inc.estimated_cost > 0 && (
                              <p className="text-muted-foreground mt-2"><span className="text-foreground font-medium">Est. Cost:</span> ${inc.estimated_cost.toLocaleString()}</p>
                            )}
                            {inc.equipment_grounded && (
                              <p className="text-orange-400 mt-2 font-medium flex items-center gap-1">
                                <Shield className="w-4 h-4" /> Equipment Grounded
                              </p>
                            )}
                          </div>
                          <div>
                            {inc.resolution && (
                              <div className="mb-3">
                                <h4 className="font-medium text-foreground mb-1">Resolution</h4>
                                <p className="text-muted-foreground whitespace-pre-wrap">{inc.resolution}</p>
                                {inc.resolution_date && <p className="text-xs text-muted-foreground mt-1">Resolved: {inc.resolution_date}</p>}
                              </div>
                            )}
                            {inc.corrective_actions && (
                              <div className="mb-3">
                                <h4 className="font-medium text-foreground mb-1">Corrective Actions</h4>
                                <p className="text-muted-foreground whitespace-pre-wrap">{inc.corrective_actions}</p>
                              </div>
                            )}
                            {inc.notes && (
                              <div>
                                <h4 className="font-medium text-foreground mb-1">Notes</h4>
                                <p className="text-muted-foreground whitespace-pre-wrap">{inc.notes}</p>
                              </div>
                            )}
                            {inc.reported_by_name && (
                              <p className="text-xs text-muted-foreground mt-3">Reported by: {inc.reported_by_name}</p>
                            )}
                            {inc.flight_id && (
                              <p className="text-xs text-muted-foreground mt-1">Linked Flight: #{inc.flight_id}</p>
                            )}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
              {incidents.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center">
                    <AlertTriangle className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
                    <p className="text-muted-foreground">No incidents found</p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {showAdd && (
        <IncidentModal pilots={pilots} vehicles={vehicles} flights={flights}
          onSave={handleCreate} onClose={() => setShowAdd(false)} />
      )}
      {resolveTarget && (
        <ResolveModal incident={resolveTarget}
          onSave={handleResolve} onClose={() => setResolveTarget(null)} />
      )}
    </div>
  )
}
