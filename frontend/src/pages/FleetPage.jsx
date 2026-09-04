import { useState, useEffect, useMemo, useRef } from 'react'
import { Link } from 'react-router-dom'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { Modal } from '@/components/ui/Modal'
import { useConfirm } from '@/hooks/useConfirm'
import { Plus, Edit, Trash2, Search, Battery, Gamepad2, Warehouse, Cpu, Paperclip, Package, ChevronUp, ChevronDown, Download, Loader2, Merge } from 'lucide-react'
import { QuadcopterIcon } from '@/components/icons/QuadcopterIcon'
import { daysUntil } from '@/lib/utils'

// ─── Generic Equipment Modal ────────────────────────────────────────────────

/**
 * Statuses that take an item out of service, mirroring DECOMMISSIONED_STATUSES
 * in backend/app/services/equipment_lifecycle.py. Note this is NOT the same as
 * "not active": a vehicle grounded for maintenance is still in service, and the
 * incident workflow sets that status automatically, so filtering on
 * status === 'active' would hide aircraft the user very much needs to see.
 */
const DECOMMISSIONED_STATUSES = new Set(['retired', 'damaged'])

const STATUS_FILTERS = [
  { value: 'in_service', label: 'In service' },
  { value: 'decommissioned', label: 'Retired & damaged' },
  { value: 'all', label: 'All statuses' },
]

const isDecommissioned = (item) =>
  DECOMMISSIONED_STATUSES.has((item.status || '').toLowerCase())

function EquipmentModal({ title, record, fields, onSave, onClose, vehicleModels }) {
  const defaults = {}
  fields.forEach(f => { defaults[f.key] = '' })
  const [form, setForm] = useState(record || defaults)
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    const data = { ...form }
    fields.forEach(f => {
      if (f.type === 'number' && data[f.key]) data[f.key] = Number.parseFloat(data[f.key])
      if (data[f.key] === '') delete data[f.key]
    })
    setSaving(true)
    try { await onSave(data) } finally { setSaving(false) }
  }

  return (
    <Modal open onClose={onClose} title={record?.id ? `Edit ${title}` : `Add ${title}`} className="max-w-md max-h-[90vh] overflow-y-auto">
        <form onSubmit={handleSubmit} className="space-y-3">
          {fields.map(f => {
            if (f.type === 'select') {
              return (
                <div key={f.key}>
                  <label htmlFor={`field-${f.key}`} className="block text-sm font-medium text-foreground mb-1">{f.label}</label>
                  <select
                    id={`field-${f.key}`}
                    value={form[f.key] || ''}
                    onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                    className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm"
                  >
                    {f.options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
              )
            }
            if (f.type === 'combobox') {
              return (
                <div key={f.key}>
                  <label htmlFor={`field-${f.key}`} className="block text-sm font-medium text-foreground mb-1">{f.label}</label>
                  <input
                    id={`field-${f.key}`}
                    type="text"
                    list={`${f.key}-options`}
                    value={form[f.key] || ''}
                    onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                    className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground focus:outline-none focus:ring-2 focus:ring-ring text-sm"
                    placeholder="Select or type a model..."
                  />
                  <datalist id={`${f.key}-options`}>
                    {(vehicleModels || []).map(m => <option key={m} value={m} />)}
                  </datalist>
                </div>
              )
            }
            return (
              <div key={f.key}>
                <label htmlFor={`field-${f.key}`} className="block text-sm font-medium text-foreground mb-1">{f.label}</label>
                <input
                  id={`field-${f.key}`}
                  type={f.type || 'text'}
                  value={form[f.key] || ''}
                  onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground focus:outline-none focus:ring-2 focus:ring-ring text-sm"
                />
              </div>
            )
          })}
          <div className="flex gap-2 pt-2">
            <button type="submit" disabled={saving} className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2">
              {saving && <Loader2 className="w-4 h-4 animate-spin" />}
              {!saving && (record?.id ? 'Update' : `Add ${title}`)}
            </button>
            <button type="button" onClick={onClose} className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90">
              Cancel
            </button>
          </div>
        </form>
    </Modal>
  )
}

// ─── Generic Equipment Table ────────────────────────────────────────────────

function EquipmentTable({ items, columns, isAdmin, onEdit, onDelete, onMerge, emptyMessage, sortKey, sortDir, onToggleSort }) {
  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden">
      <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/30">
            {columns.map(c => (
              <th key={c.key}
                className={`${c.align === 'right' ? 'text-right' : 'text-left'} px-4 py-3 font-medium text-muted-foreground${c.sortable === false ? '' : ' cursor-pointer hover:text-foreground select-none'}`}
                onClick={() => c.sortable !== false && onToggleSort?.(c.key)}
                onKeyDown={c.sortable === false ? undefined : (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onToggleSort?.(c.key) } }}
                tabIndex={c.sortable === false ? undefined : 0}>
                {c.label}
                {sortKey === c.key && (sortDir === 'asc' ? <ChevronUp className="w-3 h-3 inline ml-1" /> : <ChevronDown className="w-3 h-3 inline ml-1" />)}
              </th>
            ))}
            <th className="text-right px-4 py-3 font-medium text-muted-foreground">Actions</th>
          </tr>
        </thead>
        <tbody>
          {items.map(item => (
            <tr key={item.id} className="border-b border-border/50 hover:bg-accent/30 transition-colors">
              {columns.map(c => (
                <td key={c.key} className={`px-4 py-3 ${c.align === 'right' ? 'text-right' : ''} ${c.primary ? 'text-foreground font-medium' : 'text-muted-foreground'}`}>
                  {c.render ? c.render(item) : (item[c.key] || '—')}
                </td>
              ))}
              <td className="px-4 py-3 text-right">
                {isAdmin && (
                  <div className="flex items-center justify-end gap-1">
                    <button onClick={() => onEdit(item)} className="p-1.5 text-muted-foreground hover:text-foreground rounded-lg hover:bg-accent" aria-label="Edit">
                      <Edit className="w-4 h-4" />
                    </button>
                    {onMerge && (
                      <button onClick={() => onMerge(item)} className="p-1.5 text-muted-foreground hover:text-primary rounded-lg hover:bg-primary/10" aria-label="Merge" title="Merge duplicate into this item">
                        <Merge className="w-4 h-4" />
                      </button>
                    )}
                    <button onClick={() => onDelete(item.id)} className="p-1.5 text-muted-foreground hover:text-destructive rounded-lg hover:bg-destructive/10" aria-label="Delete">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                )}
              </td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr><td colSpan={columns.length + 1} className="px-4 py-12 text-center text-muted-foreground">{emptyMessage}</td></tr>
          )}
        </tbody>
      </table>
      </div>
    </div>
  )
}

// ─── Status Badge ───────────────────────────────────────────────────────────

function StatusBadge({ status }) {
  const colors = {
    active: 'bg-success-bg text-success',
    available: 'bg-success-bg text-success',
    online: 'bg-success-bg text-success',
    in_use: 'bg-info-bg text-info',
    charging: 'bg-info-bg text-info',
    maintenance: 'bg-warning-bg text-warning',
    offline: 'bg-zinc-500/15 text-zinc-400',
    retired: 'bg-danger-bg text-danger',
    damaged: 'bg-danger-bg text-danger',
  }
  return (
    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${colors[status] || 'bg-zinc-500/15 text-zinc-400'}`}>
      {status || '—'}
    </span>
  )
}

// ─── Singular helper ────────────────────────────────────────────────────────

function singularize(label) {
  const map = { Batteries: 'Battery', Vehicles: 'Vehicle', Controllers: 'Controller', Docks: 'Dock', Sensors: 'Sensor', Attachments: 'Attachment', Other: 'Other Item' }
  return map[label] || label.slice(0, -1)
}

// ─── Tab Configs ────────────────────────────────────────────────────────────

// Uniform service-life dates shared by every fleet type.
const LIFECYCLE_COLUMNS = [
  { key: 'acquired_date', label: 'Acquired' },
  { key: 'decommissioned_date', label: 'Decommissioned' },
]
const LIFECYCLE_FIELDS = [
  { key: 'acquired_date', label: 'Acquired Date', type: 'date' },
  { key: 'decommissioned_date', label: 'Decommissioned Date', type: 'date' },
]

const TAB_CONFIGS = {
  vehicles: {
    exportPath: '/export/vehicles/csv',
    icon: QuadcopterIcon,
    label: 'Vehicles',
    endpoint: '/vehicles',
    columns: [
      { key: 'nickname', label: 'Vehicle', primary: true, render: v => {
        const name = v.nickname || v.serial_number || '—'
        return <Link to={`/fleet/vehicles/${v.id}`} className="text-primary hover:underline">{name}</Link>
      }},
      { key: 'manufacturer', label: 'Manufacturer' },
      { key: 'model', label: 'Model' },
      { key: 'serial_number', label: 'Serial Number' },
      { key: 'faa_registration', label: 'FAA Reg', render: v => v._reg_number || v.faa_registration || '—' },
      { key: 'next_due', label: 'Next Due', sortable: true, render: v => {
        if (!v._reg_expiry) return <span className="text-muted-foreground">--</span>
        const days = daysUntil(v._reg_expiry)
        const isExpired = days < 0
        const isUrgent = days >= 0 && days < 30
        const isWarning = days >= 30 && days <= 90
        const badgeClass = (() => {
          if (isExpired) return 'bg-red-900/20 text-red-300'
          if (isUrgent) return 'bg-red-500/15 text-red-400'
          if (isWarning) return 'bg-amber-500/15 text-amber-400'
          return 'bg-emerald-500/15 text-emerald-400'
        })()
        return (
          <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${badgeClass}`}>
            {isExpired ? `Overdue` : `${days}d`}
          </span>
        )
      }},
      ...LIFECYCLE_COLUMNS,
      { key: 'status', label: 'Status', render: v => <StatusBadge status={v.status} /> },
    ],
    fields: [
      { key: 'serial_number', label: 'Serial Number' },
      { key: 'provider_serial', label: 'API Serial (what the provider calls this aircraft)' },
      { key: 'manufacturer', label: 'Manufacturer' },
      { key: 'model', label: 'Model' },
      { key: 'nickname', label: 'Nickname' },
      ...LIFECYCLE_FIELDS,
      { key: 'status', label: 'Status', type: 'select', options: [
        { value: 'active', label: 'Active' }, { value: 'maintenance', label: 'Maintenance' }, { value: 'retired', label: 'Retired' }
      ]},
      { key: 'notes', label: 'Notes' },
    ],
  },
  batteries: {
    exportPath: '/export/fleet/batteries/csv',
    icon: Battery,
    label: 'Batteries',
    endpoint: '/batteries',
    columns: [
      { key: 'nickname', label: 'Battery', primary: true, render: b => {
        const name = b.nickname || b.serial_number || '—'
        return <Link to={`/fleet/batteries/${b.id}`} className="text-primary hover:underline">{name}</Link>
      }},
      { key: 'serial_number', label: 'Serial' },
      { key: 'manufacturer', label: 'Manufacturer' },
      { key: 'model', label: 'Model' },
      { key: 'vehicle_model', label: 'Vehicle Model' },
      { key: 'cycle_count', label: 'Cycles', align: 'right' },
      { key: 'health_pct', label: 'Health', align: 'right', render: b => b.health_pct == null ? '—' : `${b.health_pct}%` },
      ...LIFECYCLE_COLUMNS,
      { key: 'status', label: 'Status', render: b => <StatusBadge status={b.status} /> },
    ],
    fields: [
      { key: 'serial_number', label: 'Serial Number' },
      { key: 'nickname', label: 'Nickname' },
      { key: 'manufacturer', label: 'Manufacturer' },
      { key: 'model', label: 'Model' },
      { key: 'vehicle_model', label: 'Vehicle Model', type: 'combobox' },
      { key: 'cycle_count', label: 'Cycle Count', type: 'number' },
      { key: 'health_pct', label: 'Health %', type: 'number' },
      ...LIFECYCLE_FIELDS,
      { key: 'status', label: 'Status', type: 'select', options: [
        { value: 'active', label: 'Active' }, { value: 'charging', label: 'Charging' },
        { value: 'maintenance', label: 'Maintenance' }, { value: 'retired', label: 'Retired' }
      ]},
    ],
  },
  controllers: {
    exportPath: '/export/fleet/controllers/csv',
    icon: Gamepad2,
    label: 'Controllers',
    endpoint: '/controllers',
    columns: [
      { key: 'nickname', label: 'Controller', primary: true, render: c => {
        const name = c.nickname || c.serial_number || '—'
        return <Link to={`/fleet/controllers/${c.id}`} className="text-primary hover:underline">{name}</Link>
      }},
      { key: 'serial_number', label: 'Serial' },
      { key: 'manufacturer', label: 'Manufacturer' },
      { key: 'model', label: 'Model' },
      ...LIFECYCLE_COLUMNS,
      { key: 'status', label: 'Status', render: c => <StatusBadge status={c.status} /> },
    ],
    fields: [
      { key: 'serial_number', label: 'Serial Number' },
      { key: 'nickname', label: 'Nickname' },
      { key: 'manufacturer', label: 'Manufacturer' },
      { key: 'model', label: 'Model' },
      ...LIFECYCLE_FIELDS,
      { key: 'status', label: 'Status', type: 'select', options: [
        { value: 'active', label: 'Active' }, { value: 'maintenance', label: 'Maintenance' }, { value: 'retired', label: 'Retired' }
      ]},
    ],
  },
  docks: {
    exportPath: '/export/fleet/docks/csv',
    icon: Warehouse,
    label: 'Docks',
    endpoint: '/docks',
    columns: [
      { key: 'name', label: 'Name', primary: true, render: d => {
        const name = d.name || d.serial_number || '—'
        return <Link to={`/fleet/docks/${d.id}`} className="text-primary hover:underline">{name}</Link>
      }},
      { key: 'serial_number', label: 'Serial' },
      { key: 'location_name', label: 'Location' },
      { key: 'lat', label: 'Lat', render: d => d.lat == null ? '—' : Number.parseFloat(d.lat).toFixed(6) },
      { key: 'lon', label: 'Lon', render: d => d.lon == null ? '—' : Number.parseFloat(d.lon).toFixed(6) },
      ...LIFECYCLE_COLUMNS,
      { key: 'status', label: 'Status', render: d => <StatusBadge status={d.status} /> },
    ],
    fields: [
      { key: 'serial_number', label: 'Serial Number' },
      { key: 'name', label: 'Name' },
      { key: 'location_name', label: 'Location Name' },
      { key: 'lat', label: 'Latitude', type: 'number' },
      { key: 'lon', label: 'Longitude', type: 'number' },
      ...LIFECYCLE_FIELDS,
      { key: 'status', label: 'Status', type: 'select', options: [
        { value: 'online', label: 'Online' }, { value: 'offline', label: 'Offline' }, { value: 'maintenance', label: 'Maintenance' }
      ]},
    ],
  },
  sensors: {
    exportPath: '/export/fleet/sensors/csv',
    icon: Cpu,
    label: 'Sensors',
    endpoint: '/sensors',
    columns: [
      { key: 'name', label: 'Name', primary: true, render: s => {
        const name = s.name || s.serial_number || '—'
        return <Link to={`/fleet/sensors/${s.id}`} className="text-primary hover:underline">{name}</Link>
      }},
      { key: 'serial_number', label: 'Serial' },
      { key: 'type', label: 'Type' },
      { key: 'manufacturer', label: 'Manufacturer' },
      { key: 'model', label: 'Model' },
      ...LIFECYCLE_COLUMNS,
      { key: 'status', label: 'Status', render: s => <StatusBadge status={s.status} /> },
    ],
    fields: [
      { key: 'serial_number', label: 'Serial Number' },
      { key: 'name', label: 'Name' },
      { key: 'type', label: 'Type' },
      { key: 'manufacturer', label: 'Manufacturer' },
      { key: 'model', label: 'Model' },
      ...LIFECYCLE_FIELDS,
      { key: 'status', label: 'Status', type: 'select', options: [
        { value: 'active', label: 'Active' }, { value: 'maintenance', label: 'Maintenance' }, { value: 'retired', label: 'Retired' }
      ]},
    ],
  },
  attachments: {
    exportPath: '/export/fleet/attachments/csv',
    icon: Paperclip,
    label: 'Attachments',
    endpoint: '/attachments',
    columns: [
      { key: 'name', label: 'Name', primary: true, render: a => {
        const name = a.name || a.serial_number || '—'
        return <Link to={`/fleet/attachments/${a.id}`} className="text-primary hover:underline">{name}</Link>
      }},
      { key: 'serial_number', label: 'Serial' },
      { key: 'type', label: 'Type' },
      { key: 'manufacturer', label: 'Manufacturer' },
      { key: 'model', label: 'Model' },
      ...LIFECYCLE_COLUMNS,
      { key: 'status', label: 'Status', render: a => <StatusBadge status={a.status} /> },
    ],
    fields: [
      { key: 'serial_number', label: 'Serial Number' },
      { key: 'name', label: 'Name' },
      { key: 'type', label: 'Type' },
      { key: 'manufacturer', label: 'Manufacturer' },
      { key: 'model', label: 'Model' },
      ...LIFECYCLE_FIELDS,
      { key: 'status', label: 'Status', type: 'select', options: [
        { value: 'active', label: 'Active' }, { value: 'maintenance', label: 'Maintenance' }, { value: 'retired', label: 'Retired' }
      ]},
    ],
  },
  other: {
    exportPath: '/export/fleet/other-equipment/csv',
    icon: Package,
    label: 'Other',
    endpoint: '/other-equipment',
    columns: [
      { key: 'name', label: 'Name', primary: true, render: o => (
        <Link to={`/fleet/other/${o.id}`} className="text-primary hover:underline">{o.name || '—'}</Link>
      )},
      { key: 'category', label: 'Category' },
      { key: 'serial_number', label: 'Serial' },
      ...LIFECYCLE_COLUMNS,
      { key: 'status', label: 'Status', render: o => <StatusBadge status={o.status} /> },
    ],
    fields: [
      { key: 'name', label: 'Name' },
      { key: 'category', label: 'Category' },
      { key: 'serial_number', label: 'Serial Number' },
      ...LIFECYCLE_FIELDS,
      { key: 'status', label: 'Status', type: 'select', options: [
        { value: 'active', label: 'Active' }, { value: 'maintenance', label: 'Maintenance' },
        { value: 'retired', label: 'Retired' }, { value: 'damaged', label: 'Damaged' }
      ]},
      { key: 'notes', label: 'Notes' },
    ],
  },
}

// ─── Main Component ─────────────────────────────────────────────────────────

export default function FleetPage() {
  // Read tab from URL query param (e.g., /fleet?tab=attachments)
  const initialTab = (() => {
    try { return new URLSearchParams(globalThis.location.search).get('tab') || 'vehicles' } catch { return 'vehicles' }
  })()
  const [activeTab, setActiveTab] = useState(initialTab)
  const [items, setItems] = useState([])
  const [search, setSearch] = useState('')
  // Retired kit stays out of the way until asked for; shared across tabs so the
  // choice does not silently reset when switching between equipment types.
  const [statusFilter, setStatusFilter] = useState('in_service')
  const [modal, setModal] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [sortKey, setSortKey] = useState('name')
  const [sortDir, setSortDir] = useState('asc')
  const [vehicleModels, setVehicleModels] = useState([])
  const { isSupervisor } = useAuth()
  const toast = useToast()
  const [confirmProps, requestConfirm] = useConfirm()
  // Stale-response guard: each load() captures the current sequence number;
  // only the most recent load applies its result. Prevents a slow load
  // (e.g. the vehicles fan-out) from clobbering a newer tab's list.
  const loadSeq = useRef(0)

  // Fetch unique vehicle models for combobox
  useEffect(() => {
    api.get('/vehicles').then(vehicles => {
      const models = [...new Set(vehicles.map(v => v.model).filter(Boolean))]
      setVehicleModels([...models].sort((a, b) => a.localeCompare(b)))
    }).catch(() => {})
  }, [])

  const toggleSort = (key) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  const config = TAB_CONFIGS[activeTab]

  const load = async () => {
    const seq = ++loadSeq.current
    setLoading(true)
    try {
      const data = await api.get(config.endpoint)
      if (activeTab === 'vehicles') {
        // Enrich vehicles with their current registration in a single request.
        // The backend marks exactly one registration per vehicle as is_current,
        // so we trust that flag rather than re-deriving latest-by-date client-side.
        let currentByVehicle = {}
        try {
          const currentRegs = await api.get('/vehicle-registrations/current')
          currentByVehicle = Object.fromEntries(currentRegs.map(r => [r.vehicle_id, r]))
        } catch { currentByVehicle = {} }
        const enriched = data.map((v) => {
          const current = currentByVehicle[v.id]
          return { ...v, _reg_expiry: current?.expiry_date || null, _reg_number: current?.registration_number || null, next_due: current?.expiry_date || '' }
        })
        if (seq !== loadSeq.current) return
        setItems(enriched)
      } else {
        if (seq !== loadSeq.current) return
        setItems(data)
      }
    } catch (err) { if (seq === loadSeq.current) setError(err.message) }
    finally { if (seq === loadSeq.current) setLoading(false) }
  }

  useEffect(() => {
    setSearch('')
    setModal(null)
    setSortKey('name')
    setSortDir('asc')
    load()
  }, [activeTab])

  const handleSave = async (data) => {
    try {
      if (data.id) {
        await api.patch(`${config.endpoint}/${data.id}`, data)
      } else {
        await api.post(config.endpoint, data)
      }
      setModal(null)
      load()
    } catch (err) {
      toast.error(err.message)
    }
  }

  const [mergeTarget, setMergeTarget] = useState(null)
  const [mergeFromId, setMergeFromId] = useState('')
  const [merging, setMerging] = useState(false)

  const handleMerge = async () => {
    if (!mergeTarget || !mergeFromId) return
    setMerging(true)
    try {
      const res = await api.post(`${config.endpoint}/${mergeTarget.id}/merge?merge_from_id=${mergeFromId}`, undefined, { timeout: 120000 })
      toast.success(res.message || 'Merged successfully')
      setMergeTarget(null)
      setMergeFromId('')
      load()
    } catch (err) {
      toast.error(err.message)
    } finally {
      setMerging(false)
    }
  }

  const handleDelete = (id) => {
    requestConfirm({
      title: `Delete ${singularize(config.label)}`,
      message: `Are you sure you want to delete this ${singularize(config.label).toLowerCase()}? This cannot be undone.`,
      onConfirm: async () => {
        try {
          await api.delete(`${config.endpoint}/${id}`)
          load()
        } catch (err) {
          toast.error(err.message)
        }
      }
    })
  }

  const filtered = useMemo(() => {
    const list = items.filter(item => {
      if (statusFilter !== 'all') {
        const out = isDecommissioned(item)
        if (statusFilter === 'decommissioned' ? !out : out) return false
      }
      const searchable = config.columns.map(c => {
        if (c.key === 'status') return item.status || ''
        return item[c.key] || ''
      }).join(' ')
      return searchable.toLowerCase().includes(search.toLowerCase())
    })
    return [...list].sort((a, b) => {
      let aVal, bVal
      // For vehicle nickname column, sort by nickname or serial_number
      if (sortKey === 'nickname' && activeTab === 'vehicles') {
        aVal = (a.nickname || a.serial_number || '').toLowerCase()
        bVal = (b.nickname || b.serial_number || '').toLowerCase()
      } else if (typeof a[sortKey] === 'number' || typeof b[sortKey] === 'number') {
        aVal = a[sortKey] ?? 0
        bVal = b[sortKey] ?? 0
      } else {
        aVal = (a[sortKey] || '').toString().toLowerCase()
        bVal = (b[sortKey] || '').toString().toLowerCase()
      }
      if (aVal < bVal) return sortDir === 'asc' ? -1 : 1
      if (aVal > bVal) return sortDir === 'asc' ? 1 : -1
      return 0
    })
  }, [items, search, statusFilter, sortKey, sortDir, config.columns, activeTab])

  // Items withheld by the status filter alone. Search narrowing is visible to
  // the user as they type; a status filter they did not set is not, so only the
  // latter is worth announcing.
  const hiddenCount = useMemo(() => {
    if (statusFilter === 'all') return 0
    const wantDecommissioned = statusFilter === 'decommissioned'
    return items.filter(i => wantDecommissioned !== isDecommissioned(i)).length
  }, [items, statusFilter])

  return (
    <div className="space-y-4">
      {error && <div className="bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg p-4 mb-4">{error}</div>}
      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-border pb-2 overflow-x-auto">
        {Object.entries(TAB_CONFIGS).map(([key, cfg]) => {
          const Icon = cfg.icon
          return (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={`text-sm font-medium pb-2 border-b-2 transition-colors flex items-center gap-1.5 px-3 whitespace-nowrap ${
                activeTab === key
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              <Icon className="w-4 h-4" /> {cfg.label}
            </button>
          )
        })}
      </div>

      {/* Search + Add */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2 sm:gap-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            placeholder={`Search ${config.label.toLowerCase()}...`}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>

        {/* One right-anchored group. The controls previously sat in the flow
            between the search box and the Add button, so the status filter slid
            sideways whenever a tab changed which buttons were present. */}
        <div className="flex items-center gap-2 shrink-0">
          {/* Say what is being withheld, so a missing item is never a mystery. */}
          {hiddenCount > 0 && (
            <span className="text-xs text-muted-foreground whitespace-nowrap">
              {hiddenCount} hidden
            </span>
          )}
          <label htmlFor="fleet-status-filter" className="sr-only">Status</label>
          <select
            id="fleet-status-filter"
            aria-label="Status"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          >
            {STATUS_FILTERS.map(f => (
              <option key={f.value} value={f.value}>{f.label}</option>
            ))}
          </select>
          <button
            onClick={() => api.download(config.exportPath)}
            className="flex items-center gap-1.5 px-3 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90 whitespace-nowrap"
          >
            <Download className="w-4 h-4" /> Export CSV
          </button>
          {isSupervisor && (
            <button
              onClick={() => setModal('add')}
              /* Fixed width so the group's left edge does not shift between
                 "Add Dock" and "Add Attachment". */
              className="flex items-center justify-center gap-2 w-44 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 whitespace-nowrap"
            >
              <Plus className="w-4 h-4" /> Add {singularize(config.label)}
            </button>
          )}
        </div>
      </div>

      {/* Table */}
      {loading ? (
        <div className="flex items-center justify-center h-64">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <EquipmentTable
          items={filtered}
          columns={config.columns}
          isAdmin={isSupervisor}
          onEdit={(item) => setModal(item)}
          onDelete={handleDelete}
          onMerge={['vehicles', 'batteries', 'sensors', 'attachments'].includes(activeTab) && isSupervisor ? (item) => { setMergeTarget(item); setMergeFromId('') } : null}
          emptyMessage={`No ${config.label.toLowerCase()} found`}
          sortKey={sortKey}
          sortDir={sortDir}
          onToggleSort={toggleSort}
        />
      )}

      {/* Modal */}
      {modal && (
        <EquipmentModal
          title={singularize(config.label)}
          record={modal === 'add' ? null : modal}
          fields={config.fields}
          onSave={handleSave}
          onClose={() => setModal(null)}
          vehicleModels={vehicleModels}
        />
      )}
      {/* Merge Modal */}
      {mergeTarget && (
        <Modal open onClose={() => setMergeTarget(null)} title={`Merge ${singularize(config.label)}`} className="max-w-md">
            <p className="text-sm text-muted-foreground mb-4">
              Select a duplicate to merge into <strong className="text-foreground">{mergeTarget.nickname || mergeTarget.name || mergeTarget.serial_number}</strong>. All flight references will be updated and the duplicate will be deleted.
            </p>
            <div>
              <label htmlFor="merge-from-duplicate-to-remove" className="block text-sm font-medium text-foreground mb-1">Merge from (duplicate to remove)</label>
              <select id="merge-from-duplicate-to-remove"
                value={mergeFromId}
                onChange={e => setMergeFromId(e.target.value)}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm"
              >
                <option value="">Select duplicate...</option>
                {items.filter(i => i.id !== mergeTarget.id).map(i => (
                  <option key={i.id} value={i.id}>{i.nickname || i.name || i.serial_number} ({i.serial_number})</option>
                ))}
              </select>
            </div>
            <div className="flex gap-2 mt-4">
              <button
                onClick={handleMerge}
                disabled={!mergeFromId || merging}
                className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {merging ? <Loader2 className="w-4 h-4 animate-spin" /> : <Merge className="w-4 h-4" />}
                Merge
              </button>
              <button onClick={() => setMergeTarget(null)} className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm">Cancel</button>
            </div>
        </Modal>
      )}
      <ConfirmDialog {...confirmProps} />
    </div>
  )
}
