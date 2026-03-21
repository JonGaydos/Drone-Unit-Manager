import { useState, useEffect } from 'react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { Plus, Trash2, Search, Wrench, CalendarClock, History } from 'lucide-react'

function MaintenanceModal({ record, onSave, onClose }) {
  const [form, setForm] = useState(record || {
    entity_type: 'vehicle', entity_id: '', maintenance_type: 'scheduled',
    description: '', performed_by: '', performed_date: '', next_due_date: '',
    cost: '', notes: ''
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    const data = { ...form }
    if (data.cost) data.cost = parseFloat(data.cost)
    else delete data.cost
    if (data.entity_id) data.entity_id = parseInt(data.entity_id)
    Object.keys(data).forEach(k => { if (data[k] === '') delete data[k] })
    onSave(data)
  }

  const field = (label, key, type = 'text') => (
    <div>
      <label className="block text-sm font-medium text-foreground mb-1">{label}</label>
      <input
        type={type}
        value={form[key] || ''}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
        className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground focus:outline-none focus:ring-2 focus:ring-ring text-sm"
      />
    </div>
  )

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
                onChange={(e) => setForm({ ...form, entity_type: e.target.value })}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm"
              >
                <option value="vehicle">Vehicle</option>
                <option value="battery">Battery</option>
                <option value="controller">Controller</option>
                <option value="dock">Dock</option>
              </select>
            </div>
            {field('Entity ID', 'entity_id', 'number')}
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
          {field('Description', 'description')}
          <div className="grid grid-cols-2 gap-3">
            {field('Performed By', 'performed_by')}
            {field('Performed Date', 'performed_date', 'date')}
          </div>
          <div className="grid grid-cols-2 gap-3">
            {field('Next Due Date', 'next_due_date', 'date')}
            {field('Cost ($)', 'cost', 'number')}
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Notes</label>
            <textarea
              value={form.notes || ''}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm h-20 resize-none"
            />
          </div>
          <div className="flex gap-2 pt-2">
            <button type="submit" className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90">
              {record ? 'Update' : 'Add Maintenance'}
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

export default function MaintenancePage() {
  const [view, setView] = useState('upcoming')
  const [records, setRecords] = useState([])
  const [search, setSearch] = useState('')
  const [modal, setModal] = useState(null)
  const [loading, setLoading] = useState(true)
  const { isAdmin } = useAuth()

  const load = () => {
    setLoading(true)
    const endpoint = view === 'upcoming' ? '/maintenance?upcoming=true' : '/maintenance'
    api.get(endpoint).then(setRecords).catch(console.error).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [view])

  const handleSave = async (data) => {
    try {
      if (data.id) {
        await api.patch(`/maintenance/${data.id}`, data)
      } else {
        await api.post('/maintenance', data)
      }
      setModal(null)
      load()
    } catch (err) {
      alert(err.message)
    }
  }

  const handleDelete = async (id) => {
    if (!confirm('Delete this maintenance record?')) return
    try {
      await api.delete(`/maintenance/${id}`)
      load()
    } catch (err) {
      alert(err.message)
    }
  }

  const filtered = records.filter(r =>
    `${r.description || ''} ${r.entity_type || ''} ${r.performed_by || ''} ${r.maintenance_type || ''}`
      .toLowerCase().includes(search.toLowerCase())
  )

  const TYPE_COLORS = {
    scheduled: 'bg-blue-500/15 text-blue-400',
    unscheduled: 'bg-amber-500/15 text-amber-400',
    inspection: 'bg-emerald-500/15 text-emerald-400',
  }

  if (loading) {
    return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
  }

  return (
    <div className="space-y-4">
      {/* Tabs + Controls */}
      <div className="flex items-center gap-4 border-b border-border pb-2">
        <button onClick={() => setView('upcoming')} className={`text-sm font-medium pb-2 border-b-2 transition-colors flex items-center gap-1.5 ${view === 'upcoming' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'}`}>
          <CalendarClock className="w-4 h-4" /> Upcoming
        </button>
        <button onClick={() => setView('history')} className={`text-sm font-medium pb-2 border-b-2 transition-colors flex items-center gap-1.5 ${view === 'history' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'}`}>
          <History className="w-4 h-4" /> History
        </button>
        <div className="flex-1" />
        {isAdmin && (
          <button onClick={() => setModal('add')} className="flex items-center gap-2 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90">
            <Plus className="w-4 h-4" /> Add Maintenance
          </button>
        )}
      </div>

      {/* Search */}
      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          type="text"
          placeholder="Search maintenance..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-9 pr-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>

      {/* Upcoming View - Cards */}
      {view === 'upcoming' && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map(r => {
            const dueDate = r.next_due_date ? new Date(r.next_due_date) : null
            const now = new Date()
            const daysUntil = dueDate ? Math.ceil((dueDate - now) / (1000 * 60 * 60 * 24)) : null
            const urgencyColor = daysUntil !== null
              ? daysUntil <= 0 ? 'text-red-400' : daysUntil <= 7 ? 'text-amber-400' : 'text-emerald-400'
              : 'text-muted-foreground'

            return (
              <div key={r.id} className="bg-card border border-border rounded-xl p-4">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <Wrench className="w-5 h-5 text-primary" />
                    <h3 className="font-semibold text-foreground text-sm">{r.description || 'Maintenance'}</h3>
                  </div>
                  {isAdmin && (
                    <button onClick={() => handleDelete(r.id)} className="p-1 text-muted-foreground hover:text-destructive">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
                <div className="mt-3 space-y-1.5 text-xs text-muted-foreground">
                  <p>Entity: <span className="text-foreground capitalize">{r.entity_type}</span> #{r.entity_id}</p>
                  <p>Type: <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${TYPE_COLORS[r.maintenance_type] || 'bg-zinc-500/15 text-zinc-400'}`}>{r.maintenance_type}</span></p>
                  <p>Next Due: <span className={`font-medium ${urgencyColor}`}>{r.next_due_date || 'N/A'}</span>
                    {daysUntil !== null && <span className={`ml-1 ${urgencyColor}`}>({daysUntil <= 0 ? 'Overdue' : `${daysUntil}d`})</span>}
                  </p>
                  {r.performed_by && <p>Performed by: <span className="text-foreground">{r.performed_by}</span></p>}
                  {r.cost && <p>Cost: <span className="text-foreground">${parseFloat(r.cost).toFixed(2)}</span></p>}
                </div>
              </div>
            )
          })}
          {filtered.length === 0 && (
            <div className="col-span-full text-center py-12 text-muted-foreground">No upcoming maintenance found</div>
          )}
        </div>
      )}

      {/* History View - Table */}
      {view === 'history' && (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/30">
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Description</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Entity</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Type</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Performed By</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Date</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Next Due</th>
                <th className="text-right px-4 py-3 font-medium text-muted-foreground">Cost</th>
                <th className="text-right px-4 py-3 font-medium text-muted-foreground">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(r => (
                <tr key={r.id} className="border-b border-border/50 hover:bg-accent/30 transition-colors">
                  <td className="px-4 py-3 text-foreground">{r.description || '—'}</td>
                  <td className="px-4 py-3 text-muted-foreground capitalize">{r.entity_type} #{r.entity_id}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${TYPE_COLORS[r.maintenance_type] || 'bg-zinc-500/15 text-zinc-400'}`}>
                      {r.maintenance_type}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{r.performed_by || '—'}</td>
                  <td className="px-4 py-3 text-muted-foreground">{r.performed_date || '—'}</td>
                  <td className="px-4 py-3 text-muted-foreground">{r.next_due_date || '—'}</td>
                  <td className="px-4 py-3 text-right text-foreground">{r.cost ? `$${parseFloat(r.cost).toFixed(2)}` : '—'}</td>
                  <td className="px-4 py-3 text-right">
                    {isAdmin && (
                      <button onClick={() => handleDelete(r.id)} className="p-1.5 text-muted-foreground hover:text-destructive rounded-lg hover:bg-destructive/10">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={8} className="px-4 py-12 text-center text-muted-foreground">No maintenance records found</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {modal && (
        <MaintenanceModal
          record={modal === 'add' ? null : modal}
          onSave={handleSave}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  )
}
