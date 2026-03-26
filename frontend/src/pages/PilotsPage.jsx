import { useState, useEffect, useMemo } from 'react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { Plus, Edit, Trash2, Search, ChevronUp, ChevronDown, Download, Loader2 } from 'lucide-react'
import { Link } from 'react-router-dom'

function PilotModal({ pilot, onSave, onClose }) {
  const [form, setForm] = useState(pilot || {
    first_name: '', last_name: '', email: '', phone: '', phone_type: 'work', phone_work: '', badge_number: '', status: 'active', notes: ''
  })
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSaving(true)
    try { await onSave(form) } finally { setSaving(false) }
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
      <div className="bg-card border border-border rounded-xl p-6 w-full max-w-md shadow-xl" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-foreground mb-4">{pilot ? 'Edit Pilot' : 'Add Pilot'}</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            {field('First Name', 'first_name')}
            {field('Last Name', 'last_name')}
          </div>
          {field('Email', 'email', 'email')}
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Personal Cell</label>
            <input
              type="tel"
              value={form.phone || ''}
              onChange={(e) => {
                const digits = e.target.value.replace(/\D/g, '').slice(0, 10)
                let formatted = digits
                if (digits.length > 3) formatted = digits.slice(0,3) + '-' + digits.slice(3)
                if (digits.length > 6) formatted = digits.slice(0,3) + '-' + digits.slice(3,6) + '-' + digits.slice(6)
                setForm({ ...form, phone: formatted })
              }}
              placeholder="###-###-####"
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Work Cell</label>
            <input
              type="tel"
              value={form.phone_work || ''}
              onChange={(e) => {
                const digits = e.target.value.replace(/\D/g, '').slice(0, 10)
                let formatted = digits
                if (digits.length > 3) formatted = digits.slice(0,3) + '-' + digits.slice(3)
                if (digits.length > 6) formatted = digits.slice(0,3) + '-' + digits.slice(3,6) + '-' + digits.slice(6)
                setForm({ ...form, phone_work: formatted })
              }}
              placeholder="###-###-####"
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          {field('Badge Number', 'badge_number')}
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Status</label>
            <select
              value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value })}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm"
            >
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
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
            <button type="submit" disabled={saving} className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : (pilot ? 'Update' : 'Add Pilot')}
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

export default function PilotsPage() {
  const [pilots, setPilots] = useState([])
  const [search, setSearch] = useState('')
  const [modal, setModal] = useState(null) // null | 'add' | pilot object
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [sortKey, setSortKey] = useState('last_name')
  const [sortDir, setSortDir] = useState('asc')
  const { isAdmin, isPilot, isSupervisor } = useAuth()
  const toast = useToast()

  const toggleSort = (key) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  const loadPilots = () => {
    api.get('/pilots').then(setPilots).catch(err => setError(err.message)).finally(() => setLoading(false))
  }

  useEffect(() => { loadPilots() }, [])

  const handleSave = async (data) => {
    try {
      if (data.id) {
        await api.patch(`/pilots/${data.id}`, data)
      } else {
        await api.post('/pilots', data)
      }
      setModal(null)
      loadPilots()
    } catch (err) {
      toast.error(err.message)
    }
  }

  const handleDelete = async (pilot) => {
    if (!window.confirm(`Are you sure you want to deactivate ${pilot.first_name} ${pilot.last_name}?`)) return
    try {
      await api.delete(`/pilots/${pilot.id}`)
      loadPilots()
    } catch (err) {
      toast.error(err.message)
    }
  }

  const filtered = useMemo(() => {
    const list = pilots.filter(p =>
      `${p.first_name} ${p.last_name} ${p.email || ''} ${p.badge_number || ''}`
        .toLowerCase().includes(search.toLowerCase())
    )
    return [...list].sort((a, b) => {
      let aVal, bVal
      if (sortKey === 'last_name') {
        aVal = `${a.last_name} ${a.first_name}`.toLowerCase()
        bVal = `${b.last_name} ${b.first_name}`.toLowerCase()
      } else if (sortKey === 'email') {
        aVal = (a.email || '').toLowerCase()
        bVal = (b.email || '').toLowerCase()
      } else if (sortKey === 'badge_number') {
        aVal = (a.badge_number || '').toLowerCase()
        bVal = (b.badge_number || '').toLowerCase()
      } else if (sortKey === 'status') {
        aVal = (a.status || '').toLowerCase()
        bVal = (b.status || '').toLowerCase()
      } else {
        aVal = (a[sortKey] || '').toString().toLowerCase()
        bVal = (b[sortKey] || '').toString().toLowerCase()
      }
      if (aVal < bVal) return sortDir === 'asc' ? -1 : 1
      if (aVal > bVal) return sortDir === 'asc' ? 1 : -1
      return 0
    })
  }, [pilots, search, sortKey, sortDir])

  if (loading) {
    return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
  }

  return (
    <div className="space-y-4">
      {error && <div className="bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg p-4 mb-4">{error}</div>}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2 sm:gap-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search pilots..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
        <button
          onClick={() => api.download('/export/pilots/csv')}
          className="flex items-center justify-center gap-1.5 px-3 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90"
        >
          <Download className="w-4 h-4" /> Export CSV
        </button>
        {isSupervisor && (
          <button
            onClick={() => setModal('add')}
            className="flex items-center justify-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90"
          >
            <Plus className="w-4 h-4" /> Add Pilot
          </button>
        )}
      </div>

      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/30">
              <th className="text-left px-4 py-3 font-medium text-muted-foreground cursor-pointer hover:text-foreground select-none" onClick={() => toggleSort('last_name')}>
                Name{sortKey === 'last_name' && (sortDir === 'asc' ? <ChevronUp className="w-3 h-3 inline ml-1" /> : <ChevronDown className="w-3 h-3 inline ml-1" />)}
              </th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground cursor-pointer hover:text-foreground select-none hidden md:table-cell" onClick={() => toggleSort('email')}>
                Email{sortKey === 'email' && (sortDir === 'asc' ? <ChevronUp className="w-3 h-3 inline ml-1" /> : <ChevronDown className="w-3 h-3 inline ml-1" />)}
              </th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground cursor-pointer hover:text-foreground select-none hidden md:table-cell" onClick={() => toggleSort('badge_number')}>
                Badge #{sortKey === 'badge_number' && (sortDir === 'asc' ? <ChevronUp className="w-3 h-3 inline ml-1" /> : <ChevronDown className="w-3 h-3 inline ml-1" />)}
              </th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground cursor-pointer hover:text-foreground select-none" onClick={() => toggleSort('status')}>
                Status{sortKey === 'status' && (sortDir === 'asc' ? <ChevronUp className="w-3 h-3 inline ml-1" /> : <ChevronDown className="w-3 h-3 inline ml-1" />)}
              </th>
              <th className="text-right px-4 py-3 font-medium text-muted-foreground">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((p) => (
              <tr key={p.id} className="border-b border-border/50 hover:bg-accent/30 transition-colors">
                <td className="px-4 py-3">
                  <Link to={`/pilots/${p.id}`} className="flex items-center gap-2 text-foreground hover:text-primary">
                    <div className="w-8 h-8 rounded-full bg-primary/15 flex items-center justify-center text-primary text-xs font-medium">
                      {p.first_name[0]}{p.last_name[0]}
                    </div>
                    {p.full_name}
                  </Link>
                </td>
                <td className="px-4 py-3 text-muted-foreground hidden md:table-cell">{p.email || '—'}</td>
                <td className="px-4 py-3 text-muted-foreground hidden md:table-cell">{p.badge_number || '—'}</td>
                <td className="px-4 py-3">
                  <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                    p.status === 'active' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-red-500/15 text-red-400'
                  }`}>
                    {p.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-right">
                  {isSupervisor && (
                    <div className="flex items-center justify-end gap-1">
                      <button onClick={() => setModal(p)} className="p-1.5 text-muted-foreground hover:text-foreground rounded-lg hover:bg-accent" aria-label="Edit">
                        <Edit className="w-4 h-4" />
                      </button>
                      <button onClick={() => handleDelete(p)} className="p-1.5 text-muted-foreground hover:text-destructive rounded-lg hover:bg-destructive/10" aria-label="Delete">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-12 text-center text-muted-foreground">No pilots found</td></tr>
            )}
          </tbody>
        </table>
        </div>
      </div>

      {modal && (
        <PilotModal
          pilot={modal === 'add' ? null : modal}
          onSave={handleSave}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  )
}
