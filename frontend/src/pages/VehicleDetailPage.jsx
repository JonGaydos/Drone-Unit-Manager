import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { formatHours, formatDuration } from '@/lib/utils'
import {
  ArrowLeft, Plane, Clock, Calendar, Battery, Edit,
  FileText, Wrench, Gamepad2, Cpu, Paperclip, Camera,
  ShieldCheck, Plus, Trash2, AlertTriangle
} from 'lucide-react'
import DocumentUpload from '@/components/DocumentUpload'

const STATUS_COLORS = {
  active: 'bg-emerald-500/15 text-emerald-400',
  available: 'bg-emerald-500/15 text-emerald-400',
  maintenance: 'bg-amber-500/15 text-amber-400',
  retired: 'bg-red-500/15 text-red-400',
  damaged: 'bg-red-500/15 text-red-400',
}

export default function VehicleDetailPage() {
  const { id } = useParams()
  const { isAdmin } = useAuth()
  const [vehicle, setVehicle] = useState(null)
  const [stats, setStats] = useState(null)
  const [flights, setFlights] = useState([])
  const [batteries, setBatteries] = useState([])
  const [controllers, setControllers] = useState([])
  const [sensors, setSensors] = useState([])
  const [attachments, setAttachments] = useState([])
  const [maintenance, setMaintenance] = useState([])
  const [registrations, setRegistrations] = useState([])
  const [loading, setLoading] = useState(true)
  const [equipTab, setEquipTab] = useState('batteries')
  const [showRegForm, setShowRegForm] = useState(false)
  const [regForm, setRegForm] = useState({ registration_number: '', registration_date: '', notes: '' })

  const loadRegistrations = () => {
    api.get(`/vehicles/${id}/registrations`).then(setRegistrations).catch(() => [])
  }

  useEffect(() => {
    Promise.all([
      api.get(`/vehicles/${id}`),
      api.get(`/vehicles/${id}/stats`),
      api.get(`/flights?vehicle_id=${id}&limit=50`),
      api.get('/batteries').catch(() => []),
      api.get('/controllers').catch(() => []),
      api.get('/sensors').catch(() => []),
      api.get('/attachments').catch(() => []),
      api.get(`/maintenance?entity_type=vehicle&entity_id=${id}`).catch(() => []),
      api.get(`/vehicles/${id}/registrations`).catch(() => []),
    ]).then(([v, s, f, bat, ctrl, sens, att, maint, regs]) => {
      setVehicle(v)
      setStats(s)
      setFlights(f)
      setBatteries(bat)
      setControllers(ctrl)
      setSensors(sens)
      setAttachments(att)
      setMaintenance(maint)
      setRegistrations(regs)
    }).catch(console.error).finally(() => setLoading(false))
  }, [id])

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
  if (!vehicle) return <div className="text-center text-muted-foreground py-12">Vehicle not found</div>

  const vehicleName = `${vehicle.manufacturer || ''} ${vehicle.model || ''}`.trim()
  const displayName = vehicle.nickname ? `${vehicleName} (${vehicle.nickname})` : vehicleName

  // Extract unique battery serials from flights
  const flightBatterySerials = [...new Set(flights.map(f => f.battery_serial).filter(Boolean))]
  // Match to battery records
  const matchedBatteries = flightBatterySerials.map(serial => {
    const record = batteries.find(b => b.serial_number === serial)
    return { serial, record }
  })

  // Count active batteries compatible with this vehicle model
  const activeBatteryCount = batteries.filter(
    b => b.vehicle_model && vehicle.model && b.vehicle_model.toLowerCase() === vehicle.model.toLowerCase() && b.status !== 'retired'
  ).length

  const equipTabs = [
    { key: 'batteries', label: 'Batteries', icon: Battery },
    { key: 'controllers', label: 'Controllers', icon: Gamepad2 },
    { key: 'sensors', label: 'Sensors', icon: Cpu },
    { key: 'attachments', label: 'Attachments', icon: Paperclip },
  ]

  return (
    <div className="space-y-6">
      <Link to="/fleet" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="w-4 h-4" /> Back to Fleet
      </Link>

      {/* Header */}
      <div className="bg-card border border-border rounded-xl p-6">
        <div className="flex items-start gap-4">
          <div className="relative shrink-0">
            {vehicle.photo_url ? (
              <img src={vehicle.photo_url} alt={displayName}
                className="w-16 h-16 rounded-2xl object-cover" />
            ) : (
              <div className="w-16 h-16 rounded-2xl bg-primary/15 flex items-center justify-center text-primary">
                <Plane className="w-8 h-8" />
              </div>
            )}
            {isAdmin && (
              <label className="absolute -bottom-1 -right-1 w-6 h-6 bg-primary text-primary-foreground rounded-full flex items-center justify-center cursor-pointer hover:opacity-90 shadow-sm">
                <Camera className="w-3 h-3" />
                <input type="file" accept="image/*" className="hidden" onChange={async (e) => {
                  const file = e.target.files[0]
                  if (!file) return
                  const formData = new FormData()
                  formData.append('file', file)
                  const token = localStorage.getItem('token')
                  try {
                    const res = await fetch(`/api/vehicles/${id}/photo`, {
                      method: 'POST',
                      headers: { Authorization: `Bearer ${token}` },
                      body: formData,
                    })
                    if (!res.ok) throw new Error('Upload failed')
                    const result = await res.json()
                    setVehicle({ ...vehicle, photo_url: result.photo_url + '?t=' + Date.now() })
                  } catch (err) { alert(err.message) }
                  e.target.value = ''
                }} />
              </label>
            )}
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-bold text-foreground">{displayName || 'Unnamed Vehicle'}</h2>
              {isAdmin && (
                <Link to={`/fleet`} className="p-1.5 text-muted-foreground hover:text-foreground rounded-lg hover:bg-accent">
                  <Edit className="w-4 h-4" />
                </Link>
              )}
            </div>
            <div className="flex flex-wrap gap-4 mt-2 text-sm text-muted-foreground">
              {vehicle.serial_number && <span>S/N: {vehicle.serial_number}</span>}
              {vehicle.faa_registration && <span>FAA: {vehicle.faa_registration}</span>}
              {vehicle.acquired_date && <span>Acquired: {vehicle.acquired_date}</span>}
            </div>
            <span className={`inline-flex mt-2 px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[vehicle.status] || 'bg-zinc-500/15 text-zinc-400'}`}>
              {vehicle.status || 'unknown'}
            </span>
          </div>
        </div>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary/15 flex items-center justify-center text-primary"><Plane className="w-5 h-5" /></div>
          <div><p className="text-2xl font-bold text-foreground">{stats?.total_flights || 0}</p><p className="text-xs text-muted-foreground">Total Flights</p></div>
        </div>
        <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-500/15 flex items-center justify-center text-blue-400"><Clock className="w-5 h-5" /></div>
          <div><p className="text-2xl font-bold text-foreground">{formatHours(stats?.total_flight_hours * 3600 || 0)}</p><p className="text-xs text-muted-foreground">Total Hours</p></div>
        </div>
        <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-500/15 flex items-center justify-center text-emerald-400"><Calendar className="w-5 h-5" /></div>
          <div><p className="text-2xl font-bold text-foreground">{stats?.last_flight_date || 'Never'}</p><p className="text-xs text-muted-foreground">Last Flight</p></div>
        </div>
        <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-amber-500/15 flex items-center justify-center text-amber-400"><Battery className="w-5 h-5" /></div>
          <div><p className="text-2xl font-bold text-foreground">{activeBatteryCount}</p><p className="text-xs text-muted-foreground">Active Batteries</p></div>
        </div>
      </div>

      {/* Equipment History */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-border">
          <h3 className="font-semibold text-foreground">Equipment History</h3>
        </div>
        <div className="flex items-center gap-1 px-4 pt-3 overflow-x-auto">
          {equipTabs.map(tab => {
            const Icon = tab.icon
            return (
              <button
                key={tab.key}
                onClick={() => setEquipTab(tab.key)}
                className={`text-sm font-medium pb-2 border-b-2 transition-colors flex items-center gap-1.5 px-3 whitespace-nowrap ${
                  equipTab === tab.key
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                }`}
              >
                <Icon className="w-4 h-4" /> {tab.label}
              </button>
            )
          })}
        </div>
        <div className="p-4">
          {equipTab === 'batteries' && (
            <div className="space-y-2">
              {matchedBatteries.length > 0 ? matchedBatteries.map(({ serial, record }) => (
                <div key={serial} className="flex items-center justify-between px-3 py-2 bg-secondary/50 rounded-lg">
                  <div className="flex items-center gap-2">
                    <Battery className="w-4 h-4 text-muted-foreground" />
                    <span className="text-sm text-foreground font-medium">{serial}</span>
                    {record && (
                      <span className="text-xs text-muted-foreground">
                        {record.manufacturer} {record.model} | {record.cycle_count ?? '?'} cycles | {record.health_pct != null ? `${record.health_pct}%` : '?'} health
                      </span>
                    )}
                  </div>
                  {record && (
                    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[record.status] || 'bg-zinc-500/15 text-zinc-400'}`}>
                      {record.status}
                    </span>
                  )}
                </div>
              )) : (
                <p className="text-sm text-muted-foreground text-center py-4">No batteries found in flight records</p>
              )}
            </div>
          )}
          {equipTab === 'controllers' && (
            <div className="space-y-2">
              {controllers.length > 0 ? controllers.map(c => (
                <div key={c.id} className="flex items-center justify-between px-3 py-2 bg-secondary/50 rounded-lg">
                  <div className="flex items-center gap-2">
                    <Gamepad2 className="w-4 h-4 text-muted-foreground" />
                    <span className="text-sm text-foreground font-medium">{c.serial_number}</span>
                    <span className="text-xs text-muted-foreground">{c.manufacturer} {c.model}</span>
                  </div>
                  <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[c.status] || 'bg-zinc-500/15 text-zinc-400'}`}>
                    {c.status}
                  </span>
                </div>
              )) : (
                <p className="text-sm text-muted-foreground text-center py-4">No controllers found</p>
              )}
            </div>
          )}
          {equipTab === 'sensors' && (
            <div className="space-y-2">
              {sensors.length > 0 ? sensors.map(s => (
                <div key={s.id} className="flex items-center justify-between px-3 py-2 bg-secondary/50 rounded-lg">
                  <div className="flex items-center gap-2">
                    <Cpu className="w-4 h-4 text-muted-foreground" />
                    <span className="text-sm text-foreground font-medium">{s.name || s.serial_number}</span>
                    <span className="text-xs text-muted-foreground">{s.type} | {s.manufacturer} {s.model}</span>
                  </div>
                  <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[s.status] || 'bg-zinc-500/15 text-zinc-400'}`}>
                    {s.status}
                  </span>
                </div>
              )) : (
                <p className="text-sm text-muted-foreground text-center py-4">No sensors found</p>
              )}
            </div>
          )}
          {equipTab === 'attachments' && (
            <div className="space-y-2">
              {attachments.length > 0 ? attachments.map(a => (
                <div key={a.id} className="flex items-center justify-between px-3 py-2 bg-secondary/50 rounded-lg">
                  <div className="flex items-center gap-2">
                    <Paperclip className="w-4 h-4 text-muted-foreground" />
                    <span className="text-sm text-foreground font-medium">{a.name || a.serial_number}</span>
                    <span className="text-xs text-muted-foreground">{a.type} | {a.manufacturer} {a.model}</span>
                  </div>
                  <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[a.status] || 'bg-zinc-500/15 text-zinc-400'}`}>
                    {a.status}
                  </span>
                </div>
              )) : (
                <p className="text-sm text-muted-foreground text-center py-4">No attachments found</p>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Flight History */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-border">
          <h3 className="font-semibold text-foreground">Flight History</h3>
        </div>
        <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/30">
              <th className="text-left px-4 py-2 text-muted-foreground font-medium">Date</th>
              <th className="text-left px-4 py-2 text-muted-foreground font-medium">Pilot</th>
              <th className="text-left px-4 py-2 text-muted-foreground font-medium hidden md:table-cell">Purpose</th>
              <th className="text-left px-4 py-2 text-muted-foreground font-medium">Duration</th>
              <th className="text-left px-4 py-2 text-muted-foreground font-medium hidden md:table-cell">Battery</th>
              <th className="text-left px-4 py-2 text-muted-foreground font-medium hidden lg:table-cell">Location</th>
            </tr>
          </thead>
          <tbody>
            {flights.map(f => (
              <tr key={f.id} className="border-b border-border/50 hover:bg-accent/30">
                <td className="px-4 py-2 text-foreground">
                  <Link to={`/flights/${f.id}`} className="hover:text-primary">{f.date || '—'}</Link>
                </td>
                <td className="px-4 py-2 text-muted-foreground">
                  {f.pilot_id ? (
                    <Link to={`/pilots/${f.pilot_id}`} className="hover:text-primary">{f.pilot_name || `Pilot #${f.pilot_id}`}</Link>
                  ) : '—'}
                </td>
                <td className="px-4 py-2 text-muted-foreground hidden md:table-cell">{f.purpose || '—'}</td>
                <td className="px-4 py-2 text-muted-foreground">{formatDuration(f.duration_seconds)}</td>
                <td className="px-4 py-2 text-muted-foreground hidden md:table-cell">{f.battery_serial || '—'}</td>
                <td className="px-4 py-2 text-muted-foreground truncate max-w-[200px] hidden lg:table-cell">{f.takeoff_address || '—'}</td>
              </tr>
            ))}
            {flights.length === 0 && <tr><td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">No flights recorded</td></tr>}
          </tbody>
        </table>
        </div>
      </div>

      {/* Maintenance History */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center gap-2">
          <Wrench className="w-4 h-4 text-primary" />
          <h3 className="font-semibold text-foreground">Maintenance History</h3>
        </div>
        <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/30">
              <th className="text-left px-4 py-2 text-muted-foreground font-medium">Date</th>
              <th className="text-left px-4 py-2 text-muted-foreground font-medium">Description</th>
              <th className="text-left px-4 py-2 text-muted-foreground font-medium hidden md:table-cell">Type</th>
              <th className="text-left px-4 py-2 text-muted-foreground font-medium hidden md:table-cell">Performed By</th>
              <th className="text-right px-4 py-2 text-muted-foreground font-medium">Cost</th>
            </tr>
          </thead>
          <tbody>
            {maintenance.map(m => (
              <tr key={m.id} className="border-b border-border/50 hover:bg-accent/30">
                <td className="px-4 py-2 text-foreground">{m.date || m.performed_date || '—'}</td>
                <td className="px-4 py-2 text-muted-foreground">{m.description || '—'}</td>
                <td className="px-4 py-2 text-muted-foreground hidden md:table-cell">{m.maintenance_type || m.type || '—'}</td>
                <td className="px-4 py-2 text-muted-foreground hidden md:table-cell">{m.performed_by || '—'}</td>
                <td className="px-4 py-2 text-muted-foreground text-right">{m.cost != null ? `$${parseFloat(m.cost).toFixed(2)}` : '—'}</td>
              </tr>
            ))}
            {maintenance.length === 0 && <tr><td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">No maintenance records</td></tr>}
          </tbody>
        </table>
        </div>
      </div>

      {/* FAA Registration */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-primary" />
            <h3 className="font-semibold text-foreground">FAA Registration</h3>
          </div>
          {isAdmin && (
            <button
              onClick={() => setShowRegForm(!showRegForm)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-medium hover:opacity-90"
            >
              <Plus className="w-3.5 h-3.5" /> Add Registration
            </button>
          )}
        </div>

        {/* Current Registration Summary */}
        {(() => {
          const current = registrations.find(r => r.is_current)
          if (current) {
            const today = new Date()
            const expiry = current.expiry_date ? new Date(current.expiry_date) : null
            const daysUntil = expiry ? Math.ceil((expiry - today) / (1000 * 60 * 60 * 24)) : null
            const isExpired = daysUntil !== null && daysUntil < 0
            const isExpiringSoon = daysUntil !== null && daysUntil <= 90 && daysUntil >= 0
            return (
              <div className={`px-4 py-3 border-b border-border flex items-center gap-4 ${
                isExpired ? 'bg-red-500/5' : isExpiringSoon ? 'bg-amber-500/5' : 'bg-emerald-500/5'
              }`}>
                <div className="flex-1">
                  <p className="text-sm font-medium text-foreground">
                    {current.registration_number || 'No registration number'}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Registered: {current.registration_date || 'N/A'} | Expires: {current.expiry_date || 'N/A'}
                  </p>
                </div>
                <div className="text-right">
                  {daysUntil !== null && (
                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
                      isExpired ? 'bg-red-500/15 text-red-400' :
                      isExpiringSoon ? 'bg-amber-500/15 text-amber-400' :
                      'bg-emerald-500/15 text-emerald-400'
                    }`}>
                      {isExpired && <AlertTriangle className="w-3 h-3" />}
                      {isExpired ? `Expired ${Math.abs(daysUntil)}d ago` :
                       `${daysUntil}d until renewal`}
                    </span>
                  )}
                </div>
              </div>
            )
          }
          return null
        })()}

        {/* Add Registration Form */}
        {showRegForm && isAdmin && (
          <div className="px-4 py-3 border-b border-border bg-muted/20 space-y-2">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Registration #</label>
                <input type="text" value={regForm.registration_number}
                  onChange={e => setRegForm({...regForm, registration_number: e.target.value})}
                  placeholder="FA..."
                  className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Registration Date</label>
                <input type="date" value={regForm.registration_date}
                  onChange={e => setRegForm({...regForm, registration_date: e.target.value})}
                  className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Notes</label>
                <input type="text" value={regForm.notes}
                  onChange={e => setRegForm({...regForm, notes: e.target.value})}
                  placeholder="Optional"
                  className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
              </div>
            </div>
            <div className="flex gap-2">
              <button
                onClick={async () => {
                  try {
                    await api.post(`/vehicles/${id}/registrations`, {
                      registration_number: regForm.registration_number || null,
                      registration_date: regForm.registration_date || null,
                      notes: regForm.notes || null,
                    })
                    setRegForm({ registration_number: '', registration_date: '', notes: '' })
                    setShowRegForm(false)
                    loadRegistrations()
                  } catch (err) { alert(err.message) }
                }}
                className="px-4 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-medium hover:opacity-90"
              >
                Save Registration
              </button>
              <button onClick={() => setShowRegForm(false)}
                className="px-4 py-1.5 bg-secondary text-secondary-foreground rounded-lg text-xs hover:opacity-90">
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Registration History */}
        {registrations.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/30">
                  <th className="text-left px-4 py-2 text-muted-foreground font-medium">Reg #</th>
                  <th className="text-left px-4 py-2 text-muted-foreground font-medium">Registered</th>
                  <th className="text-left px-4 py-2 text-muted-foreground font-medium">Expires</th>
                  <th className="text-left px-4 py-2 text-muted-foreground font-medium">Status</th>
                  <th className="text-left px-4 py-2 text-muted-foreground font-medium hidden md:table-cell">Notes</th>
                  {isAdmin && <th className="text-right px-4 py-2 text-muted-foreground font-medium">Actions</th>}
                </tr>
              </thead>
              <tbody>
                {registrations.map(r => (
                  <tr key={r.id} className="border-b border-border/50 hover:bg-accent/30">
                    <td className="px-4 py-2 text-foreground font-medium">{r.registration_number || '--'}</td>
                    <td className="px-4 py-2 text-muted-foreground">{r.registration_date || '--'}</td>
                    <td className="px-4 py-2 text-muted-foreground">{r.expiry_date || '--'}</td>
                    <td className="px-4 py-2">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                        r.is_current ? 'bg-emerald-500/15 text-emerald-400' : 'bg-zinc-500/15 text-zinc-400'
                      }`}>
                        {r.is_current ? 'Current' : 'Previous'}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-muted-foreground hidden md:table-cell">{r.notes || '--'}</td>
                    {isAdmin && (
                      <td className="px-4 py-2 text-right">
                        <button onClick={async () => {
                          if (!confirm('Delete this registration?')) return
                          try {
                            await api.delete(`/vehicle-registrations/${r.id}`)
                            loadRegistrations()
                          } catch (err) { alert(err.message) }
                        }} className="p-1.5 text-muted-foreground hover:text-destructive rounded hover:bg-destructive/10">
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="px-4 py-8 text-center text-muted-foreground text-sm">No FAA registrations recorded</div>
        )}
      </div>

      {/* Documents */}
      <DocumentUpload entityType="vehicle" entityId={id} />
    </div>
  )
}
