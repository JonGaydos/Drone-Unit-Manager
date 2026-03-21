import { useState, useEffect } from 'react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { Plus, Edit, Trash2, Search } from 'lucide-react'
import { formatHours } from '@/lib/utils'

function VehicleModal({ vehicle, onSave, onClose }) {
  const [form, setForm] = useState(vehicle || {
    serial_number: '', manufacturer: '', model: '', nickname: '',
    faa_registration: '', status: 'active', acquired_date: '', notes: ''
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    const data = { ...form }
    if (!data.acquired_date) delete data.acquired_date
    onSave(data)
  }

  const field = (label, key, type = 'text', opts = {}) => (
    <div>
      <label className="block text-sm font-medium text-foreground mb-1">{label}</label>
      <input
        type={type}
        value={form[key] || ''}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
        className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        {...opts}
      />
    </div>
  )

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-xl p-6 w-full max-w-md shadow-xl" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-foreground mb-4">{vehicle ? 'Edit Vehicle' : 'Add Vehicle'}</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          {field('Serial Number', 'serial_number')}
          <div className="grid grid-cols-2 gap-3">
            {field('Manufacturer', 'manufacturer')}
            {field('Model', 'model')}
          </div>
          {field('Nickname', 'nickname')}
          {field('FAA Registration', 'faa_registration')}
          {field('Acquired Date', 'acquired_date', 'date')}
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Status</label>
            <select
              value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value })}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm"
            >
              <option value="active">Active</option>
              <option value="maintenance">Maintenance</option>
              <option value="retired">Retired</option>
            </select>
          </div>
          <div className="flex gap-2 pt-2">
            <button type="submit" className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90">
              {vehicle ? 'Update' : 'Add Vehicle'}
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

export default function VehiclesPage() {
  const [vehicles, setVehicles] = useState([])
  const [search, setSearch] = useState('')
  const [modal, setModal] = useState(null)
  const [loading, setLoading] = useState(true)
  const { isAdmin } = useAuth()

  const load = () => api.get('/vehicles').then(setVehicles).catch(console.error).finally(() => setLoading(false))
  useEffect(() => { load() }, [])

  const handleSave = async (data) => {
    try {
      if (data.id) await api.patch(`/vehicles/${data.id}`, data)
      else await api.post('/vehicles', data)
      setModal(null)
      load()
    } catch (err) { alert(err.message) }
  }

  const handleDelete = async (id) => {
    if (!confirm('Delete this vehicle?')) return
    try { await api.delete(`/vehicles/${id}`); load() } catch (err) { alert(err.message) }
  }

  const filtered = vehicles.filter(v =>
    `${v.manufacturer} ${v.model} ${v.serial_number} ${v.nickname || ''}`
      .toLowerCase().includes(search.toLowerCase())
  )

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input type="text" placeholder="Search vehicles..." value={search} onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
        </div>
        {isAdmin && (
          <button onClick={() => setModal('add')} className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90">
            <Plus className="w-4 h-4" /> Add Vehicle
          </button>
        )}
      </div>

      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/30">
              <th className="text-left px-4 py-3 font-medium text-muted-foreground">Vehicle</th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground">Serial</th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground">FAA Reg</th>
              <th className="text-right px-4 py-3 font-medium text-muted-foreground">Flights</th>
              <th className="text-right px-4 py-3 font-medium text-muted-foreground">Hours</th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground">Status</th>
              <th className="text-right px-4 py-3 font-medium text-muted-foreground">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(v => (
              <tr key={v.id} className="border-b border-border/50 hover:bg-accent/30 transition-colors">
                <td className="px-4 py-3 text-foreground font-medium">
                  {v.manufacturer} {v.model}{v.nickname ? ` (${v.nickname})` : ''}
                </td>
                <td className="px-4 py-3 text-muted-foreground font-mono text-xs">{v.serial_number}</td>
                <td className="px-4 py-3 text-muted-foreground">{v.faa_registration || '—'}</td>
                <td className="px-4 py-3 text-right text-foreground">{v.total_flights}</td>
                <td className="px-4 py-3 text-right text-foreground">{formatHours(v.total_flight_hours * 3600)}</td>
                <td className="px-4 py-3">
                  <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                    v.status === 'active' ? 'bg-emerald-500/15 text-emerald-400' :
                    v.status === 'maintenance' ? 'bg-amber-500/15 text-amber-400' :
                    'bg-red-500/15 text-red-400'
                  }`}>{v.status}</span>
                </td>
                <td className="px-4 py-3 text-right">
                  {isAdmin && (
                    <div className="flex items-center justify-end gap-1">
                      <button onClick={() => setModal(v)} className="p-1.5 text-muted-foreground hover:text-foreground rounded-lg hover:bg-accent"><Edit className="w-4 h-4" /></button>
                      <button onClick={() => handleDelete(v.id)} className="p-1.5 text-muted-foreground hover:text-destructive rounded-lg hover:bg-destructive/10"><Trash2 className="w-4 h-4" /></button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && <tr><td colSpan={7} className="px-4 py-12 text-center text-muted-foreground">No vehicles found</td></tr>}
          </tbody>
        </table>
      </div>

      {modal && <VehicleModal vehicle={modal === 'add' ? null : modal} onSave={handleSave} onClose={() => setModal(null)} />}
    </div>
  )
}
