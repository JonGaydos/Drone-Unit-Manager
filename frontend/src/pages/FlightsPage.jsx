import { useState, useEffect, useMemo } from 'react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { formatDuration } from '@/lib/utils'
import { Plus, Search, Filter, CheckCircle, ChevronUp, ChevronDown } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'

function FlightModal({ pilots, vehicles, purposes, onSave, onClose }) {
  const [form, setForm] = useState({
    pilot_id: '', vehicle_id: '', date: '', takeoff_time: '', landing_time: '',
    duration_seconds: '', purpose: '', takeoff_address: '', case_number: '', notes: ''
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    const data = { ...form }
    if (data.pilot_id) data.pilot_id = parseInt(data.pilot_id)
    else delete data.pilot_id
    if (data.vehicle_id) data.vehicle_id = parseInt(data.vehicle_id)
    else delete data.vehicle_id
    if (data.duration_seconds) data.duration_seconds = parseInt(data.duration_seconds)
    else delete data.duration_seconds
    Object.keys(data).forEach(k => { if (data[k] === '') delete data[k] })
    onSave(data)
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-xl p-6 w-full max-w-lg shadow-xl" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-foreground mb-4">Add Flight</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Pilot</label>
              <select value={form.pilot_id} onChange={e => setForm({...form, pilot_id: e.target.value})}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
                <option value="">Select pilot...</option>
                {pilots.map(p => <option key={p.id} value={p.id}>{p.full_name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Vehicle</label>
              <select value={form.vehicle_id} onChange={e => setForm({...form, vehicle_id: e.target.value})}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
                <option value="">Select vehicle...</option>
                {vehicles.map(v => <option key={v.id} value={v.id}>{v.manufacturer} {v.model}</option>)}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Date</label>
              <input type="date" value={form.date} onChange={e => setForm({...form, date: e.target.value})}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Duration (seconds)</label>
              <input type="number" value={form.duration_seconds} onChange={e => setForm({...form, duration_seconds: e.target.value})}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Purpose</label>
            <select value={form.purpose} onChange={e => setForm({...form, purpose: e.target.value})}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
              <option value="">Select purpose...</option>
              {purposes.map(p => <option key={p.id} value={p.name}>{p.name}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Takeoff Address</label>
            <input type="text" value={form.takeoff_address} onChange={e => setForm({...form, takeoff_address: e.target.value})}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Case Number</label>
            <input type="text" value={form.case_number} onChange={e => setForm({...form, case_number: e.target.value})}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
          </div>
          <div className="flex gap-2 pt-2">
            <button type="submit" className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90">Add Flight</button>
            <button type="button" onClick={onClose} className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm">Cancel</button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function FlightsPage() {
  const [flights, setFlights] = useState([])
  const [pilots, setPilots] = useState([])
  const [vehicles, setVehicles] = useState([])
  const [purposes, setPurposes] = useState([])
  const [search, setSearch] = useState('')
  const [modal, setModal] = useState(false)
  const [loading, setLoading] = useState(true)
  const [sortKey, setSortKey] = useState('date')
  const [sortDir, setSortDir] = useState('desc')
  const [searchParams] = useSearchParams()
  const { isAdmin } = useAuth()

  const toggleSort = (key) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  const reviewFilter = searchParams.get('review_status')

  const load = () => {
    const params = reviewFilter ? `?review_status=${reviewFilter}` : ''
    Promise.all([
      api.get(`/flights${params}`),
      api.get('/pilots'),
      api.get('/vehicles'),
      api.get('/flights/purposes/list'),
    ]).then(([f, p, v, pu]) => {
      setFlights(f); setPilots(p); setVehicles(v); setPurposes(pu)
    }).catch(console.error).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [reviewFilter])

  const handleSave = async (data) => {
    try {
      await api.post('/flights', data)
      setModal(false)
      load()
    } catch (err) { alert(err.message) }
  }

  const handleBulkApprove = async (ids) => {
    try {
      await api.post('/flights/bulk-update', {
        flight_ids: ids, review_status: 'reviewed', pilot_confirmed: true
      })
      load()
    } catch (err) { alert(err.message) }
  }

  const filtered = useMemo(() => {
    const list = flights.filter(f =>
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

  const needsReview = flights.filter(f => f.review_status === 'needs_review')

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input type="text" placeholder="Search flights..." value={search} onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
        </div>
        <div className="flex gap-2">
          {reviewFilter && needsReview.length > 0 && isAdmin && (
            <button
              onClick={() => handleBulkApprove(needsReview.map(f => f.id))}
              className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:opacity-90"
            >
              <CheckCircle className="w-4 h-4" /> Approve All ({needsReview.length})
            </button>
          )}
          {isAdmin && (
            <button onClick={() => setModal(true)} className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90">
              <Plus className="w-4 h-4" /> Add Flight
            </button>
          )}
        </div>
      </div>

      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/30">
              <th className="text-left px-4 py-3 font-medium text-muted-foreground cursor-pointer hover:text-foreground select-none" onClick={() => toggleSort('date')}>
                Date{sortKey === 'date' && (sortDir === 'asc' ? <ChevronUp className="w-3 h-3 inline ml-1" /> : <ChevronDown className="w-3 h-3 inline ml-1" />)}
              </th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground cursor-pointer hover:text-foreground select-none" onClick={() => toggleSort('pilot_name')}>
                Pilot{sortKey === 'pilot_name' && (sortDir === 'asc' ? <ChevronUp className="w-3 h-3 inline ml-1" /> : <ChevronDown className="w-3 h-3 inline ml-1" />)}
              </th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground cursor-pointer hover:text-foreground select-none hidden md:table-cell" onClick={() => toggleSort('vehicle_name')}>
                Vehicle{sortKey === 'vehicle_name' && (sortDir === 'asc' ? <ChevronUp className="w-3 h-3 inline ml-1" /> : <ChevronDown className="w-3 h-3 inline ml-1" />)}
              </th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground cursor-pointer hover:text-foreground select-none hidden md:table-cell" onClick={() => toggleSort('purpose')}>
                Purpose{sortKey === 'purpose' && (sortDir === 'asc' ? <ChevronUp className="w-3 h-3 inline ml-1" /> : <ChevronDown className="w-3 h-3 inline ml-1" />)}
              </th>
              <th className="text-right px-4 py-3 font-medium text-muted-foreground cursor-pointer hover:text-foreground select-none" onClick={() => toggleSort('duration_seconds')}>
                Duration{sortKey === 'duration_seconds' && (sortDir === 'asc' ? <ChevronUp className="w-3 h-3 inline ml-1" /> : <ChevronDown className="w-3 h-3 inline ml-1" />)}
              </th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">Location</th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground cursor-pointer hover:text-foreground select-none" onClick={() => toggleSort('review_status')}>
                Status{sortKey === 'review_status' && (sortDir === 'asc' ? <ChevronUp className="w-3 h-3 inline ml-1" /> : <ChevronDown className="w-3 h-3 inline ml-1" />)}
              </th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(f => (
              <tr key={f.id} className="border-b border-border/50 hover:bg-accent/30 transition-colors">
                <td className="px-4 py-3">
                  <Link to={`/flights/${f.id}`} className="text-foreground hover:text-primary">{f.date || '—'}</Link>
                </td>
                <td className="px-4 py-3 text-foreground">{f.pilot_name || <span className="text-amber-400">Unassigned</span>}</td>
                <td className="px-4 py-3 text-muted-foreground hidden md:table-cell">{f.vehicle_name || '—'}</td>
                <td className="px-4 py-3 text-muted-foreground hidden md:table-cell">{f.purpose || <span className="text-amber-400">None</span>}</td>
                <td className="px-4 py-3 text-right text-foreground">{formatDuration(f.duration_seconds)}</td>
                <td className="px-4 py-3 text-muted-foreground truncate max-w-[200px] hidden lg:table-cell">{f.takeoff_address || '—'}</td>
                <td className="px-4 py-3">
                  <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                    f.review_status === 'needs_review' ? 'bg-amber-500/15 text-amber-400' : 'bg-emerald-500/15 text-emerald-400'
                  }`}>{f.review_status === 'needs_review' ? 'Needs Review' : 'Reviewed'}</span>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && <tr><td colSpan={7} className="px-4 py-12 text-center text-muted-foreground">No flights found</td></tr>}
          </tbody>
        </table>
        </div>
      </div>

      {modal && <FlightModal pilots={pilots} vehicles={vehicles} purposes={purposes} onSave={handleSave} onClose={() => setModal(false)} />}
    </div>
  )
}
