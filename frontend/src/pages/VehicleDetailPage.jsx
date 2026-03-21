import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { formatHours, formatDuration } from '@/lib/utils'
import {
  ArrowLeft, Plane, Clock, Calendar, Battery, Edit,
  FileText, Wrench, Gamepad2, Cpu, Paperclip
} from 'lucide-react'

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
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [equipTab, setEquipTab] = useState('batteries')

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
      api.get(`/documents?entity_type=vehicle&entity_id=${id}`).catch(() => []),
    ]).then(([v, s, f, bat, ctrl, sens, att, maint, docs]) => {
      setVehicle(v)
      setStats(s)
      setFlights(f)
      setBatteries(bat)
      setControllers(ctrl)
      setSensors(sens)
      setAttachments(att)
      setMaintenance(maint)
      setDocuments(docs)
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
          <div className="w-16 h-16 rounded-2xl bg-primary/15 flex items-center justify-center text-primary">
            <Plane className="w-8 h-8" />
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

      {/* Documents */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center gap-2">
          <FileText className="w-4 h-4 text-primary" />
          <h3 className="font-semibold text-foreground">Documents</h3>
        </div>
        <div className="divide-y divide-border/50">
          {documents.map(doc => (
            <button
              key={doc.id}
              onClick={() => window.open(doc.view_url, '_blank')}
              className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-accent/30 transition-colors"
            >
              <FileText className="w-4 h-4 text-muted-foreground shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-foreground truncate">{doc.title || doc.filename}</p>
                <p className="text-xs text-muted-foreground">{doc.mime_type}</p>
              </div>
            </button>
          ))}
          {documents.length === 0 && (
            <div className="px-4 py-8 text-center text-muted-foreground text-sm">No documents uploaded</div>
          )}
        </div>
      </div>
    </div>
  )
}
