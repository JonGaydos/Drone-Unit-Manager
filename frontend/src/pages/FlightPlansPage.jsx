import React, { useState, useEffect } from 'react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { sortByName, sortVehicles, sortPilotsActiveFirst } from '@/lib/formatters'
import {
  ClipboardCheck, Plus, Filter, X, Loader2, Check, Ban, Clock,
  ChevronDown, ChevronUp, Cloud, Download,
} from 'lucide-react'

const STATUS_COLORS = {
  pending: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  approved: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  denied: 'bg-red-500/15 text-red-400 border-red-500/30',
  cancelled: 'bg-zinc-500/15 text-zinc-400 border-zinc-500/30',
  completed: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
}

const STATUSES = ['pending', 'approved', 'denied', 'cancelled', 'completed']

function PlanModal({ pilots, vehicles, currentUser, onSave, onClose }) {
  const toast = useToast()
  const autoFillPilotId = currentUser?.pilot_id || ''
  const [form, setForm] = useState({
    title: '',
    date_planned: '',
    pilot_id: autoFillPilotId ? String(autoFillPilotId) : '',
    vehicle_id: '',
    location: '',
    purpose: '',
    case_number: '',
    description: '',
    max_altitude_planned: '',
    estimated_duration_min: '',
    checklist_completed: false,
    notes: '',
  })
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.title || !form.date_planned || !form.pilot_id) return
    // Validate altitude
    if (form.max_altitude_planned) {
      const alt = parseFloat(form.max_altitude_planned)
      if (alt < 0 || alt > 400) {
        toast.error('Altitude must be between 0 and 400 ft AGL (FAA Part 107)')
        return
      }
    }
    const data = { ...form }
    data.pilot_id = parseInt(data.pilot_id)
    if (data.vehicle_id) data.vehicle_id = parseInt(data.vehicle_id); else delete data.vehicle_id
    if (data.max_altitude_planned) data.max_altitude_planned = parseFloat(data.max_altitude_planned); else delete data.max_altitude_planned
    if (data.estimated_duration_min) data.estimated_duration_min = parseInt(data.estimated_duration_min); else delete data.estimated_duration_min
    Object.keys(data).forEach(k => { if (data[k] === '') delete data[k] })
    setSaving(true)
    try { await onSave(data) } finally { setSaving(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-xl p-6 w-full max-w-2xl shadow-xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-foreground mb-4">Submit Flight Plan</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Title *</label>
            <input type="text" value={form.title} onChange={e => setForm({ ...form, title: e.target.value })}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" required />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Planned Date/Time *</label>
              <input type="datetime-local" value={form.date_planned} onChange={e => setForm({ ...form, date_planned: e.target.value })}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" required />
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Pilot *</label>
              <select value={form.pilot_id} onChange={e => setForm({ ...form, pilot_id: e.target.value })}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" required>
                <option value="">Select pilot...</option>
                {sortPilotsActiveFirst(pilots).map(p => <option key={p.id} value={p.id}>{p.full_name}</option>)}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Vehicle</label>
              <select value={form.vehicle_id} onChange={e => setForm({ ...form, vehicle_id: e.target.value })}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
                <option value="">Select vehicle...</option>
                {sortVehicles(vehicles).map(v => <option key={v.id} value={v.id}>{v.manufacturer} {v.model}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Location</label>
              <input type="text" value={form.location} onChange={e => setForm({ ...form, location: e.target.value })}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Purpose</label>
              <input type="text" value={form.purpose} onChange={e => setForm({ ...form, purpose: e.target.value })}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Case Number</label>
              <input type="text" value={form.case_number} onChange={e => setForm({ ...form, case_number: e.target.value })}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Description</label>
            <textarea value={form.description} onChange={e => setForm({ ...form, description: e.target.value })}
              rows={3} className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm resize-none" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Max Altitude (ft)</label>
              <input type="number" min="0" max="400" step="1" value={form.max_altitude_planned} onChange={e => setForm({ ...form, max_altitude_planned: e.target.value })}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" placeholder="Max 400 ft AGL" />
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Est. Duration (min)</label>
              <input type="number" value={form.estimated_duration_min} onChange={e => setForm({ ...form, estimated_duration_min: e.target.value })}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <input type="checkbox" id="checklist" checked={form.checklist_completed}
              onChange={e => setForm({ ...form, checklist_completed: e.target.checked })}
              className="rounded border-border" />
            <label htmlFor="checklist" className="text-sm text-foreground">Pre-flight checklist completed</label>
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Notes</label>
            <textarea value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })}
              rows={2} className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm resize-none" />
          </div>
          <div className="flex gap-2 pt-2">
            <button type="submit" disabled={saving}
              className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Submit Plan'}
            </button>
            <button type="button" onClick={onClose}
              className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm">Cancel</button>
          </div>
        </form>
      </div>
    </div>
  )
}

function DenyModal({ plan, onDeny, onClose }) {
  const [reason, setReason] = useState('')
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!reason) return
    setSaving(true)
    try { await onDeny(plan.id, { denial_reason: reason, review_notes: notes || undefined }) } finally { setSaving(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-xl p-6 w-full max-w-md shadow-xl" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-foreground mb-4">Deny Flight Plan</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Denial Reason *</label>
            <textarea value={reason} onChange={e => setReason(e.target.value)}
              rows={3} className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm resize-none" required />
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Review Notes</label>
            <textarea value={notes} onChange={e => setNotes(e.target.value)}
              rows={2} className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm resize-none" />
          </div>
          <div className="flex gap-2 pt-2">
            <button type="submit" disabled={saving}
              className="flex-1 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Deny Plan'}
            </button>
            <button type="button" onClick={onClose}
              className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm">Cancel</button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function FlightPlansPage() {
  const [plans, setPlans] = useState([])
  const [pilots, setPilots] = useState([])
  const [vehicles, setVehicles] = useState([])
  const [pendingCount, setPendingCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [denyTarget, setDenyTarget] = useState(null)
  const [expandedId, setExpandedId] = useState(null)
  const [viewMode, setViewMode] = useState('all') // 'all' or 'mine'
  const [statusFilter, setStatusFilter] = useState('')
  const { user, isAdmin } = useAuth()
  const toast = useToast()
  const isSupervisor = user?.role === 'admin' || user?.role === 'supervisor'

  const load = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (statusFilter) params.set('status', statusFilter)
      if (viewMode === 'mine' && user?.id) params.set('submitted_by_id', user.id)
      const qs = params.toString() ? `?${params}` : ''
      const [p, pi, v, pc] = await Promise.all([
        api.get(`/flight-plans${qs}`),
        api.get('/pilots'),
        api.get('/vehicles'),
        api.get('/flight-plans/pending/count'),
      ])
      setPlans(Array.isArray(p) ? p : p.plans || p.flight_plans || [])
      setPilots(Array.isArray(pi) ? pi : pi.pilots || [])
      setVehicles(Array.isArray(v) ? v : v.vehicles || [])
      setPendingCount(pc.count)
    } catch (err) {
      toast.error(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [viewMode, statusFilter])

  const handleCreate = async (data) => {
    try {
      await api.post('/flight-plans', data)
      toast.success('Flight plan submitted')
      setShowAdd(false)
      load()
    } catch (err) {
      toast.error(err.message)
    }
  }

  const handleApprove = async (id) => {
    try {
      await api.post(`/flight-plans/${id}/approve`, {})
      toast.success('Flight plan approved')
      load()
    } catch (err) {
      toast.error(err.message)
    }
  }

  const handleDeny = async (id, data) => {
    try {
      await api.post(`/flight-plans/${id}/deny`, data)
      toast.success('Flight plan denied')
      setDenyTarget(null)
      load()
    } catch (err) {
      toast.error(err.message)
    }
  }

  const handleCancel = async (id) => {
    if (!window.confirm('Cancel this flight plan?')) return
    try {
      await api.post(`/flight-plans/${id}/cancel`, {})
      toast.success('Flight plan cancelled')
      load()
    } catch (err) {
      toast.error(err.message)
    }
  }

  const handleAdminEdit = async (id) => {
    try {
      await api.patch(`/flight-plans/${id}`, { status: 'pending' })
      toast.success('Plan reopened as pending for editing')
      load()
    } catch (err) {
      toast.error(err.message)
    }
  }

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this flight plan?')) return
    try {
      await api.delete(`/flight-plans/${id}`)
      toast.success('Flight plan deleted')
      load()
    } catch (err) {
      toast.error(err.message)
    }
  }

  const formatDT = (dt) => {
    if (!dt) return '—'
    try {
      return new Date(dt).toLocaleString(undefined, {
        month: 'short', day: 'numeric', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
      })
    } catch { return dt }
  }

  if (loading && plans.length === 0) {
    return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3 flex-wrap">
          {/* View Mode Tabs */}
          <div className="flex items-center bg-secondary rounded-lg border border-border">
            <button onClick={() => setViewMode('all')}
              className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${viewMode === 'all' ? 'bg-primary text-primary-foreground font-medium' : 'text-muted-foreground hover:text-foreground'}`}>
              All Plans
            </button>
            <button onClick={() => setViewMode('mine')}
              className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${viewMode === 'mine' ? 'bg-primary text-primary-foreground font-medium' : 'text-muted-foreground hover:text-foreground'}`}>
              My Plans
            </button>
          </div>
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-muted-foreground" />
            <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
              className="px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
              <option value="">All Statuses</option>
              {STATUSES.map(s => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
            </select>
          </div>
          {pendingCount > 0 && (
            <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-amber-500/15 text-amber-400 rounded-full text-xs font-medium border border-amber-500/30">
              <Clock className="w-3 h-3" /> {pendingCount} Pending
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => api.download('/export/flight-plans/csv')}
            className="flex items-center gap-2 px-3 py-2 bg-secondary border border-border text-secondary-foreground rounded-lg text-sm hover:bg-secondary/80">
            <Download className="w-4 h-4" /> Export CSV
          </button>
          <button onClick={() => setShowAdd(true)}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90">
            <Plus className="w-4 h-4" /> Submit Plan
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-secondary/50">
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Date</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Title</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Pilot</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Vehicle</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Location</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Purpose</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Status</th>
                <th className="text-right px-4 py-3 font-medium text-muted-foreground">Actions</th>
              </tr>
            </thead>
            <tbody>
              {plans.map(plan => (
                <React.Fragment key={plan.id}>
                  <tr className="border-b border-border hover:bg-secondary/30 cursor-pointer"
                    onClick={() => setExpandedId(expandedId === plan.id ? null : plan.id)}>
                    <td className="px-4 py-3 text-foreground whitespace-nowrap">{formatDT(plan.date_planned)}</td>
                    <td className="px-4 py-3 text-foreground font-medium">{plan.title}</td>
                    <td className="px-4 py-3 text-muted-foreground">{plan.pilot_name || '—'}</td>
                    <td className="px-4 py-3 text-muted-foreground">{plan.vehicle_name || '—'}</td>
                    <td className="px-4 py-3 text-muted-foreground">{plan.location || '—'}</td>
                    <td className="px-4 py-3 text-muted-foreground">{plan.purpose || '—'}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium border ${STATUS_COLORS[plan.status] || ''}`}>
                        {plan.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right" onClick={e => e.stopPropagation()}>
                      <div className="flex items-center justify-end gap-1">
                        <button onClick={() => setExpandedId(expandedId === plan.id ? null : plan.id)}
                          className="p-1.5 text-muted-foreground hover:text-foreground rounded-lg hover:bg-accent" title="Details">
                          {expandedId === plan.id ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                        </button>
                        {isSupervisor && plan.status === 'pending' && (
                          <>
                            <button onClick={() => handleApprove(plan.id)}
                              className="p-1.5 text-muted-foreground hover:text-emerald-400 rounded-lg hover:bg-emerald-500/10" title="Approve">
                              <Check className="w-4 h-4" />
                            </button>
                            <button onClick={() => setDenyTarget(plan)}
                              className="p-1.5 text-muted-foreground hover:text-red-400 rounded-lg hover:bg-red-500/10" title="Deny">
                              <Ban className="w-4 h-4" />
                            </button>
                          </>
                        )}
                        {(plan.submitted_by_id === user?.id || isSupervisor) && (plan.status === 'pending' || plan.status === 'approved') && (
                          <button onClick={() => handleCancel(plan.id)}
                            className="p-1.5 text-muted-foreground hover:text-amber-400 rounded-lg hover:bg-amber-500/10" title="Cancel">
                            <X className="w-4 h-4" />
                          </button>
                        )}
                        {isAdmin && (plan.status === 'cancelled' || plan.status === 'denied') && (
                          <button onClick={() => { /* Admin override edit - reopen plan */ handleAdminEdit(plan.id) }}
                            className="p-1.5 text-muted-foreground hover:text-primary rounded-lg hover:bg-primary/10" title="Edit (Admin Override)">
                            <ClipboardCheck className="w-4 h-4" />
                          </button>
                        )}
                        {isSupervisor && (
                          <button onClick={() => handleDelete(plan.id)}
                            className="p-1.5 text-muted-foreground hover:text-destructive rounded-lg hover:bg-destructive/10" title="Delete">
                            <X className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                  {expandedId === plan.id && (
                    <tr key={`${plan.id}-detail`} className="border-b border-border">
                      <td colSpan={8} className="px-4 py-4 bg-secondary/20">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                          <div>
                            {plan.description && (
                              <div className="mb-3">
                                <h4 className="font-medium text-foreground mb-1">Description</h4>
                                <p className="text-muted-foreground whitespace-pre-wrap">{plan.description}</p>
                              </div>
                            )}
                            {plan.case_number && (
                              <p className="text-muted-foreground"><span className="text-foreground font-medium">Case #:</span> {plan.case_number}</p>
                            )}
                            {plan.max_altitude_planned && (
                              <p className="text-muted-foreground mt-1"><span className="text-foreground font-medium">Max Altitude:</span> {plan.max_altitude_planned} ft</p>
                            )}
                            {plan.estimated_duration_min && (
                              <p className="text-muted-foreground mt-1"><span className="text-foreground font-medium">Est. Duration:</span> {plan.estimated_duration_min} min</p>
                            )}
                            <p className="text-muted-foreground mt-1">
                              <span className="text-foreground font-medium">Checklist:</span>{' '}
                              {plan.checklist_completed ? <span className="text-emerald-400">Completed</span> : <span className="text-amber-400">Not completed</span>}
                            </p>
                            {plan.location && (
                              <a
                                href={`https://weather.gov/`}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 mt-2 text-primary hover:underline text-xs"
                              >
                                <Cloud className="w-3 h-3" /> Weather Briefing
                              </a>
                            )}
                          </div>
                          <div>
                            {plan.review_date && (
                              <div className="mb-3">
                                <h4 className="font-medium text-foreground mb-1">Review</h4>
                                <p className="text-muted-foreground">Reviewed by: {plan.reviewed_by_name || '—'}</p>
                                <p className="text-muted-foreground">Date: {formatDT(plan.review_date)}</p>
                                {plan.review_notes && <p className="text-muted-foreground mt-1">{plan.review_notes}</p>}
                              </div>
                            )}
                            {plan.denial_reason && (
                              <div className="mb-3">
                                <h4 className="font-medium text-red-400 mb-1">Denial Reason</h4>
                                <p className="text-muted-foreground whitespace-pre-wrap">{plan.denial_reason}</p>
                              </div>
                            )}
                            {plan.notes && (
                              <div className="mb-3">
                                <h4 className="font-medium text-foreground mb-1">Notes</h4>
                                <p className="text-muted-foreground whitespace-pre-wrap">{plan.notes}</p>
                              </div>
                            )}
                            <p className="text-xs text-muted-foreground mt-3">Submitted by: {plan.submitted_by_name || '—'}</p>
                            {plan.linked_flight_id && (
                              <p className="text-xs text-muted-foreground mt-1">Linked Flight: #{plan.linked_flight_id}</p>
                            )}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
              {plans.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center">
                    <ClipboardCheck className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
                    <p className="text-muted-foreground">No flight plans found</p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {showAdd && (
        <PlanModal pilots={pilots} vehicles={vehicles} currentUser={user}
          onSave={handleCreate} onClose={() => setShowAdd(false)} />
      )}
      {denyTarget && (
        <DenyModal plan={denyTarget}
          onDeny={handleDeny} onClose={() => setDenyTarget(null)} />
      )}
    </div>
  )
}
