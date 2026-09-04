import { useState, useEffect, useMemo, useRef } from 'react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { formatDuration, normalizeDateValue } from '@/lib/utils'
import { sortByName, sortVehicles, sortPilotsActiveFirst, vehicleDisplayName } from '@/lib/formatters'
import { Plus, Search, CheckCircle, ChevronUp, ChevronDown, Pencil, X, Check, Download, Loader2, Copy } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { Modal } from '@/components/ui/Modal'

function FlightModal({ pilots, vehicles, purposes, batteries, sensors, attachments, onSave, onClose, initial }) {
  // When `initial` is provided (Duplicate), pre-fill the reusable fields and
  // leave the flight-specific ones (date, times, duration) blank.
  const [form, setForm] = useState(() => ({
    pilot_id: initial?.pilot_id ? String(initial.pilot_id) : '',
    vehicle_id: initial?.vehicle_id ? String(initial.vehicle_id) : '',
    date: '', takeoff_time: '', landing_time: '',
    duration_seconds: '',
    purpose: initial?.purpose || '',
    takeoff_address: initial?.takeoff_address || '',
    case_number: '',
    notes: '',
    battery_serial: initial?.battery_serial || '',
    sensor_package: initial?.sensor_package || '',
    attachment_top: initial?.attachment_top || '',
    attachment_bottom: initial?.attachment_bottom || '',
    attachment_left: initial?.attachment_left || '',
    attachment_right: initial?.attachment_right || '',
    carrier: initial?.carrier || '',
  }))
  const [saving, setSaving] = useState(false)
  const [preflightWarnings, setPreflightWarnings] = useState([])

  // Fetch non-blocking pre-flight warnings (overdue maintenance, expired
  // registration, non-active status) whenever the selected vehicle changes.
  useEffect(() => {
    if (!form.vehicle_id) { setPreflightWarnings([]); return }
    let active = true
    api.get(`/flights/preflight-check?vehicle_id=${form.vehicle_id}`)
      .then(r => { if (active) setPreflightWarnings(r.warnings || []) })
      .catch(() => { if (active) setPreflightWarnings([]) })
    return () => { active = false }
  }, [form.vehicle_id])

  const handleSubmit = async (e) => {
    e.preventDefault()
    const data = { ...form }
    if (data.pilot_id) data.pilot_id = Number.parseInt(data.pilot_id, 10)
    else delete data.pilot_id
    if (data.vehicle_id) data.vehicle_id = Number.parseInt(data.vehicle_id, 10)
    else delete data.vehicle_id
    if (data.duration_seconds) data.duration_seconds = Number.parseInt(data.duration_seconds, 10)
    else delete data.duration_seconds
    Object.keys(data).forEach(k => { if (data[k] === '') delete data[k] })
    setSaving(true)
    try { await onSave(data) } finally { setSaving(false) }
  }

  return (
    <Modal open onClose={onClose} title="Add Flight">
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="pilot" className="block text-sm font-medium text-foreground mb-1">Pilot</label>
              <select id="pilot" value={form.pilot_id} onChange={e => setForm({...form, pilot_id: e.target.value})}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
                <option value="">Select pilot...</option>
                {sortPilotsActiveFirst(pilots).map(p => <option key={p.id} value={p.id}>{p.full_name}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="vehicle" className="block text-sm font-medium text-foreground mb-1">Vehicle</label>
              <select id="vehicle" value={form.vehicle_id} onChange={e => setForm({...form, vehicle_id: e.target.value})}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
                <option value="">Select vehicle...</option>
                {sortVehicles(vehicles).map(v => <option key={v.id} value={v.id}>{vehicleDisplayName(v)}</option>)}
              </select>
            </div>
          </div>
          {preflightWarnings.length > 0 && (
            <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2">
              <p className="text-xs font-semibold text-amber-400 mb-1">Pre-flight warnings for this vehicle</p>
              <ul className="list-disc list-inside space-y-0.5">
                {preflightWarnings.map(w => <li key={w} className="text-xs text-amber-300">{w}</li>)}
              </ul>
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="date" className="block text-sm font-medium text-foreground mb-1">Date</label>
              <input id="date" type="date" value={form.date} onChange={e => setForm({...form, date: e.target.value})}
                onBlur={e => { const n = normalizeDateValue(e.target.value); if (n !== e.target.value) setForm(prev => ({...prev, date: n})) }}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
            <div>
              <label htmlFor="duration-seconds" className="block text-sm font-medium text-foreground mb-1">Duration (seconds)</label>
              <input id="duration-seconds" type="number" value={form.duration_seconds} onChange={e => setForm({...form, duration_seconds: e.target.value})}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
          </div>
          <div>
            <label htmlFor="purpose" className="block text-sm font-medium text-foreground mb-1">Purpose</label>
            <select id="purpose" value={form.purpose} onChange={e => setForm({...form, purpose: e.target.value})}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
              <option value="">Select purpose...</option>
              {sortByName(purposes, 'name').map(p => <option key={p.id} value={p.name}>{p.name}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="takeoff-address" className="block text-sm font-medium text-foreground mb-1">Takeoff Address</label>
            <input id="takeoff-address" type="text" value={form.takeoff_address} onChange={e => setForm({...form, takeoff_address: e.target.value})}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
          </div>
          <div>
            <label htmlFor="case-number" className="block text-sm font-medium text-foreground mb-1">Case Number</label>
            <input id="case-number" type="text" value={form.case_number} onChange={e => setForm({...form, case_number: e.target.value})}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="battery" className="block text-sm font-medium text-foreground mb-1">Battery</label>
              <input id="battery" list="battery-list" value={form.battery_serial} onChange={e => setForm({...form, battery_serial: e.target.value})}
                onFocus={e => { e.target.showPicker?.() }}
                placeholder="Select or type..."
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              <datalist id="battery-list">
                {(batteries || []).map(b => <option key={b.id} value={b.serial_number}>{b.nickname || b.serial_number}</option>)}
              </datalist>
            </div>
            <div>
              <label htmlFor="sensor-package" className="block text-sm font-medium text-foreground mb-1">Sensor Package</label>
              <input id="sensor-package" list="sensor-list" value={form.sensor_package} onChange={e => setForm({...form, sensor_package: e.target.value})}
                onFocus={e => { e.target.showPicker?.() }}
                placeholder="Select or type..."
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              <datalist id="sensor-list">
                {(sensors || []).map(s => <option key={s.id} value={s.serial_number}>{s.name || s.serial_number}</option>)}
              </datalist>
            </div>
            <div>
              <label htmlFor="attachment-top" className="block text-sm font-medium text-foreground mb-1">Attachment (Top)</label>
              <input id="attachment-top" list="attach-list" value={form.attachment_top} onChange={e => setForm({...form, attachment_top: e.target.value})}
                onFocus={e => { e.target.showPicker?.() }}
                placeholder="Select or type..."
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              <datalist id="attach-list">
                {(attachments || []).map(a => <option key={a.id} value={a.serial_number}>{a.name || a.serial_number}</option>)}
              </datalist>
            </div>
            <div>
              <label htmlFor="attachment-bottom" className="block text-sm font-medium text-foreground mb-1">Attachment (Bottom)</label>
              <input id="attachment-bottom" list="attach-list" value={form.attachment_bottom} onChange={e => setForm({...form, attachment_bottom: e.target.value})}
                onFocus={e => { e.target.showPicker?.() }}
                placeholder="Select or type..."
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
            <div>
              <label htmlFor="attachment-left" className="block text-sm font-medium text-foreground mb-1">Attachment (Left)</label>
              <input id="attachment-left" list="attach-list" value={form.attachment_left} onChange={e => setForm({...form, attachment_left: e.target.value})}
                onFocus={e => { e.target.showPicker?.() }}
                placeholder="Select or type..."
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
            <div>
              <label htmlFor="attachment-right" className="block text-sm font-medium text-foreground mb-1">Attachment (Right)</label>
              <input id="attachment-right" list="attach-list" value={form.attachment_right} onChange={e => setForm({...form, attachment_right: e.target.value})}
                onFocus={e => { e.target.showPicker?.() }}
                placeholder="Select or type..."
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
          </div>
          <div>
            <label htmlFor="carrier" className="block text-sm font-medium text-foreground mb-1">Carrier(s)</label>
            <input id="carrier" type="text" value={form.carrier} onChange={e => setForm({...form, carrier: e.target.value})}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
          </div>
          <div className="flex gap-2 pt-2">
            <button type="submit" disabled={saving} className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2">{saving ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Add Flight'}</button>
            <button type="button" onClick={onClose} className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm">Cancel</button>
          </div>
        </form>
    </Modal>
  )
}

export default function FlightsPage() {
  const [flights, setFlights] = useState([])
  const [pilots, setPilots] = useState([])
  const [vehicles, setVehicles] = useState([])
  const [purposes, setPurposes] = useState([])
  const [batteries, setBatteries] = useState([])
  const [sensors, setSensors] = useState([])
  const [attachments, setAttachments] = useState([])
  const [search, setSearch] = useState('')
  const [modal, setModal] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [sortKey, setSortKey] = useState('date')
  const [sortDir, setSortDir] = useState('desc')
  const { isPilot, isSupervisor } = useAuth()
  const toast = useToast()

  // Status filter: 'all' | 'needs_review' | 'reviewed'
  const [statusFilter, setStatusFilter] = useState('all')

  // Date range and dropdown filters
  const [filterDateFrom, setFilterDateFrom] = useState('')
  const [filterDateTo, setFilterDateTo] = useState('')
  const [filterPilotId, setFilterPilotId] = useState('')
  const [filterVehicleId, setFilterVehicleId] = useState('')
  const [filterPurpose, setFilterPurpose] = useState(() => {
    try { return new URLSearchParams(globalThis.location.search).get('purpose') || '' } catch { return '' }
  })

  // Pagination state
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [total, setTotal] = useState(0)
  const [reviewCount, setReviewCount] = useState(0)

  // Inline editing state
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState({})
  const [showBulkApproveConfirm, setShowBulkApproveConfirm] = useState(false)
  // Bulk selection (supervisor-only): a Set of selected flight ids + action state.
  const [selectedIds, setSelectedIds] = useState(() => new Set())
  const [bulkBusy, setBulkBusy] = useState(false)
  const [showBulkDeleteConfirm, setShowBulkDeleteConfirm] = useState(false)

  const toggleSort = (key) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  const abortRef = useRef(null)

  const load = () => {
    // Abort any in-flight load and tag this one, so a slow earlier request can't
    // resolve after a newer filter change and overwrite the table with stale data.
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    const { signal } = controller
    setSelectedIds(new Set())  // never act on rows hidden by a filter/page change

    const qp = new URLSearchParams()
    if (filterDateFrom) qp.set('date_from', filterDateFrom)
    if (filterDateTo) qp.set('date_to', filterDateTo)
    if (filterPilotId) qp.set('pilot_id', filterPilotId)
    if (filterVehicleId) qp.set('vehicle_id', filterVehicleId)
    if (filterPurpose) qp.set('purpose', filterPurpose)
    if (statusFilter && statusFilter !== 'all') qp.set('review_status', statusFilter)
    qp.set('page', page)
    qp.set('per_page', 100)
    const qs = qp.toString()
    const path = qs ? `/flights?${qs}` : '/flights'

    Promise.all([
      api.get(path, { signal }),
      api.get('/pilots', { signal }),
      api.get('/vehicles', { signal }),
      api.get('/flights/purposes/list', { signal }),
      api.get('/flights/count?review_status=needs_review', { signal }),
      api.get('/batteries', { signal }).catch(() => []),
      api.get('/sensors', { signal }).catch(() => []),
      api.get('/attachments', { signal }).catch(() => []),
    ]).then(([data, p, v, pu, rc, bats, sens, atts]) => {
      // Guard against a request that resolved just before being superseded: only
      // the most recent load is allowed to write state.
      if (abortRef.current !== controller) return
      setFlights(data.flights || [])
      setTotal(data.total || 0)
      setTotalPages(data.total_pages || 1)
      setPilots(p); setVehicles(v); setPurposes(pu); setBatteries(bats); setSensors(sens); setAttachments(atts)
      setReviewCount(rc.count || 0)
    }).catch(err => {
      // A superseded load rejects with AbortError; ignore it (a newer load owns the UI).
      if (err.name === 'AbortError' || abortRef.current !== controller) return
      setError(err.message)
    }).finally(() => {
      if (abortRef.current === controller) setLoading(false)
    })
  }

  useEffect(() => { load() }, [filterDateFrom, filterDateTo, filterPilotId, filterVehicleId, filterPurpose, statusFilter, page])

  // Client-side search hides rows; clearing selection on search change keeps bulk
  // ops from acting on rows you can no longer see.
  useEffect(() => setSelectedIds(new Set()), [search])

  const handleSave = async (data) => {
    try {
      await api.post('/flights', data)
      setModal(false)
      load()
    } catch (err) { toast.error(err.message) }
  }

  const handleBulkApprove = async (ids) => {
    try {
      await api.post('/flights/bulk-update', {
        flight_ids: ids, review_status: 'reviewed', pilot_confirmed: true
      })
      load()
    } catch (err) { toast.error(err.message) }
  }

  const startEditing = (flight) => {
    setEditingId(flight.id)
    setEditForm({
      pilot_id: flight.pilot_id || '',
      purpose: flight.purpose || '',
      date: flight.date || '',
      duration_seconds: flight.duration_seconds || '',
      review_status: flight.review_status || 'needs_review',
    })
  }

  const cancelEditing = () => {
    setEditingId(null)
    setEditForm({})
  }

  const saveEditing = async () => {
    try {
      const data = { ...editForm }
      if (data.pilot_id) data.pilot_id = Number.parseInt(data.pilot_id, 10)
      else data.pilot_id = null
      if (data.duration_seconds) data.duration_seconds = Number.parseInt(data.duration_seconds, 10)
      else delete data.duration_seconds
      await api.patch(`/flights/${editingId}`, data)
      setEditingId(null)
      setEditForm({})
      load()
    } catch (err) { toast.error(err.message) }
  }

  const handleExport = async () => {
    try {
      await api.download('/export/flights/csv')
    } catch (err) { toast.error(err.message) }
  }

  const filtered = useMemo(() => {
    // Status filter is now applied server-side via the API query param
    // Apply text search
    let list = flights.filter(f =>
      `${f.pilot_name || ''} ${f.vehicle_name || ''} ${f.purpose || ''} ${f.takeoff_address || ''}`
        .toLowerCase().includes(search.toLowerCase())
    )

    return [...list].sort((a, b) => {
      let aVal, bVal
      if (sortKey === 'date') {
        aVal = a.date || a.takeoff_time || ''
        bVal = b.date || b.takeoff_time || ''
      } else if (sortKey === 'pilot_name') {
        aVal = (a.pilot_name || '').toLowerCase()
        bVal = (b.pilot_name || '').toLowerCase()
      } else if (sortKey === 'vehicle_name') {
        aVal = (a.vehicle_name || '').toLowerCase()
        bVal = (b.vehicle_name || '').toLowerCase()
      } else if (sortKey === 'purpose') {
        aVal = (a.purpose || '').toLowerCase()
        bVal = (b.purpose || '').toLowerCase()
      } else if (sortKey === 'duration_seconds') {
        aVal = a.duration_seconds || 0
        bVal = b.duration_seconds || 0
      } else if (sortKey === 'review_status') {
        aVal = (a.review_status || '').toLowerCase()
        bVal = (b.review_status || '').toLowerCase()
      } else {
        aVal = (a[sortKey] || '').toString().toLowerCase()
        bVal = (b[sortKey] || '').toString().toLowerCase()
      }
      if (aVal < bVal) return sortDir === 'asc' ? -1 : 1
      if (aVal > bVal) return sortDir === 'asc' ? 1 : -1
      return 0
    })
  }, [flights, search, sortKey, sortDir])

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>

  // Approve button acts on the visible page (after search), so base it on the
  // `filtered` set rather than the unfiltered flights list.
  const needsReview = filtered.filter(f => f.review_status === 'needs_review')
  const needsReviewCount = reviewCount

  // Bulk selection helpers (supervisor-only). Selection clears on every load()
  // (filter/page change or after an op), so we never act on rows you can't see.
  const toggleRow = (id) => setSelectedIds(prev => {
    const next = new Set(prev)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  })
  const toggleSelectAll = () => setSelectedIds(prev => (
    filtered.length > 0 && filtered.every(f => prev.has(f.id)) ? new Set() : new Set(filtered.map(f => f.id))
  ))
  const runBulkUpdate = async (body) => {
    setBulkBusy(true)
    try {
      await api.post('/flights/bulk-update', { flight_ids: [...selectedIds], ...body })
      load()
    } catch (err) { toast.error(err.message) } finally { setBulkBusy(false) }
  }
  const runBulkDelete = async () => {
    setBulkBusy(true)
    try {
      await api.post('/flights/bulk-delete', { flight_ids: [...selectedIds] }, { timeout: 120000 })
      load()
    } catch (err) { toast.error(err.message) } finally { setBulkBusy(false) }
  }

  const selectCls = "px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
  const inputCls = "px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"

  return (
    <div className="space-y-4">
      {error && <div className="bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg p-4 mb-4">{error}</div>}
      {/* Status filter toggle */}
      <div className="flex items-center gap-2">
        {['all', 'needs_review', 'reviewed'].map(s => (
          <button key={s} onClick={() => { setStatusFilter(s); setPage(1) }}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              statusFilter === s
                ? 'bg-primary text-primary-foreground'
                : 'bg-secondary text-secondary-foreground hover:bg-accent/30'
            }`}>
            {{ all: 'All', needs_review: `Needs Review (${needsReviewCount})`, reviewed: 'Reviewed' }[s]}
          </button>
        ))}
      </div>

      {/* Filters row */}
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor="date-from" className="block text-xs text-muted-foreground mb-1">Date From</label>
          <input id="date-from" type="date" value={filterDateFrom} onChange={e => setFilterDateFrom(e.target.value)}
            onBlur={e => { const n = normalizeDateValue(e.target.value); if (n !== e.target.value) { e.target.value = n; setFilterDateFrom(n) } }} className={inputCls} />
        </div>
        <div>
          <label htmlFor="date-to" className="block text-xs text-muted-foreground mb-1">Date To</label>
          <input id="date-to" type="date" value={filterDateTo} onChange={e => setFilterDateTo(e.target.value)}
            onBlur={e => { const n = normalizeDateValue(e.target.value); if (n !== e.target.value) { e.target.value = n; setFilterDateTo(n) } }} className={inputCls} />
        </div>
        <div>
          <label htmlFor="pilot-1" className="block text-xs text-muted-foreground mb-1">Pilot</label>
          <select id="pilot-1" value={filterPilotId} onChange={e => setFilterPilotId(e.target.value)} className={selectCls}>
            <option value="">All Pilots</option>
            {sortPilotsActiveFirst(pilots).map(p => <option key={p.id} value={p.id}>{p.full_name}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="vehicle-1" className="block text-xs text-muted-foreground mb-1">Vehicle</label>
          <select id="vehicle-1" value={filterVehicleId} onChange={e => setFilterVehicleId(e.target.value)} className={selectCls}>
            <option value="">All Vehicles</option>
            {sortVehicles(vehicles).map(v => <option key={v.id} value={v.id}>{vehicleDisplayName(v)}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="purpose-1" className="block text-xs text-muted-foreground mb-1">Purpose</label>
          <select id="purpose-1" value={filterPurpose} onChange={e => setFilterPurpose(e.target.value)} className={selectCls}>
            <option value="">All Purposes</option>
            <option value="__none__">No Purpose</option>
            {sortByName(purposes, 'name').map(p => <option key={p.id} value={p.name}>{p.name}</option>)}
          </select>
        </div>
      </div>

      {/* Search + actions */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input type="text" placeholder="Search flights..." value={search} onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
        </div>
        <div className="flex gap-2">
          <button onClick={handleExport}
            className="flex items-center gap-2 px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm font-medium hover:opacity-90">
            <Download className="w-4 h-4" /> Export CSV
          </button>
          {needsReview.length > 0 && isSupervisor && (
            <button
              onClick={() => setShowBulkApproveConfirm(true)}
              className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:opacity-90"
            >
              <CheckCircle className="w-4 h-4" /> Approve Page ({needsReview.length})
            </button>
          )}
          {isPilot && (
            <button onClick={() => setModal(true)} className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90">
              <Plus className="w-4 h-4" /> Add Flight
            </button>
          )}
        </div>
      </div>

      {isSupervisor && selectedIds.size > 0 && (
        <div className="flex items-center gap-3 flex-wrap bg-primary/10 border border-primary/30 rounded-lg px-4 py-2">
          <span className="text-sm font-medium text-foreground">{selectedIds.size} selected</span>
          <select disabled={bulkBusy} value="" aria-label="Reassign pilot for selected flights"
            onChange={e => { if (e.target.value) runBulkUpdate({ pilot_id: Number.parseInt(e.target.value, 10) }) }}
            className="px-2 py-1 bg-secondary border border-border rounded text-foreground text-sm">
            <option value="">Reassign pilot…</option>
            {sortPilotsActiveFirst(pilots).map(p => <option key={p.id} value={p.id}>{p.full_name}</option>)}
          </select>
          <select disabled={bulkBusy} value="" aria-label="Set purpose for selected flights"
            onChange={e => { if (e.target.value) runBulkUpdate({ purpose: e.target.value }) }}
            className="px-2 py-1 bg-secondary border border-border rounded text-foreground text-sm">
            <option value="">Set purpose…</option>
            {sortByName(purposes, 'name').map(p => <option key={p.id} value={p.name}>{p.name}</option>)}
          </select>
          <button disabled={bulkBusy} onClick={() => runBulkUpdate({ review_status: 'reviewed', pilot_confirmed: true })}
            className="px-3 py-1 bg-emerald-600 text-white rounded text-sm font-medium hover:opacity-90 disabled:opacity-50">Mark reviewed</button>
          <button disabled={bulkBusy} onClick={() => setShowBulkDeleteConfirm(true)}
            className="px-3 py-1 bg-destructive text-destructive-foreground rounded text-sm font-medium hover:opacity-90 disabled:opacity-50">Delete</button>
          <button disabled={bulkBusy} onClick={() => setSelectedIds(new Set())} className="ml-auto text-sm text-muted-foreground hover:text-foreground">Clear</button>
        </div>
      )}

      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/30">
              {isSupervisor && (
                <th className="px-4 py-3 w-10">
                  <input type="checkbox" aria-label="Select all flights on this page"
                    checked={filtered.length > 0 && filtered.every(f => selectedIds.has(f.id))}
                    onChange={toggleSelectAll} className="rounded border-border" />
                </th>
              )}
              <th className="text-left px-4 py-3 font-medium text-muted-foreground">Flight ID</th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground cursor-pointer hover:text-foreground select-none" onClick={() => toggleSort('date')} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); (() => toggleSort('date'))() } }} tabIndex={0}>
                Date{sortKey === 'date' && (sortDir === 'asc' ? <ChevronUp className="w-3 h-3 inline ml-1" /> : <ChevronDown className="w-3 h-3 inline ml-1" />)}
              </th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground cursor-pointer hover:text-foreground select-none" onClick={() => toggleSort('pilot_name')} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); (() => toggleSort('pilot_name'))() } }} tabIndex={0}>
                Pilot{sortKey === 'pilot_name' && (sortDir === 'asc' ? <ChevronUp className="w-3 h-3 inline ml-1" /> : <ChevronDown className="w-3 h-3 inline ml-1" />)}
              </th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground cursor-pointer hover:text-foreground select-none hidden md:table-cell" onClick={() => toggleSort('vehicle_name')} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); (() => toggleSort('vehicle_name'))() } }} tabIndex={0}>
                Vehicle{sortKey === 'vehicle_name' && (sortDir === 'asc' ? <ChevronUp className="w-3 h-3 inline ml-1" /> : <ChevronDown className="w-3 h-3 inline ml-1" />)}
              </th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground cursor-pointer hover:text-foreground select-none hidden md:table-cell" onClick={() => toggleSort('purpose')} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); (() => toggleSort('purpose'))() } }} tabIndex={0}>
                Purpose{sortKey === 'purpose' && (sortDir === 'asc' ? <ChevronUp className="w-3 h-3 inline ml-1" /> : <ChevronDown className="w-3 h-3 inline ml-1" />)}
              </th>
              <th className="text-right px-4 py-3 font-medium text-muted-foreground cursor-pointer hover:text-foreground select-none" onClick={() => toggleSort('duration_seconds')} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); (() => toggleSort('duration_seconds'))() } }} tabIndex={0}>
                Duration{sortKey === 'duration_seconds' && (sortDir === 'asc' ? <ChevronUp className="w-3 h-3 inline ml-1" /> : <ChevronDown className="w-3 h-3 inline ml-1" />)}
              </th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">Location</th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground cursor-pointer hover:text-foreground select-none" onClick={() => toggleSort('review_status')} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); (() => toggleSort('review_status'))() } }} tabIndex={0}>
                Status{sortKey === 'review_status' && (sortDir === 'asc' ? <ChevronUp className="w-3 h-3 inline ml-1" /> : <ChevronDown className="w-3 h-3 inline ml-1" />)}
              </th>
              <th className="text-right px-4 py-3 font-medium text-muted-foreground w-20">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(f => editingId === f.id ? (
              <FlightEditRow key={f.id} f={f} editForm={editForm} setEditForm={setEditForm}
                pilots={pilots} purposes={purposes} onSave={saveEditing} onCancel={cancelEditing} selectable={isSupervisor} />
            ) : (
              <tr key={f.id} className="border-b border-border/50 hover:bg-accent/30 transition-colors">
                {isSupervisor && (
                  <td className="px-4 py-3">
                    <input type="checkbox" aria-label={`Select flight ${f.external_id || f.id}`}
                      checked={selectedIds.has(f.id)} onChange={() => toggleRow(f.id)} className="rounded border-border" />
                  </td>
                )}
                <td className="px-4 py-3 text-xs font-mono" title={f.external_id || ''}>
                  <Link to={`/flights/${f.id}`} className="text-primary hover:underline">{f.external_id ? f.external_id.slice(0, 8) : `#${f.id}`}</Link>
                </td>
                <td className="px-4 py-3 text-foreground">{f.date || '—'}</td>
                <td className="px-4 py-3 text-foreground">
                  {f.pilot_id ? <Link to={`/pilots/${f.pilot_id}`} className="text-primary hover:underline">{f.pilot_name}</Link> : (f.pilot_name || <span className="text-amber-400">Unassigned</span>)}
                </td>
                <td className="px-4 py-3 text-foreground hidden md:table-cell">
                  {f.vehicle_id ? <Link to={`/fleet/vehicles/${f.vehicle_id}`} className="text-primary hover:underline">{f.vehicle_name}</Link> : (f.vehicle_name || '—')}
                </td>
                <td className="px-4 py-3 text-foreground hidden md:table-cell">{f.purpose || <span className="text-amber-400">None</span>}</td>
                <td className="px-4 py-3 text-right text-foreground">{formatDuration(f.duration_seconds)}</td>
                <td className="px-4 py-3 text-foreground truncate max-w-[200px] hidden lg:table-cell">{f.takeoff_address || '—'}</td>
                <td className="px-4 py-3">
                  <div className="flex flex-col gap-0.5 items-start">
                    {(() => {
                      const badgeCls = `inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                        f.review_status === 'needs_review' ? 'bg-amber-500/15 text-amber-400' : 'bg-emerald-500/15 text-emerald-400'
                      }`
                      const label = f.review_status === 'needs_review' ? 'Needs Review' : 'Reviewed'
                      if (isSupervisor) {
                        const next = f.review_status === 'reviewed' ? 'needs_review' : 'reviewed'
                        const nextLabel = next === 'reviewed' ? 'Reviewed' : 'Needs Review'
                        return (
                          <button type="button" onClick={async (e) => { e.stopPropagation(); try { await api.patch(`/flights/${f.id}/review-status`, { review_status: next }); load() } catch (err) { toast.error(err.message) } }}
                            className={`${badgeCls} cursor-pointer hover:brightness-110`} title={`Click to mark ${nextLabel}`}>{label}</button>
                        )
                      }
                      return <span className={badgeCls}>{label}</span>
                    })()}
                    {(() => {
                      if (f.telemetry_synced) {
                        const cls = "text-[10px] leading-none text-emerald-400"
                        return isSupervisor
                          ? <button type="button" onClick={async (e) => { e.stopPropagation(); try { await api.patch(`/flights/${f.id}/telemetry-status`, { telemetry_synced: false }); load() } catch (err) { toast.error(err.message) } }} className={`${cls} cursor-pointer hover:text-emerald-300`} title="Click to mark not synced">Telemetry ✓</button>
                          : <span className={cls}>Telemetry ✓</span>
                      }
                      if (f.external_id) {
                        const cls = "text-[10px] leading-none text-muted-foreground"
                        return isSupervisor
                          ? <button type="button" onClick={async (e) => { e.stopPropagation(); try { await api.patch(`/flights/${f.id}/telemetry-status`, { telemetry_synced: true }); load() } catch (err) { toast.error(err.message) } }} className={`${cls} cursor-pointer hover:text-foreground`} title="Click to mark synced">Telemetry pending</button>
                          : <span className={cls}>Telemetry pending</span>
                      }
                      return null
                    })()}
                  </div>
                </td>
                <td className="px-4 py-3 text-right">
                  {isPilot && (
                    <div className="flex items-center justify-end gap-1">
                      <button onClick={() => setModal({
                        pilot_id: f.pilot_id, vehicle_id: f.vehicle_id, purpose: f.purpose,
                        takeoff_address: f.takeoff_address, battery_serial: f.battery_serial,
                        sensor_package: f.sensor_package, attachment_top: f.attachment_top,
                        attachment_bottom: f.attachment_bottom, attachment_left: f.attachment_left,
                        attachment_right: f.attachment_right, carrier: f.carrier,
                      })} title="Duplicate (same pilot, vehicle, purpose)" aria-label="Duplicate" className="p-1.5 text-muted-foreground hover:text-foreground rounded hover:bg-accent/30">
                        <Copy className="w-4 h-4" />
                      </button>
                      <button onClick={() => startEditing(f)} title="Edit" aria-label="Edit" className="p-1.5 text-muted-foreground hover:text-foreground rounded hover:bg-accent/30">
                        <Pencil className="w-4 h-4" />
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && <tr><td colSpan={isSupervisor ? 10 : 9} className="px-4 py-12 text-center text-muted-foreground">No flights found</td></tr>}
          </tbody>
        </table>
        </div>
        <div className="flex items-center justify-between px-4 py-3 border-t border-border">
          <span className="text-sm text-muted-foreground">
            Showing {total === 0 ? 0 : ((page-1)*100)+1}-{Math.min(page*100, total)} of {total} flights
          </span>
          <div className="flex gap-2">
            <button disabled={page <= 1} onClick={() => setPage(p => p-1)} className="px-3 py-1 text-sm bg-secondary rounded-lg disabled:opacity-40">Previous</button>
            <span className="px-3 py-1 text-sm">Page {page} of {totalPages}</span>
            <button disabled={page >= totalPages} onClick={() => setPage(p => p+1)} className="px-3 py-1 text-sm bg-secondary rounded-lg disabled:opacity-40">Next</button>
          </div>
        </div>
      </div>

      {modal && <FlightModal initial={modal === true ? null : modal} pilots={pilots} vehicles={vehicles} purposes={purposes} batteries={batteries} sensors={sensors} attachments={attachments} onSave={handleSave} onClose={() => setModal(false)} />}

      <ConfirmDialog
        open={showBulkApproveConfirm}
        onClose={() => setShowBulkApproveConfirm(false)}
        onConfirm={() => handleBulkApprove(needsReview.map(f => f.id))}
        title="Approve Page Flights"
        message={`Are you sure you want to approve the ${needsReview.length} flights that need review on this page?`}
        confirmLabel="Approve Page"
        confirmVariant="primary"
      />

      <ConfirmDialog
        open={showBulkDeleteConfirm}
        onClose={() => setShowBulkDeleteConfirm(false)}
        onConfirm={runBulkDelete}
        title="Delete Flights"
        message={`Permanently delete ${selectedIds.size} selected flight(s)? This also removes their telemetry and cannot be undone.`}
        confirmLabel="Delete"
        confirmVariant="danger"
      />
    </div>
  )
}

function FlightEditRow({ f, editForm, setEditForm, pilots, purposes, onSave, onCancel, selectable }) {
  return (
    <tr className="border-b border-border/50 bg-accent/20">
      {selectable && <td className="px-4 py-2" />}
      <td className="px-4 py-2 text-foreground text-xs font-mono" title={f.external_id || ''}>{f.external_id ? f.external_id.slice(0, 8) : '—'}</td>
      <td className="px-4 py-2">
        <input type="date" value={editForm.date} onChange={e => setEditForm({...editForm, date: e.target.value})}
          onBlur={e => { const n = normalizeDateValue(e.target.value); if (n !== e.target.value) setEditForm(prev => ({...prev, date: n})) }}
          className="w-full px-2 py-1 bg-secondary border border-border rounded text-foreground text-sm" />
      </td>
      <td className="px-4 py-2">
        <select value={editForm.pilot_id} onChange={e => setEditForm({...editForm, pilot_id: e.target.value})}
          className="w-full px-2 py-1 bg-secondary border border-border rounded text-foreground text-sm">
          <option value="">Unassigned</option>
          {sortPilotsActiveFirst(pilots).map(p => <option key={p.id} value={p.id}>{p.full_name}</option>)}
        </select>
      </td>
      <td className="px-4 py-2 hidden md:table-cell text-foreground">{f.vehicle_name || '—'}</td>
      <td className="px-4 py-2 hidden md:table-cell">
        <select value={editForm.purpose} onChange={e => setEditForm({...editForm, purpose: e.target.value})}
          className="w-full px-2 py-1 bg-secondary border border-border rounded text-foreground text-sm">
          <option value="">None</option>
          {sortByName(purposes, 'name').map(p => <option key={p.id} value={p.name}>{p.name}</option>)}
        </select>
      </td>
      <td className="px-4 py-2 text-right">
        <input type="number" value={editForm.duration_seconds} onChange={e => setEditForm({...editForm, duration_seconds: e.target.value})}
          className="w-20 px-2 py-1 bg-secondary border border-border rounded text-foreground text-sm text-right" placeholder="sec" />
      </td>
      <td className="px-4 py-2 hidden lg:table-cell text-foreground">{f.takeoff_address || '—'}</td>
      <td className="px-4 py-2">
        <div className="flex flex-col gap-0.5 items-start">
          <button type="button" onClick={() => setEditForm({...editForm, review_status: editForm.review_status === 'reviewed' ? 'needs_review' : 'reviewed'})}
            className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium cursor-pointer ${
              editForm.review_status === 'needs_review' ? 'bg-amber-500/15 text-amber-400' : 'bg-emerald-500/15 text-emerald-400'
            }`}>
            {editForm.review_status === 'needs_review' ? 'Needs Review' : 'Reviewed'}
          </button>
          {f.telemetry_synced && <span className="text-[10px] leading-none text-emerald-400">Telemetry ✓</span>}
          {!f.telemetry_synced && f.external_id && <span className="text-[10px] leading-none text-muted-foreground">Telemetry pending</span>}
        </div>
      </td>
      <td className="px-4 py-2 text-right">
        <div className="flex items-center justify-end gap-1">
          <button onClick={onSave} title="Save" className="p-1.5 text-emerald-400 hover:bg-emerald-500/15 rounded">
            <Check className="w-4 h-4" />
          </button>
          <button onClick={onCancel} title="Cancel" className="p-1.5 text-muted-foreground hover:bg-accent/30 rounded">
            <X className="w-4 h-4" />
          </button>
        </div>
      </td>
    </tr>
  )
}
