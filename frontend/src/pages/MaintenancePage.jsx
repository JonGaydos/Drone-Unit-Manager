import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { useConfirm } from '@/hooks/useConfirm'
import { normalizeDateValue } from '@/lib/utils'
import { FREQUENCY_COLORS } from '@/lib/constants'
import { sortByName, sortPilotsActiveFirst, vehicleDisplayName, equipmentDisplayName } from '@/lib/formatters'
import { Plus, Trash2, Search, Wrench, CalendarClock, History, Download, Edit, CheckCircle, Clock } from 'lucide-react'

// Map entity_type to API endpoint
const ENTITY_ENDPOINTS = {
  vehicle: '/vehicles',
  battery: '/batteries',
  controller: '/controllers',
  dock: '/docks',
}

// Get display name for an entity from its data
function getEntityName(entity, entityType) {
  if (!entity) return '—'
  if (entityType === 'vehicle') return vehicleDisplayName(entity)
  if (entityType === 'battery' || entityType === 'controller') return equipmentDisplayName(entity)
  if (entityType === 'dock') return entity.name || entity.serial_number || `Dock #${entity.id}`
  return `#${entity.id}`
}

function MaintenanceModal({ record, onSave, onClose, entityLists, pilots }) {
  const [form, setForm] = useState(record || {
    entity_type: 'vehicle', entity_id: '', maintenance_type: 'scheduled',
    description: '', performed_by: '', performed_date: '', notes: ''
  })
  const [entityOptions, setEntityOptions] = useState([])

  // Update entity options when entity_type changes
  useEffect(() => {
    const list = entityLists[form.entity_type] || []
    setEntityOptions(list)
    // Reset entity_id if switching types (unless editing)
    if (!record) {
      setForm(prev => ({ ...prev, entity_id: '' }))
    }
  }, [form.entity_type, entityLists, record])

  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSubmitError(null)
    const data = { ...form }
    if (data.entity_id) data.entity_id = parseInt(data.entity_id)
    Object.keys(data).forEach(k => { if (data[k] === '') delete data[k] })
    setSubmitting(true)
    try {
      await onSave(data)
    } catch (err) {
      setSubmitError(err?.message || String(err) || 'Failed to save maintenance record')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-xl p-6 w-full max-w-lg shadow-xl" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-foreground mb-4">{record ? 'Edit Maintenance' : 'Add Maintenance'}</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Entity Type</label>
              <select
                value={form.entity_type}
                onChange={(e) => setForm({ ...form, entity_type: e.target.value, entity_id: '' })}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm"
              >
                <option value="vehicle">Vehicle</option>
                <option value="battery">Battery</option>
                <option value="controller">Controller</option>
                <option value="dock">Dock</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Entity</label>
              <select
                value={form.entity_id || ''}
                onChange={(e) => setForm({ ...form, entity_id: e.target.value })}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm"
              >
                <option value="">Select {form.entity_type}...</option>
                {[...entityOptions].sort((a, b) => getEntityName(a, form.entity_type).localeCompare(getEntityName(b, form.entity_type))).map(ent => (
                  <option key={ent.id} value={ent.id}>{getEntityName(ent, form.entity_type)}</option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Maintenance Type</label>
            <select
              value={form.maintenance_type}
              onChange={(e) => setForm({ ...form, maintenance_type: e.target.value })}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm"
            >
              <option value="scheduled">Scheduled</option>
              <option value="unscheduled">Unscheduled</option>
              <option value="inspection">Inspection</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Description</label>
            <input
              type="text"
              value={form.description || ''}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground focus:outline-none focus:ring-2 focus:ring-ring text-sm"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Performed By</label>
              <select
                value={form.performed_by || ''}
                onChange={(e) => setForm({ ...form, performed_by: e.target.value })}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm"
              >
                <option value="">Select pilot...</option>
                {sortPilotsActiveFirst(pilots).map(p => (
                  <option key={p.id} value={p.full_name}>{p.full_name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Performed Date</label>
              <input
                type="date"
                value={form.performed_date || ''}
                onChange={(e) => setForm({ ...form, performed_date: e.target.value })}
                onBlur={e => { const n = normalizeDateValue(e.target.value); if (n !== e.target.value) setForm(prev => ({...prev, performed_date: n})) }}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground focus:outline-none focus:ring-2 focus:ring-ring text-sm"
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Notes</label>
            <textarea
              value={form.notes || ''}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm h-20 resize-none"
            />
          </div>
          {submitError && <div className="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg p-2">{submitError}</div>}
          <div className="flex gap-2 pt-2">
            <button type="submit" disabled={submitting} className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50">
              {submitting ? 'Saving...' : (record ? 'Update' : 'Add Maintenance')}
            </button>
            <button type="button" onClick={onClose} className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90">
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function ScheduleModal({ schedule, onSave, onClose }) {
  const [form, setForm] = useState(schedule || {
    name: '', entity_type: 'vehicle', entity_id: '', frequency: 'monthly',
    description: '', assigned_to_id: ''
  })
  const [pilots, setPilots] = useState([])
  const [entities, setEntities] = useState([])

  useEffect(() => {
    api.get('/pilots').then(p => setPilots(Array.isArray(p) ? p : p.pilots || [])).catch(() => {})
  }, [])

  useEffect(() => {
    if (form.entity_type === 'organization') {
      setEntities([])
      return
    }
    const endpointMap = {
      vehicle: '/vehicles',
      battery: '/batteries',
      controller: '/controllers',
      dock: '/docks',
    }
    const endpoint = endpointMap[form.entity_type]
    if (endpoint) {
      api.get(endpoint).then(d => setEntities(Array.isArray(d) ? d : d.items || [])).catch(() => {})
    }
  }, [form.entity_type])

  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSubmitError(null)
    const data = { ...form }
    if (data.entity_id) data.entity_id = parseInt(data.entity_id)
    else data.entity_id = null
    if (data.assigned_to_id) data.assigned_to_id = parseInt(data.assigned_to_id)
    else data.assigned_to_id = null
    setSubmitting(true)
    try {
      await onSave(data)
    } catch (err) {
      setSubmitError(err?.message || String(err) || 'Failed to create schedule')
    } finally {
      setSubmitting(false)
    }
  }

  const getEntityLabel = (entity) => {
    if (entity.nickname) return `${entity.nickname} (${entity.serial_number || ''})`
    if (entity.name) return `${entity.name} (${entity.serial_number || ''})`
    return entity.serial_number || `#${entity.id}`
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-xl p-6 w-full max-w-lg shadow-xl" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-foreground mb-4">{schedule ? 'Edit Schedule' : 'Add Schedule'}</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Name *</label>
            <input
              type="text"
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Entity Type</label>
              <select
                value={form.entity_type}
                onChange={(e) => setForm({ ...form, entity_type: e.target.value, entity_id: '' })}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm"
              >
                <option value="vehicle">Vehicle</option>
                <option value="battery">Battery</option>
                <option value="controller">Controller</option>
                <option value="dock">Dock</option>
                <option value="organization">Organization-wide</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Entity</label>
              {form.entity_type === 'organization' ? (
                <input type="text" disabled value="All" className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-muted-foreground text-sm" />
              ) : (
                <select
                  value={form.entity_id}
                  onChange={(e) => setForm({ ...form, entity_id: e.target.value })}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm"
                >
                  <option value="">Select...</option>
                  {[...entities].sort((a, b) => getEntityLabel(a).localeCompare(getEntityLabel(b))).map(e => (
                    <option key={e.id} value={e.id}>{getEntityLabel(e)}</option>
                  ))}
                </select>
              )}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Frequency</label>
              <select
                value={form.frequency}
                onChange={(e) => setForm({ ...form, frequency: e.target.value })}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm"
              >
                <option value="monthly">Monthly</option>
                <option value="quarterly">Quarterly</option>
                <option value="yearly">Yearly</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Assigned To</label>
              <select
                value={form.assigned_to_id}
                onChange={(e) => setForm({ ...form, assigned_to_id: e.target.value })}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm"
              >
                <option value="">Unassigned</option>
                {sortPilotsActiveFirst(pilots).map(p => <option key={p.id} value={p.id}>{p.full_name}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Description</label>
            <textarea
              value={form.description || ''}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm h-20 resize-none"
            />
          </div>
          {submitError && <div className="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg p-2">{submitError}</div>}
          <div className="flex gap-2 pt-2">
            <button type="submit" disabled={submitting} className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50">
              {submitting ? 'Saving...' : (schedule ? 'Update' : 'Add Schedule')}
            </button>
            <button type="button" onClick={onClose} className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90">
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// Resolve entity name from the entity lists
function resolveEntityName(entityType, entityId, entityLists) {
  const list = entityLists[entityType] || []
  const entity = list.find(e => e.id === entityId)
  return entity ? getEntityName(entity, entityType) : `${entityType} #${entityId}`
}

// Render entity reference — clickable Link for vehicles, plain text for others
function EntityRef({ entityType, entityId, entityLists }) {
  const name = resolveEntityName(entityType, entityId, entityLists)
  if (entityType === 'vehicle') {
    return <Link to={`/fleet/vehicles/${entityId}`} className="text-primary hover:underline capitalize">{name}</Link>
  }
  return <span className="text-foreground capitalize">{name}</span>
}

export default function MaintenancePage() {
  const [upcomingRecords, setUpcomingRecords] = useState([])
  const [historyRecords, setHistoryRecords] = useState([])
  const [schedules, setSchedules] = useState([])
  const [search, setSearch] = useState('')
  const [modal, setModal] = useState(null)
  const [scheduleModal, setScheduleModal] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showAllUpcoming, setShowAllUpcoming] = useState(false)
  const { isAdmin, isPilot, isSupervisor } = useAuth()
  const toast = useToast()
  const [confirmProps, requestConfirm] = useConfirm()

  // Entity lists for name resolution and dropdowns
  const [entityLists, setEntityLists] = useState({ vehicle: [], battery: [], controller: [], dock: [] })
  const [pilots, setPilots] = useState([])

  // Load entity lists and pilots on mount
  useEffect(() => {
    Promise.all([
      api.get('/vehicles').catch(() => []),
      api.get('/batteries').catch(() => []),
      api.get('/controllers').catch(() => []),
      api.get('/docks').catch(() => []),
      api.get('/pilots').catch(() => []),
    ]).then(([vehicles, batteries, controllers, docks, pilotsData]) => {
      const toArr = (d, key) => Array.isArray(d) ? d : d[key] || d.items || []
      setEntityLists({
        vehicle: toArr(vehicles, 'vehicles'),
        battery: toArr(batteries, 'batteries'),
        controller: toArr(controllers, 'controllers'),
        dock: toArr(docks, 'docks'),
      })
      setPilots(Array.isArray(pilotsData) ? pilotsData : pilotsData.pilots || [])
    })
  }, [])

  const loadAll = () => {
    setLoading(true)
    Promise.all([
      api.get('/maintenance?upcoming=true').catch(() => []),
      api.get('/maintenance').catch(() => []),
      api.get('/maintenance/schedules?all=true').catch(() => []),
    ]).then(([upcoming, history, sched]) => {
      setUpcomingRecords(upcoming)
      setHistoryRecords(history)
      setSchedules(sched)
    }).finally(() => setLoading(false))
  }

  useEffect(() => { loadAll() }, [])

  const handleSave = async (data) => {
    try {
      if (data.id) {
        await api.patch(`/maintenance/${data.id}`, data)
      } else {
        await api.post('/maintenance', data)
      }
      setModal(null)
      loadAll()
    } catch (err) {
      toast.error(err.message || 'Failed to save maintenance record')
      throw err
    }
  }

  const handleDelete = (id) => {
    requestConfirm({
      title: 'Delete Maintenance Record',
      message: 'Are you sure you want to delete this maintenance record?',
      onConfirm: async () => {
        try {
          await api.delete(`/maintenance/${id}`)
          loadAll()
        } catch (err) {
          toast.error(err.message)
        }
      }
    })
  }

  const handleScheduleSave = async (data) => {
    try {
      if (data.id) {
        await api.patch(`/maintenance/schedules/${data.id}`, data)
      } else {
        await api.post('/maintenance/schedules', data)
      }
      setScheduleModal(null)
      loadAll()
    } catch (err) {
      toast.error(err.message || 'Failed to save schedule')
      throw err
    }
  }

  const handleScheduleDelete = (id) => {
    requestConfirm({
      title: 'Delete Schedule',
      message: 'Are you sure you want to delete this maintenance schedule?',
      onConfirm: async () => {
        try {
          await api.delete(`/maintenance/schedules/${id}`)
          loadAll()
        } catch (err) {
          toast.error(err.message)
        }
      }
    })
  }

  const handleScheduleComplete = async (id) => {
    try {
      await api.post(`/maintenance/schedules/${id}/complete`)
      loadAll()
    } catch (err) {
      toast.error(err.message)
    }
  }

  const filterRecords = (recs) => recs.filter(r =>
    `${r.description || ''} ${r.entity_type || ''} ${r.performed_by || ''} ${r.maintenance_type || ''} ${resolveEntityName(r.entity_type, r.entity_id, entityLists)}`
      .toLowerCase().includes(search.toLowerCase())
  )

  const filteredUpcoming = filterRecords(upcomingRecords)
  const filteredHistory = filterRecords(historyRecords)
  const filteredSchedules = schedules.filter(s =>
    `${s.name || ''} ${s.entity_type || ''} ${s.frequency || ''} ${s.assigned_to_name || ''}`
      .toLowerCase().includes(search.toLowerCase())
  )
  const displayedUpcoming = showAllUpcoming ? filteredUpcoming : filteredUpcoming.slice(0, 10)

  const TYPE_COLORS = {
    scheduled: 'bg-blue-500/15 text-blue-400',
    unscheduled: 'bg-amber-500/15 text-amber-400',
    inspection: 'bg-emerald-500/15 text-emerald-400',
  }

  if (loading) {
    return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
  }

  return (
    <div className="space-y-6">
      {/* Top Controls */}
      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search maintenance..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
        <div className="flex-1" />
        <button
          onClick={() => api.download('/export/maintenance/csv')}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90"
        >
          <Download className="w-4 h-4" /> Export CSV
        </button>
        {isPilot && (
          <button onClick={() => setModal('add')} className="flex items-center gap-2 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90">
            <Plus className="w-4 h-4" /> Add Maintenance
          </button>
        )}
      </div>

      {/* ── Upcoming Section ────────────────────────────────────────────── */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CalendarClock className="w-4 h-4 text-primary" />
            <h3 className="font-semibold text-foreground">Upcoming</h3>
            <span className="text-xs text-muted-foreground">({filteredUpcoming.length})</span>
          </div>
        </div>
        {displayedUpcoming.length > 0 ? (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 p-4">
              {displayedUpcoming.map(r => {
                const dueDate = r.next_due_date ? new Date(r.next_due_date) : null
                const now = new Date()
                const daysUntil = dueDate ? Math.ceil((dueDate - now) / (1000 * 60 * 60 * 24)) : null
                const urgencyColor = daysUntil !== null
                  ? daysUntil <= 0 ? 'text-red-400' : daysUntil <= 7 ? 'text-amber-400' : 'text-emerald-400'
                  : 'text-muted-foreground'

                return (
                  <div key={r.id} className="bg-secondary/30 border border-border/50 rounded-lg p-3">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-2">
                        <Wrench className="w-4 h-4 text-primary" />
                        <h4 className="font-medium text-foreground text-sm">{r.description || 'Maintenance'}</h4>
                      </div>
                      {isPilot && (
                        <button onClick={() => handleDelete(r.id)} className="p-1 text-muted-foreground hover:text-destructive">
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                    <div className="mt-2 space-y-1 text-xs text-muted-foreground">
                      <p>Entity: <EntityRef entityType={r.entity_type} entityId={r.entity_id} entityLists={entityLists} /></p>
                      <p>Type: <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${TYPE_COLORS[r.maintenance_type] || 'bg-zinc-500/15 text-zinc-400'}`}>{r.maintenance_type}</span></p>
                      <p>Next Due: <span className={`font-medium ${urgencyColor}`}>{r.next_due_date || 'N/A'}</span>
                        {daysUntil !== null && <span className={`ml-1 ${urgencyColor}`}>({daysUntil <= 0 ? 'Overdue' : `${daysUntil}d`})</span>}
                      </p>
                      {r.performed_by && <p>By: <span className="text-foreground">{r.performed_by}</span></p>}
                    </div>
                  </div>
                )
              })}
            </div>
            {filteredUpcoming.length > 10 && !showAllUpcoming && (
              <div className="px-4 pb-3">
                <button onClick={() => setShowAllUpcoming(true)} className="text-sm text-primary hover:opacity-80 font-medium">
                  Show all ({filteredUpcoming.length})
                </button>
              </div>
            )}
            {showAllUpcoming && filteredUpcoming.length > 10 && (
              <div className="px-4 pb-3">
                <button onClick={() => setShowAllUpcoming(false)} className="text-sm text-primary hover:opacity-80 font-medium">
                  Show less
                </button>
              </div>
            )}
          </>
        ) : (
          <div className="px-4 py-8 text-center text-muted-foreground text-sm">No upcoming maintenance</div>
        )}
      </div>

      {/* ── History Section ─────────────────────────────────────────────── */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <div className="flex items-center gap-2">
            <History className="w-4 h-4 text-primary" />
            <h3 className="font-semibold text-foreground">History</h3>
            <span className="text-xs text-muted-foreground">({filteredHistory.length})</span>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/30">
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Description</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Entity</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Type</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Performed By</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Date</th>
                <th className="text-right px-4 py-3 font-medium text-muted-foreground">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredHistory.map(r => (
                <tr key={r.id} className="border-b border-border/50 hover:bg-accent/30 transition-colors">
                  <td className="px-4 py-3 text-foreground">{r.description || '\u2014'}</td>
                  <td className="px-4 py-3">
                    <EntityRef entityType={r.entity_type} entityId={r.entity_id} entityLists={entityLists} />
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${TYPE_COLORS[r.maintenance_type] || 'bg-zinc-500/15 text-zinc-400'}`}>
                      {r.maintenance_type}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{r.performed_by || '\u2014'}</td>
                  <td className="px-4 py-3 text-muted-foreground">{r.performed_date || '\u2014'}</td>
                  <td className="px-4 py-3 text-right">
                    {isPilot && (
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => setModal(r)}
                          className="p-1.5 text-muted-foreground hover:text-foreground rounded-lg hover:bg-accent"
                          title="Edit"
                        >
                          <Edit className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleDelete(r.id)}
                          className="p-1.5 text-muted-foreground hover:text-destructive rounded-lg hover:bg-destructive/10"
                          title="Delete"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {filteredHistory.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-12 text-center text-muted-foreground">No maintenance records found</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Schedules Section ───────────────────────────────────────────── */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-primary" />
            <h3 className="font-semibold text-foreground">Schedules</h3>
            <span className="text-xs text-muted-foreground">({filteredSchedules.length})</span>
          </div>
          {isSupervisor && (
            <button onClick={() => setScheduleModal('add')} className="flex items-center gap-2 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-medium hover:opacity-90">
              <Plus className="w-3.5 h-3.5" /> Add Schedule
            </button>
          )}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/30">
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Name</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Entity</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Frequency</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Assigned To</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Last Completed</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Next Due</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Status</th>
                <th className="text-right px-4 py-3 font-medium text-muted-foreground">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredSchedules.map(s => {
                const dueDate = s.next_due ? new Date(s.next_due) : null
                const now = new Date()
                const daysUntil = dueDate ? Math.ceil((dueDate - now) / (1000 * 60 * 60 * 24)) : null
                const urgencyColor = daysUntil !== null
                  ? daysUntil <= 0 ? 'text-red-400' : daysUntil <= 7 ? 'text-amber-400' : 'text-emerald-400'
                  : 'text-muted-foreground'

                return (
                  <tr key={s.id} className="border-b border-border/50 hover:bg-accent/30 transition-colors">
                    <td className="px-4 py-3 text-foreground font-medium">{s.name}</td>
                    <td className="px-4 py-3 text-muted-foreground capitalize">
                      {s.entity_type}{s.entity_id ? ` #${s.entity_id}` : ''}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${FREQUENCY_COLORS[s.frequency] || 'bg-zinc-500/15 text-zinc-400'}`}>
                        {s.frequency}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground hidden md:table-cell">{s.assigned_to_name || '\u2014'}</td>
                    <td className="px-4 py-3 text-muted-foreground hidden md:table-cell">{s.last_completed || '\u2014'}</td>
                    <td className="px-4 py-3">
                      <span className={urgencyColor}>{s.next_due || '\u2014'}</span>
                      {daysUntil !== null && (
                        <span className={`ml-1 text-xs ${urgencyColor}`}>
                          ({daysUntil <= 0 ? 'Overdue' : `${daysUntil}d`})
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${s.is_active ? 'bg-emerald-500/15 text-emerald-400' : 'bg-zinc-500/15 text-zinc-400'}`}>
                        {s.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      {isSupervisor && (
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => handleScheduleComplete(s.id)}
                            title="Mark Complete"
                            className="p-1.5 text-muted-foreground hover:text-emerald-400 rounded-lg hover:bg-emerald-500/10"
                          >
                            <CheckCircle className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => setScheduleModal(s)}
                            className="p-1.5 text-muted-foreground hover:text-foreground rounded-lg hover:bg-accent"
                          >
                            <Edit className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => handleScheduleDelete(s.id)}
                            className="p-1.5 text-muted-foreground hover:text-destructive rounded-lg hover:bg-destructive/10"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                )
              })}
              {filteredSchedules.length === 0 && (
                <tr><td colSpan={8} className="px-4 py-12 text-center text-muted-foreground">No maintenance schedules found</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {modal && (
        <MaintenanceModal
          record={modal === 'add' ? null : modal}
          onSave={handleSave}
          onClose={() => setModal(null)}
          entityLists={entityLists}
          pilots={pilots}
        />
      )}

      {scheduleModal && (
        <ScheduleModal
          schedule={scheduleModal === 'add' ? null : scheduleModal}
          onSave={handleScheduleSave}
          onClose={() => setScheduleModal(null)}
        />
      )}
      <ConfirmDialog {...confirmProps} />
    </div>
  )
}
