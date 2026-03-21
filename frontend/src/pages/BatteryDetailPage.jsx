import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { formatHours, formatDuration } from '@/lib/utils'
import {
  ArrowLeft, Battery, Clock, Plane, Wrench, Edit, Zap, Activity
} from 'lucide-react'
import DocumentUpload from '@/components/DocumentUpload'

const STATUS_COLORS = {
  active: 'bg-emerald-500/15 text-emerald-400',
  charging: 'bg-blue-500/15 text-blue-400',
  maintenance: 'bg-amber-500/15 text-amber-400',
  retired: 'bg-red-500/15 text-red-400',
  damaged: 'bg-red-500/15 text-red-400',
}

export default function BatteryDetailPage() {
  const { id } = useParams()
  const { isAdmin } = useAuth()
  const [battery, setBattery] = useState(null)
  const [stats, setStats] = useState(null)
  const [flights, setFlights] = useState([])
  const [maintenance, setMaintenance] = useState([])
  const [vehicles, setVehicles] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      api.get(`/batteries/${id}`),
      api.get(`/batteries/${id}/stats`),
      api.get('/flights').catch(() => []),
      api.get(`/maintenance?entity_type=battery&entity_id=${id}`).catch(() => []),
      api.get('/vehicles').catch(() => []),
    ]).then(([b, s, f, m, v]) => {
      setBattery(b)
      setStats(s)
      // Filter flights by battery serial
      const batteryFlights = f.filter(fl => fl.battery_serial === b.serial_number)
      setFlights(batteryFlights)
      setMaintenance(m)
      setVehicles(v)
    }).catch(console.error).finally(() => setLoading(false))
  }, [id])

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
  if (!battery) return <div className="text-center text-muted-foreground py-12">Battery not found</div>

  const displayName = battery.nickname || battery.serial_number
  const linkedVehicle = battery.vehicle_model
    ? vehicles.find(v => v.model && v.model.toLowerCase() === battery.vehicle_model.toLowerCase())
    : null

  return (
    <div className="space-y-6">
      <Link to="/fleet" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="w-4 h-4" /> Back to Fleet
      </Link>

      {/* Header */}
      <div className="bg-card border border-border rounded-xl p-6">
        <div className="flex items-start gap-4">
          <div className="w-16 h-16 rounded-2xl bg-primary/15 flex items-center justify-center text-primary shrink-0">
            <Battery className="w-8 h-8" />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-bold text-foreground">{displayName}</h2>
              {isAdmin && (
                <Link to="/fleet" className="p-1.5 text-muted-foreground hover:text-foreground rounded-lg hover:bg-accent">
                  <Edit className="w-4 h-4" />
                </Link>
              )}
            </div>
            <div className="flex flex-wrap gap-4 mt-2 text-sm text-muted-foreground">
              {battery.manufacturer && <span>{battery.manufacturer}</span>}
              {battery.model && <span>{battery.model}</span>}
              <span>S/N: {battery.serial_number}</span>
              {battery.purchase_date && <span>Purchased: {battery.purchase_date}</span>}
            </div>
            <span className={`inline-flex mt-2 px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[battery.status] || 'bg-zinc-500/15 text-zinc-400'}`}>
              {battery.status || 'unknown'}
            </span>
          </div>
        </div>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary/15 flex items-center justify-center text-primary"><Zap className="w-5 h-5" /></div>
          <div><p className="text-2xl font-bold text-foreground">{battery.cycle_count || 0}</p><p className="text-xs text-muted-foreground">Cycle Count</p></div>
        </div>
        <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-500/15 flex items-center justify-center text-emerald-400"><Activity className="w-5 h-5" /></div>
          <div><p className="text-2xl font-bold text-foreground">{battery.health_pct != null ? `${battery.health_pct}%` : '--'}</p><p className="text-xs text-muted-foreground">Health</p></div>
        </div>
        <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-500/15 flex items-center justify-center text-blue-400"><Plane className="w-5 h-5" /></div>
          <div><p className="text-2xl font-bold text-foreground">{stats?.total_flights || 0}</p><p className="text-xs text-muted-foreground">Total Flights</p></div>
        </div>
        <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-amber-500/15 flex items-center justify-center text-amber-400"><Clock className="w-5 h-5" /></div>
          <div><p className="text-2xl font-bold text-foreground">{stats?.total_hours != null ? `${stats.total_hours}h` : '--'}</p><p className="text-xs text-muted-foreground">Total Hours</p></div>
        </div>
      </div>

      {/* Linked Vehicle */}
      {battery.vehicle_model && (
        <div className="bg-card border border-border rounded-xl p-4">
          <h3 className="text-sm font-semibold text-foreground mb-2">Vehicle Model</h3>
          <p className="text-sm text-muted-foreground">
            {battery.vehicle_model}
            {linkedVehicle && (
              <>
                {' — '}
                <Link to={`/fleet/vehicles/${linkedVehicle.id}`} className="text-primary hover:underline">
                  {linkedVehicle.nickname || `${linkedVehicle.manufacturer} ${linkedVehicle.model}`}
                </Link>
              </>
            )}
          </p>
        </div>
      )}

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
                <th className="text-left px-4 py-2 text-muted-foreground font-medium hidden lg:table-cell">Location</th>
              </tr>
            </thead>
            <tbody>
              {flights.map(f => (
                <tr key={f.id} className="border-b border-border/50 hover:bg-accent/30">
                  <td className="px-4 py-2 text-foreground">
                    <Link to={`/flights/${f.id}`} className="hover:text-primary">{f.date || '--'}</Link>
                  </td>
                  <td className="px-4 py-2 text-muted-foreground">
                    {f.pilot_id ? (
                      <Link to={`/pilots/${f.pilot_id}`} className="hover:text-primary">{f.pilot_name || `Pilot #${f.pilot_id}`}</Link>
                    ) : '--'}
                  </td>
                  <td className="px-4 py-2 text-muted-foreground hidden md:table-cell">{f.purpose || '--'}</td>
                  <td className="px-4 py-2 text-muted-foreground">{formatDuration(f.duration_seconds)}</td>
                  <td className="px-4 py-2 text-muted-foreground truncate max-w-[200px] hidden lg:table-cell">{f.takeoff_address || '--'}</td>
                </tr>
              ))}
              {flights.length === 0 && <tr><td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">No flights recorded for this battery</td></tr>}
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
                  <td className="px-4 py-2 text-foreground">{m.date || m.performed_date || '--'}</td>
                  <td className="px-4 py-2 text-muted-foreground">{m.description || '--'}</td>
                  <td className="px-4 py-2 text-muted-foreground hidden md:table-cell">{m.maintenance_type || m.type || '--'}</td>
                  <td className="px-4 py-2 text-muted-foreground hidden md:table-cell">{m.performed_by || '--'}</td>
                  <td className="px-4 py-2 text-muted-foreground text-right">{m.cost != null ? `$${parseFloat(m.cost).toFixed(2)}` : '--'}</td>
                </tr>
              ))}
              {maintenance.length === 0 && <tr><td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">No maintenance records</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {/* Notes */}
      {battery.notes && (
        <div className="bg-card border border-border rounded-xl p-4">
          <h3 className="text-sm font-semibold text-foreground mb-2">Notes</h3>
          <p className="text-sm text-muted-foreground whitespace-pre-wrap">{battery.notes}</p>
        </div>
      )}

      {/* Documents */}
      <DocumentUpload entityType="battery" entityId={id} />
    </div>
  )
}
