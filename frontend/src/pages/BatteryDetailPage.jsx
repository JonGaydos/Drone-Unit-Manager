import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { formatDuration } from '@/lib/utils'
import { STATUS_COLORS } from '@/lib/constants'
import {
  ArrowLeft, Battery, Clock, Wrench, Edit, Zap, Activity, Save, X, Loader2, Plus
} from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { QuadcopterIcon } from '@/components/icons/QuadcopterIcon'
import DocumentUpload from '@/components/DocumentUpload'

export default function BatteryDetailPage() {
  const { id } = useParams()
  const { isAdmin } = useAuth()
  const toast = useToast()
  const [battery, setBattery] = useState(null)
  const [stats, setStats] = useState(null)
  const [flights, setFlights] = useState([])
  const [maintenance, setMaintenance] = useState([])
  const [vehicles, setVehicles] = useState([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [editForm, setEditForm] = useState({})
  const [saving, setSaving] = useState(false)
  const [healthHistory, setHealthHistory] = useState([])
  const [batteryPilots, setBatteryPilots] = useState([])
  const [showReadingForm, setShowReadingForm] = useState(false)
  const [readingForm, setReadingForm] = useState({ health_pct: '', cycle_count: '', voltage: '', notes: '' })
  const [savingReading, setSavingReading] = useState(false)

  useEffect(() => {
    Promise.all([
      api.get(`/batteries/${id}`),
      api.get(`/batteries/${id}/stats`),
      api.get(`/batteries/${id}/flights`).catch(() => []),
      api.get(`/maintenance?entity_type=battery&entity_id=${id}`).catch(() => []),
      api.get('/vehicles').catch(() => []),
      api.get(`/batteries/${id}/health-history`).catch(() => []),
      api.get(`/batteries/${id}/pilots`).catch(() => []),
    ]).then(([b, s, batteryFlights, m, v, healthData, pilotsData]) => {
      setBattery(b)
      setStats(s)
      setFlights(Array.isArray(batteryFlights) ? batteryFlights : [])
      setMaintenance(m)
      setVehicles(v)
      setHealthHistory(healthData)
      setBatteryPilots(Array.isArray(pilotsData) ? pilotsData : [])
    }).catch(() => {}).finally(() => setLoading(false))
  }, [id])

  const startEditing = () => {
    setEditForm({
      serial_number: battery.serial_number || '',
      nickname: battery.nickname || '',
      manufacturer: battery.manufacturer || '',
      model: battery.model || '',
      vehicle_model: battery.vehicle_model || '',
      cycle_count: battery.cycle_count || 0,
      health_pct: battery.health_pct ?? '',
      status: battery.status || 'active',
      purchase_date: battery.purchase_date || '',
      notes: battery.notes || '',
    })
    setEditing(true)
  }

  const cancelEditing = () => {
    setEditForm({})
    setEditing(false)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const payload = { ...editForm }
      if (payload.health_pct === '') delete payload.health_pct
      else payload.health_pct = Number.parseFloat(payload.health_pct)
      payload.cycle_count = Number.parseInt(payload.cycle_count, 10) || 0
      if (!payload.purchase_date) delete payload.purchase_date
      const updated = await api.patch(`/batteries/${id}`, payload)
      setBattery(updated)
      setEditing(false)
    } catch (err) {
      toast.error(err.message)
    } finally {
      setSaving(false)
    }
  }

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
            {editing ? (
              <div className="space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label htmlFor="nickname" className="block text-xs font-medium text-muted-foreground mb-1">Nickname</label>
                    <input id="nickname" type="text" value={editForm.nickname} onChange={e => setEditForm({...editForm, nickname: e.target.value})}
                      className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                  </div>
                  <div>
                    <label htmlFor="serial-number" className="block text-xs font-medium text-muted-foreground mb-1">Serial Number</label>
                    <input id="serial-number" type="text" value={editForm.serial_number} onChange={e => setEditForm({...editForm, serial_number: e.target.value})}
                      className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                  </div>
                  <div>
                    <label htmlFor="manufacturer" className="block text-xs font-medium text-muted-foreground mb-1">Manufacturer</label>
                    <input id="manufacturer" type="text" value={editForm.manufacturer} onChange={e => setEditForm({...editForm, manufacturer: e.target.value})}
                      className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                  </div>
                  <div>
                    <label htmlFor="model" className="block text-xs font-medium text-muted-foreground mb-1">Model</label>
                    <input id="model" type="text" value={editForm.model} onChange={e => setEditForm({...editForm, model: e.target.value})}
                      className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                  </div>
                  <div>
                    <label htmlFor="vehicle-model" className="block text-xs font-medium text-muted-foreground mb-1">Vehicle Model</label>
                    <input id="vehicle-model" type="text" value={editForm.vehicle_model} onChange={e => setEditForm({...editForm, vehicle_model: e.target.value})}
                      className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                  </div>
                  <div>
                    <label htmlFor="status" className="block text-xs font-medium text-muted-foreground mb-1">Status</label>
                    <select id="status" value={editForm.status} onChange={e => setEditForm({...editForm, status: e.target.value})}
                      className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm">
                      <option value="active">Active</option>
                      <option value="inactive">Inactive</option>
                      <option value="maintenance">Maintenance</option>
                      <option value="retired">Retired</option>
                    </select>
                  </div>
                  <div>
                    <label htmlFor="cycle-count" className="block text-xs font-medium text-muted-foreground mb-1">Cycle Count</label>
                    <input id="cycle-count" type="number" min="0" value={editForm.cycle_count} onChange={e => setEditForm({...editForm, cycle_count: e.target.value})}
                      className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                  </div>
                  <div>
                    <label htmlFor="health" className="block text-xs font-medium text-muted-foreground mb-1">Health %</label>
                    <input id="health" type="number" min="0" max="100" step="0.1" value={editForm.health_pct} onChange={e => setEditForm({...editForm, health_pct: e.target.value})}
                      className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                  </div>
                  <div>
                    <label htmlFor="purchase-date" className="block text-xs font-medium text-muted-foreground mb-1">Purchase Date</label>
                    <input id="purchase-date" type="date" value={editForm.purchase_date} onChange={e => setEditForm({...editForm, purchase_date: e.target.value})}
                      className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                  </div>
                </div>
                <div>
                  <label htmlFor="notes" className="block text-xs font-medium text-muted-foreground mb-1">Notes</label>
                  <textarea id="notes" value={editForm.notes} onChange={e => setEditForm({...editForm, notes: e.target.value})}
                    className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm h-16 resize-none focus:outline-none focus:ring-2 focus:ring-ring" />
                </div>
                <div className="flex gap-2">
                  <button onClick={handleSave} disabled={saving}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50">
                    {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Save
                  </button>
                  <button onClick={cancelEditing}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90">
                    <X className="w-4 h-4" /> Cancel
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div className="flex items-center gap-3">
                  <h2 className="text-xl font-bold text-foreground">{displayName}</h2>
                  {isAdmin && (
                    <button onClick={startEditing} className="p-1.5 text-muted-foreground hover:text-foreground rounded-lg hover:bg-accent">
                      <Edit className="w-4 h-4" />
                    </button>
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
              </>
            )}
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
          <div className="w-10 h-10 rounded-xl bg-blue-500/15 flex items-center justify-center text-blue-400"><QuadcopterIcon className="w-5 h-5" /></div>
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

      {/* Pilots */}
      {batteryPilots.length > 0 && (
        <div className="bg-card border border-border rounded-xl p-4">
          <h3 className="text-sm font-semibold text-foreground mb-2">Pilots</h3>
          <div className="flex flex-wrap gap-2">
            {batteryPilots.map(p => (
              <Link key={p.id} to={`/pilots/${p.id}`} className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-secondary rounded-lg text-sm text-foreground hover:bg-accent/30 transition-colors">
                {p.full_name}
                {p.flight_count != null && <span className="text-xs text-muted-foreground">({p.flight_count} flights)</span>}
              </Link>
            ))}
          </div>
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
                <th className="text-left px-4 py-2 text-foreground font-medium">Date</th>
                <th className="text-left px-4 py-2 text-foreground font-medium">Pilot</th>
                <th className="text-left px-4 py-2 text-foreground font-medium hidden md:table-cell">Purpose</th>
                <th className="text-left px-4 py-2 text-foreground font-medium">Duration</th>
                <th className="text-left px-4 py-2 text-foreground font-medium hidden lg:table-cell">Location</th>
              </tr>
            </thead>
            <tbody>
              {flights.map(f => (
                <tr key={f.id} className="border-b border-border/50 hover:bg-accent/30">
                  <td className="px-4 py-2 text-foreground">
                    <Link to={`/flights/${f.id}`} className="text-primary hover:underline">{f.date || '--'}</Link>
                  </td>
                  <td className="px-4 py-2 text-foreground">
                    {f.pilot_id ? (
                      <Link to={`/pilots/${f.pilot_id}`} className="text-primary hover:underline">{f.pilot_name || `Pilot #${f.pilot_id}`}</Link>
                    ) : '--'}
                  </td>
                  <td className="px-4 py-2 text-foreground hidden md:table-cell">{f.purpose || '--'}</td>
                  <td className="px-4 py-2 text-foreground">{formatDuration(f.duration_seconds)}</td>
                  <td className="px-4 py-2 text-foreground truncate max-w-[200px] hidden lg:table-cell">{f.takeoff_address || '--'}</td>
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
                <th className="text-left px-4 py-2 text-foreground font-medium">Date</th>
                <th className="text-left px-4 py-2 text-foreground font-medium">Description</th>
                <th className="text-left px-4 py-2 text-foreground font-medium hidden md:table-cell">Type</th>
                <th className="text-left px-4 py-2 text-foreground font-medium hidden md:table-cell">Performed By</th>
                <th className="text-right px-4 py-2 text-foreground font-medium">Cost</th>
              </tr>
            </thead>
            <tbody>
              {maintenance.map(m => (
                <tr key={m.id} className="border-b border-border/50 hover:bg-accent/30">
                  <td className="px-4 py-2 text-foreground">{m.date || m.performed_date || '--'}</td>
                  <td className="px-4 py-2 text-foreground">{m.description || '--'}</td>
                  <td className="px-4 py-2 text-foreground hidden md:table-cell">{m.maintenance_type || m.type || '--'}</td>
                  <td className="px-4 py-2 text-foreground hidden md:table-cell">{m.performed_by || '--'}</td>
                  <td className="px-4 py-2 text-foreground text-right">{m.cost != null ? `$${Number.parseFloat(m.cost).toFixed(2)}` : '--'}</td>
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

      {/* Battery Health History */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="flex items-center justify-between p-5 border-b border-border">
          <h3 className="font-semibold text-foreground">Health History</h3>
          {isAdmin && (
            <button
              onClick={() => setShowReadingForm(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90"
            >
              <Plus className="w-4 h-4" /> Record Reading
            </button>
          )}
        </div>
        {healthHistory.length > 0 ? (
          <div className="p-5">
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={healthHistory.map(r => ({
                date: r.recorded_at ? new Date(r.recorded_at).toLocaleDateString() : '',
                health: r.health_pct,
                cycles: r.cycle_count,
              }))}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                <XAxis dataKey="date" tick={{ fill: 'var(--muted-fg)', fontSize: 12 }} />
                <YAxis yAxisId="left" domain={[0, 100]} tick={{ fill: 'var(--muted-fg)', fontSize: 12 }} label={{ value: 'Health %', angle: -90, position: 'insideLeft', fill: 'var(--muted-fg)', fontSize: 12 }} />
                <YAxis yAxisId="right" orientation="right" tick={{ fill: 'var(--muted-fg)', fontSize: 12 }} label={{ value: 'Cycles', angle: 90, position: 'insideRight', fill: 'var(--muted-fg)', fontSize: 12 }} />
                <Tooltip contentStyle={{ background: 'var(--card)', border: '1px solid var(--border-color)', borderRadius: '8px', color: 'var(--fg)' }} />
                <Legend />
                <Line yAxisId="left" type="monotone" dataKey="health" stroke="#10b981" strokeWidth={2} dot={{ r: 4 }} name="Health %" />
                <Line yAxisId="right" type="monotone" dataKey="cycles" stroke="#3b82f6" strokeWidth={2} dot={{ r: 4 }} name="Cycles" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="p-8 text-center text-muted-foreground text-sm">
            No health readings recorded yet. Click "Record Reading" to add one.
          </div>
        )}
      </div>

      {showReadingForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setShowReadingForm(false)}>
          <div className="bg-card border border-border rounded-xl p-6 w-full max-w-md shadow-xl" onClick={e => e.stopPropagation()}>
            <h2 className="text-lg font-semibold text-foreground mb-4">Record Battery Health Reading</h2>
            <div className="space-y-3">
              <div>
                <label htmlFor="health-1" className="block text-sm font-medium text-foreground mb-1">Health %</label>
                <input id="health-1" type="number" min="0" max="100" value={readingForm.health_pct} onChange={e => setReadingForm({...readingForm, health_pct: e.target.value})}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" placeholder="0-100" />
              </div>
              <div>
                <label htmlFor="cycle-count-1" className="block text-sm font-medium text-foreground mb-1">Cycle Count</label>
                <input id="cycle-count-1" type="number" min="0" value={readingForm.cycle_count} onChange={e => setReadingForm({...readingForm, cycle_count: e.target.value})}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
              <div>
                <label htmlFor="voltage" className="block text-sm font-medium text-foreground mb-1">Voltage</label>
                <input id="voltage" type="number" step="0.1" value={readingForm.voltage} onChange={e => setReadingForm({...readingForm, voltage: e.target.value})}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
              <div>
                <label htmlFor="notes-1" className="block text-sm font-medium text-foreground mb-1">Notes</label>
                <input id="notes-1" type="text" value={readingForm.notes} onChange={e => setReadingForm({...readingForm, notes: e.target.value})}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
            </div>
            <div className="flex gap-2 mt-4">
              <button
                onClick={async () => {
                  setSavingReading(true)
                  try {
                    const data = {}
                    if (readingForm.health_pct) data.health_pct = Number.parseFloat(readingForm.health_pct)
                    if (readingForm.cycle_count) data.cycle_count = Number.parseInt(readingForm.cycle_count, 10)
                    if (readingForm.voltage) data.voltage = Number.parseFloat(readingForm.voltage)
                    if (readingForm.notes) data.notes = readingForm.notes
                    await api.post(`/batteries/${id}/readings`, data)
                    toast.success('Health reading recorded')
                    setShowReadingForm(false)
                    setReadingForm({ health_pct: '', cycle_count: '', voltage: '', notes: '' })
                    // Reload health history
                    const hh = await api.get(`/batteries/${id}/health-history`).catch(() => [])
                    setHealthHistory(hh)
                    // Reload battery (health_pct may have updated)
                    const b = await api.get(`/batteries/${id}`)
                    setBattery(b)
                  } catch (err) { toast.error(err.message) }
                  finally { setSavingReading(false) }
                }}
                disabled={savingReading}
                className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {savingReading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Save Reading'}
              </button>
              <button onClick={() => setShowReadingForm(false)} className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm">Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
