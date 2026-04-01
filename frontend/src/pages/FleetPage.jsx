import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { useConfirm } from '@/hooks/useConfirm'
import { Plus, Edit, Trash2, Search, Battery, Gamepad2, Warehouse, Cpu, Paperclip, ChevronUp, ChevronDown, Download, Loader2, Merge } from 'lucide-react'
import { QuadcopterIcon } from '@/components/icons/QuadcopterIcon'

// ─── Generic Equipment Modal ────────────────────────────────────────────────

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
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <button className="absolute inset-0 bg-transparent cursor-default" onClick={onClose} aria-label="Close dialog" />
      <div className="relative bg-card border border-border rounded-xl p-6 w-full max-w-md shadow-xl max-h-[90vh] overflow-y-auto">
        <h2 className="text-lg font-semibold text-foreground mb-4">{record?.id ? `Edit ${title}` : `Add ${title}`}</h2>
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
      </div>
    </div>
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
    active: 'bg-emerald-500/15 text-emerald-400',
    available: 'bg-emerald-500/15 text-emerald-400',
    online: 'bg-emerald-500/15 text-emerald-400',
    in_use: 'bg-blue-500/15 text-blue-400',
    charging: 'bg-blue-500/15 text-blue-400',
    maintenance: 'bg-amber-500/15 text-amber-400',
    offline: 'bg-zinc-500/15 text-zinc-400',
    retired: 'bg-red-500/15 text-red-400',
    damaged: 'bg-red-500/15 text-red-400',
  }
  return (
    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${colors[status] || 'bg-zinc-500/15 text-zinc-400'}`}>
      {status || '—'}
    </span>
  )
}

// ─── Singular helper ────────────────────────────────────────────────────────

function singularize(label) {
  const map = { Batteries: 'Battery', Vehicles: 'Vehicle', Controllers: 'Controller', Docks: 'Dock', Sensors: 'Sensor', Attachments: 'Attachment' }
  return map[label] || label.slice(0, -1)
}

// ─── Tab Configs ────────────────────────────────────────────────────────────

const TAB_CONFIGS = {
  vehicles: {
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
      { key: 'faa_registration', label: 'FAA Reg' },
      { key: 'next_due', label: 'Next Due', sortable: true, render: v => {
        if (!v._reg_expiry) return <span className="text-muted-foreground">--</span>
        const today = new Date()
        const expiry = new Date(v._reg_expiry)
        const days = Math.ceil((expiry - today) / (1000 * 60 * 60 * 24))
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
      { key: 'status', label: 'Status', render: v => <StatusBadge status={v.status} /> },
    ],
    fields: [
      { key: 'serial_number', label: 'Serial Number' },
      { key: 'manufacturer', label: 'Manufacturer' },
      { key: 'model', label: 'Model' },
      { key: 'nickname', label: 'Nickname' },
      { key: 'faa_registration', label: 'FAA Registration' },
      { key: 'acquired_date', label: 'Acquired Date', type: 'date' },
      { key: 'status', label: 'Status', type: 'select', options: [
        { value: 'active', label: 'Active' }, { value: 'maintenance', label: 'Maintenance' }, { value: 'retired', label: 'Retired' }
      ]},
      { key: 'notes', label: 'Notes' },
    ],
  },
  batteries: {
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
      { key: 'purchase_date', label: 'Purchase Date', type: 'date' },
      { key: 'status', label: 'Status', type: 'select', options: [
        { value: 'active', label: 'Active' }, { value: 'charging', label: 'Charging' },
        { value: 'maintenance', label: 'Maintenance' }, { value: 'retired', label: 'Retired' }
      ]},
    ],
  },
  controllers: {
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
      { key: 'status', label: 'Status', render: c => <StatusBadge status={c.status} /> },
    ],
    fields: [
      { key: 'serial_number', label: 'Serial Number' },
      { key: 'nickname', label: 'Nickname' },
      { key: 'manufacturer', label: 'Manufacturer' },
      { key: 'model', label: 'Model' },
      { key: 'status', label: 'Status', type: 'select', options: [
        { value: 'active', label: 'Active' }, { value: 'maintenance', label: 'Maintenance' }, { value: 'retired', label: 'Retired' }
      ]},
    ],
  },
  docks: {
    icon: Warehouse,
    label: 'Docks',
    endpoint: '/docks',
    columns: [
      { key: 'name', label: 'Name', primary: true },
      { key: 'serial_number', label: 'Serial' },
      { key: 'location_name', label: 'Location' },
      { key: 'lat', label: 'Lat', render: d => d.lat == null ? '—' : Number.parseFloat(d.lat).toFixed(6) },
      { key: 'lon', label: 'Lon', render: d => d.lon == null ? '—' : Number.parseFloat(d.lon).toFixed(6) },
      { key: 'status', label: 'Status', render: d => <StatusBadge status={d.status} /> },
    ],
    fields: [
      { key: 'serial_number', label: 'Serial Number' },
      { key: 'name', label: 'Name' },
      { key: 'location_name', label: 'Location Name' },
      { key: 'lat', label: 'Latitude', type: 'number' },
      { key: 'lon', label: 'Longitude', type: 'number' },
      { key: 'status', label: 'Status', type: 'select', options: [
        { value: 'online', label: 'Online' }, { value: 'offline', label: 'Offline' }, { value: 'maintenance', label: 'Maintenance' }
      ]},
    ],
  },
  sensors: {
    icon: Cpu,
    label: 'Sensors',
    endpoint: '/sensors',
    columns: [
      { key: 'name', label: 'Name', primary: true },
      { key: 'serial_number', label: 'Serial' },
      { key: 'type', label: 'Type' },
      { key: 'manufacturer', label: 'Manufacturer' },
      { key: 'model', label: 'Model' },
      { key: 'status', label: 'Status', render: s => <StatusBadge status={s.status} /> },
    ],
    fields: [
      { key: 'serial_number', label: 'Serial Number' },
      { key: 'name', label: 'Name' },
      { key: 'type', label: 'Type' },
      { key: 'manufacturer', label: 'Manufacturer' },
      { key: 'model', label: 'Model' },
      { key: 'status', label: 'Status', type: 'select', options: [
        { value: 'active', label: 'Active' }, { value: 'maintenance', label: 'Maintenance' }, { value: 'retired', label: 'Retired' }
      ]},
    ],
  },
  attachments: {
    icon: Paperclip,
    label: 'Attachments',
    endpoint: '/attachments',
    columns: [
      { key: 'name', label: 'Name', primary: true },
      { key: 'serial_number', label: 'Serial' },
      { key: 'type', label: 'Type' },
      { key: 'manufacturer', label: 'Manufacturer' },
      { key: 'model', label: 'Model' },
      { key: 'status', label: 'Status', render: a => <StatusBadge status={a.status} /> },
    ],
    fields: [
      { key: 'serial_number', label: 'Serial Number' },
      { key: 'name', label: 'Name' },
      { key: 'type', label: 'Type' },
      { key: 'manufacturer', label: 'Manufacturer' },
      { key: 'model', label: 'Model' },
      { key: 'status', label: 'Status', type: 'select', options: [
        { value: 'active', label: 'Active' }, { value: 'maintenance', label: 'Maintenance' }, { value: 'retired', label: 'Retired' }
      ]},
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
  const [modal, setModal] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [sortKey, setSortKey] = useState('name')
  const [sortDir, setSortDir] = useState('asc')
  const [vehicleModels, setVehicleModels] = useState([])
  const { isSupervisor } = useAuth()
  const toast = useToast()
  const [confirmProps, requestConfirm] = useConfirm()

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
    setLoading(true)
    try {
      const data = await api.get(config.endpoint)
      if (activeTab === 'vehicles') {
        // Enrich vehicles with registration expiry
        const enriched = await Promise.all(data.map(async (v) => {
          try {
            const regs = await api.get(`/vehicles/${v.id}/registrations`)
            const current = [...regs].sort((a, b) => (b.registration_date || '').localeCompare(a.registration_date || ''))[0]
            return { ...v, _reg_expiry: current?.expiry_date || null, next_due: current?.expiry_date || '' }
          } catch { return { ...v, _reg_expiry: null, next_due: '' } }
        }))
        setItems(enriched)
      } else {
        setItems(data)
      }
    } catch (err) { setError(err.message) }
    finally { setLoading(false) }
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
      const res = await api.post(`${config.endpoint}/${mergeTarget.id}/merge?merge_from_id=${mergeFromId}`)
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
  }, [items, search, sortKey, sortDir, config.columns, activeTab])

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
        {activeTab === 'vehicles' && (
          <button
            onClick={() => api.download('/export/vehicles/csv')}
            className="flex items-center gap-1.5 px-3 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90"
          >
            <Download className="w-4 h-4" /> Export CSV
          </button>
        )}
        {isSupervisor && (
          <button
            onClick={() => setModal('add')}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90"
          >
            <Plus className="w-4 h-4" /> Add {singularize(config.label)}
          </button>
        )}
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
          onMerge={['batteries', 'sensors', 'attachments'].includes(activeTab) && isSupervisor ? (item) => { setMergeTarget(item); setMergeFromId('') } : null}
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
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <button className="absolute inset-0 bg-transparent cursor-default" onClick={() => setMergeTarget(null)} aria-label="Close dialog" />
          <div className="relative bg-card border border-border rounded-xl p-6 w-full max-w-md shadow-xl">
            <h2 className="text-lg font-semibold text-foreground mb-2">Merge {singularize(config.label)}</h2>
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
          </div>
        </div>
      )}
      <ConfirmDialog {...confirmProps} />
    </div>
  )
}
