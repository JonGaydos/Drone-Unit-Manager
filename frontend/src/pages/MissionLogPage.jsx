import { useState, useEffect } from 'react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { normalizeDateValue } from '@/lib/utils'
import { Plus, Search, X, ChevronDown, ChevronUp, Trash2, Download } from 'lucide-react'

const STATUS_OPTIONS = ['planned', 'in_progress', 'completed', 'cancelled']
const ROLE_OPTIONS = ['PIC', 'Observer', 'Spotter', 'Visual Observer', 'Support']

const statusColors = {
  planned: 'bg-blue-500/15 text-blue-400',
  in_progress: 'bg-amber-500/15 text-amber-400',
  completed: 'bg-emerald-500/15 text-emerald-400',
  cancelled: 'bg-red-500/15 text-red-400',
}

function MissionModal({ pilots, vehicles, onSave, onClose, initial }) {
  const [form, setForm] = useState(initial || {
    date: new Date().toISOString().slice(0, 10),
    title: '', description: '', reason: '', location: '',
    case_number: '', man_hours: '', start_time: '', end_time: '',
    vehicle_id: '', status: 'completed', notes: '',
  })
  const [pilotEntries, setPilotEntries] = useState(initial?.pilots?.map(p => ({
    pilot_id: String(p.pilot_id), role: p.role || '', hours: String(p.hours || 0)
  })) || [])

  const addPilotEntry = () => setPilotEntries([...pilotEntries, { pilot_id: '', role: '', hours: '0' }])
  const removePilotEntry = (i) => setPilotEntries(pilotEntries.filter((_, idx) => idx !== i))
  const updatePilotEntry = (i, field, val) => {
    const updated = [...pilotEntries]
    updated[i] = { ...updated[i], [field]: val }
    setPilotEntries(updated)
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    const data = { ...form }
    if (data.vehicle_id) data.vehicle_id = parseInt(data.vehicle_id)
    else delete data.vehicle_id
    if (data.man_hours) data.man_hours = parseFloat(data.man_hours)
    else data.man_hours = 0
    Object.keys(data).forEach(k => { if (data[k] === '') delete data[k] })
    data.pilots = pilotEntries
      .filter(p => p.pilot_id)
      .map(p => ({ pilot_id: parseInt(p.pilot_id), role: p.role || null, hours: parseFloat(p.hours) || 0 }))
    onSave(data)
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-xl p-6 w-full max-w-2xl shadow-xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-foreground mb-4">{initial ? 'Edit Mission' : 'Add Mission'}</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Date *</label>
              <input type="date" required value={form.date} onChange={e => setForm({...form, date: e.target.value})}
                onBlur={e => { const n = normalizeDateValue(e.target.value); if (n !== e.target.value) setForm(prev => ({...prev, date: n})) }}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Status</label>
              <select value={form.status} onChange={e => setForm({...form, status: e.target.value})}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
                {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Title *</label>
            <input type="text" required value={form.title} onChange={e => setForm({...form, title: e.target.value})}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Reason / Purpose</label>
            <input type="text" value={form.reason || ''} onChange={e => setForm({...form, reason: e.target.value})}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Location</label>
              <input type="text" value={form.location || ''} onChange={e => setForm({...form, location: e.target.value})}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Case Number</label>
              <input type="text" value={form.case_number || ''} onChange={e => setForm({...form, case_number: e.target.value})}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Man Hours</label>
              <input type="number" step="0.1" value={form.man_hours} onChange={e => setForm({...form, man_hours: e.target.value})}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Start Time</label>
              <input type="datetime-local" value={form.start_time || ''} onChange={e => setForm({...form, start_time: e.target.value})}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">End Time</label>
              <input type="datetime-local" value={form.end_time || ''} onChange={e => setForm({...form, end_time: e.target.value})}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Drone Used</label>
            <select value={form.vehicle_id} onChange={e => setForm({...form, vehicle_id: e.target.value})}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
              <option value="">Select vehicle...</option>
              {vehicles.map(v => <option key={v.id} value={v.id}>{v.manufacturer} {v.model}{v.nickname ? ` (${v.nickname})` : ''}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Description</label>
            <textarea rows={2} value={form.description || ''} onChange={e => setForm({...form, description: e.target.value})}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Notes</label>
            <textarea rows={2} value={form.notes || ''} onChange={e => setForm({...form, notes: e.target.value})}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
          </div>

          {/* Pilots Section */}
          <div className="border border-border rounded-lg p-3">
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium text-foreground">Pilots Involved</label>
              <button type="button" onClick={addPilotEntry} className="text-xs text-primary hover:underline">+ Add Pilot</button>
            </div>
            {pilotEntries.length === 0 && <p className="text-xs text-muted-foreground">No pilots added yet.</p>}
            {pilotEntries.map((pe, i) => (
              <div key={i} className="flex items-center gap-2 mb-2">
                <select value={pe.pilot_id} onChange={e => updatePilotEntry(i, 'pilot_id', e.target.value)}
                  className="flex-1 px-2 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm">
                  <option value="">Select pilot...</option>
                  {pilots.map(p => <option key={p.id} value={p.id}>{p.full_name}</option>)}
                </select>
                <select value={pe.role} onChange={e => updatePilotEntry(i, 'role', e.target.value)}
                  className="w-32 px-2 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm">
                  <option value="">Role...</option>
                  {ROLE_OPTIONS.map(r => <option key={r} value={r}>{r}</option>)}
                </select>
                <input type="number" step="0.1" placeholder="Hrs" value={pe.hours}
                  onChange={e => updatePilotEntry(i, 'hours', e.target.value)}
                  className="w-20 px-2 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm" />
                <button type="button" onClick={() => removePilotEntry(i)} className="text-muted-foreground hover:text-destructive p-1">
                  <X className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>

          <div className="flex gap-2 pt-2">
            <button type="submit" className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90">
              {initial ? 'Save Changes' : 'Add Mission'}
            </button>
            <button type="button" onClick={onClose} className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm">Cancel</button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function MissionLogPage() {
  const [missions, setMissions] = useState([])
  const [pilots, setPilots] = useState([])
  const [vehicles, setVehicles] = useState([])
  const [search, setSearch] = useState('')
  const [modal, setModal] = useState(false)
  const [editMission, setEditMission] = useState(null)
  const [expanded, setExpanded] = useState(null)
  const [loading, setLoading] = useState(true)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [filterPilot, setFilterPilot] = useState('')
  const { isAdmin } = useAuth()

  const load = () => {
    const params = new URLSearchParams()
    if (dateFrom) params.set('date_from', dateFrom)
    if (dateTo) params.set('date_to', dateTo)
    if (filterPilot) params.set('pilot_id', filterPilot)
    const qs = params.toString() ? `?${params.toString()}` : ''
    Promise.all([
      api.get(`/mission-logs${qs}`),
      api.get('/pilots'),
      api.get('/vehicles'),
    ]).then(([m, p, v]) => {
      setMissions(m); setPilots(p); setVehicles(v)
    }).catch(console.error).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [dateFrom, dateTo, filterPilot])

  const handleSave = async (data) => {
    try {
      if (editMission) {
        await api.patch(`/mission-logs/${editMission.id}`, data)
      } else {
        await api.post('/mission-logs', data)
      }
      setModal(false)
      setEditMission(null)
      load()
    } catch (err) { alert(err.message) }
  }

  const handleDelete = async (id) => {
    if (!confirm('Delete this mission log?')) return
    try {
      await api.delete(`/mission-logs/${id}`)
      load()
    } catch (err) { alert(err.message) }
  }

  const handleEdit = (mission) => {
    setEditMission(mission)
    setModal(true)
  }

  const filtered = missions.filter(m =>
    `${m.title} ${m.reason || ''} ${m.location || ''} ${m.case_number || ''} ${m.pilots?.map(p => p.pilot_name).join(' ') || ''}`
      .toLowerCase().includes(search.toLowerCase())
  )

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2 sm:gap-4 flex-wrap">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input type="text" placeholder="Search missions..." value={search} onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} placeholder="From"
            onBlur={e => { const n = normalizeDateValue(e.target.value); if (n !== e.target.value) { e.target.value = n; setDateFrom(n) } }}
            className="px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
          <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} placeholder="To"
            onBlur={e => { const n = normalizeDateValue(e.target.value); if (n !== e.target.value) { e.target.value = n; setDateTo(n) } }}
            className="px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
          <select value={filterPilot} onChange={e => setFilterPilot(e.target.value)}
            className="px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
            <option value="">All Pilots</option>
            {pilots.map(p => <option key={p.id} value={p.id}>{p.full_name}</option>)}
          </select>
          <button
            onClick={() => api.download('/export/mission-logs/csv')}
            className="flex items-center gap-1.5 px-3 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90"
          >
            <Download className="w-4 h-4" /> Export CSV
          </button>
          {isAdmin && (
            <button onClick={() => { setEditMission(null); setModal(true) }} className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90">
              <Plus className="w-4 h-4" /> Add Mission
            </button>
          )}
        </div>
      </div>

      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/30">
              <th className="w-8 px-2"></th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground">Date</th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground">Title</th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Reason</th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">Location</th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Drone</th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">Pilots</th>
              <th className="text-right px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Man Hours</th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground">Status</th>
              {isAdmin && <th className="w-10 px-2"></th>}
            </tr>
          </thead>
          <tbody>
            {filtered.map(m => (
              <>
                <tr key={m.id} className="border-b border-border/50 hover:bg-accent/30 transition-colors cursor-pointer"
                  onClick={() => setExpanded(expanded === m.id ? null : m.id)}>
                  <td className="px-2 text-muted-foreground">
                    {expanded === m.id ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </td>
                  <td className="px-4 py-3 text-foreground">{m.date}</td>
                  <td className="px-4 py-3 text-foreground font-medium">{m.title}</td>
                  <td className="px-4 py-3 text-muted-foreground hidden md:table-cell">{m.reason || '—'}</td>
                  <td className="px-4 py-3 text-muted-foreground truncate max-w-[150px] hidden lg:table-cell">{m.location || '—'}</td>
                  <td className="px-4 py-3 text-muted-foreground hidden md:table-cell">{m.vehicle_name || '—'}</td>
                  <td className="px-4 py-3 text-muted-foreground hidden lg:table-cell">
                    {m.pilots?.length > 0 ? m.pilots.map(p => p.pilot_name).join(', ') : '—'}
                  </td>
                  <td className="px-4 py-3 text-right text-foreground hidden md:table-cell">{m.man_hours || 0}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${statusColors[m.status] || 'bg-gray-500/15 text-gray-400'}`}>
                      {m.status?.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}
                    </span>
                  </td>
                  {isAdmin && (
                    <td className="px-2" onClick={e => e.stopPropagation()}>
                      <button onClick={() => handleDelete(m.id)} className="text-muted-foreground hover:text-destructive p-1">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  )}
                </tr>
                {expanded === m.id && (
                  <tr key={`${m.id}-detail`} className="border-b border-border/50 bg-muted/10">
                    <td colSpan={isAdmin ? 10 : 9} className="px-8 py-4">
                      <div className="grid grid-cols-2 gap-4 text-sm">
                        {m.description && <div><span className="text-muted-foreground">Description:</span> <span className="text-foreground">{m.description}</span></div>}
                        {m.case_number && <div><span className="text-muted-foreground">Case #:</span> <span className="text-foreground">{m.case_number}</span></div>}
                        {m.start_time && <div><span className="text-muted-foreground">Start:</span> <span className="text-foreground">{new Date(m.start_time).toLocaleString()}</span></div>}
                        {m.end_time && <div><span className="text-muted-foreground">End:</span> <span className="text-foreground">{new Date(m.end_time).toLocaleString()}</span></div>}
                        {m.notes && <div className="col-span-2"><span className="text-muted-foreground">Notes:</span> <span className="text-foreground">{m.notes}</span></div>}
                        {m.pilots?.length > 0 && (
                          <div className="col-span-2">
                            <span className="text-muted-foreground block mb-1">Pilot Details:</span>
                            <div className="space-y-1">
                              {m.pilots.map(p => (
                                <div key={p.id} className="text-foreground">
                                  {p.pilot_name} {p.role && <span className="text-muted-foreground">({p.role})</span>} — {p.hours}h
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                      {isAdmin && (
                        <button onClick={() => handleEdit(m)} className="mt-3 px-3 py-1.5 bg-secondary text-secondary-foreground rounded-lg text-xs hover:opacity-90">
                          Edit Mission
                        </button>
                      )}
                    </td>
                  </tr>
                )}
              </>
            ))}
            {filtered.length === 0 && <tr><td colSpan={isAdmin ? 10 : 9} className="px-4 py-12 text-center text-muted-foreground">No mission logs found</td></tr>}
          </tbody>
        </table>
        </div>
      </div>

      {modal && (
        <MissionModal
          pilots={pilots}
          vehicles={vehicles}
          onSave={handleSave}
          onClose={() => { setModal(false); setEditMission(null) }}
          initial={editMission}
        />
      )}
    </div>
  )
}
