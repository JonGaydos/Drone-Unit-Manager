import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { formatDuration, normalizeDateValue } from '@/lib/utils'
import { ArrowLeft, MapPin, Clock, Gauge, Battery, Plane, Save } from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'

const tooltipStyle = {
  contentStyle: { background: 'var(--card)', border: '1px solid var(--border-color)', borderRadius: '8px', color: 'var(--fg)' },
}

export default function FlightDetailPage() {
  const { id } = useParams()
  const [flight, setFlight] = useState(null)
  const [telemetry, setTelemetry] = useState([])
  const [pilots, setPilots] = useState([])
  const [vehicles, setVehicles] = useState([])
  const [purposes, setPurposes] = useState([])
  const [editing, setEditing] = useState(false)
  const [editForm, setEditForm] = useState({})
  const [loading, setLoading] = useState(true)
  const { isAdmin } = useAuth()

  const initEditForm = (f) => {
    setEditForm({
      pilot_id: f.pilot_id || '',
      vehicle_id: f.vehicle_id || '',
      purpose: f.purpose || '',
      date: f.date || '',
      takeoff_time: f.takeoff_time ? f.takeoff_time.slice(0, 16) : '',
      landing_time: f.landing_time ? f.landing_time.slice(0, 16) : '',
      duration_seconds: f.duration_seconds || '',
      takeoff_address: f.takeoff_address || '',
      case_number: f.case_number || '',
      battery_serial: f.battery_serial || '',
      sensor_package: f.sensor_package || '',
      attachment_top: f.attachment_top || '',
      attachment_bottom: f.attachment_bottom || '',
      attachment_left: f.attachment_left || '',
      attachment_right: f.attachment_right || '',
      carrier: f.carrier || '',
      notes: f.notes || '',
      review_status: f.review_status || 'needs_review',
    })
  }

  useEffect(() => {
    Promise.all([
      api.get(`/flights/${id}`),
      api.get(`/telemetry/flight/${id}`).catch(() => []),
      api.get('/pilots'),
      api.get('/vehicles'),
      api.get('/flights/purposes/list'),
    ]).then(([f, t, p, v, pu]) => {
      setFlight(f)
      setTelemetry(Array.isArray(t) ? t : [])
      setPilots(p)
      setVehicles(v)
      setPurposes(pu)
      initEditForm(f)
    }).catch(console.error).finally(() => setLoading(false))
  }, [id])

  const handleSave = async () => {
    try {
      const data = { ...editForm }
      if (data.pilot_id) data.pilot_id = parseInt(data.pilot_id)
      else data.pilot_id = null
      if (data.vehicle_id) data.vehicle_id = parseInt(data.vehicle_id)
      else data.vehicle_id = null
      if (data.duration_seconds) data.duration_seconds = parseInt(data.duration_seconds)
      else delete data.duration_seconds
      // Clean empty strings
      Object.keys(data).forEach(k => { if (data[k] === '') data[k] = null })
      const updated = await api.patch(`/flights/${id}`, data)
      setFlight(updated)
      setEditing(false)
    } catch (err) { alert(err.message) }
  }

  const handleApprove = async () => {
    try {
      const updated = await api.patch(`/flights/${id}`, { review_status: 'reviewed', pilot_confirmed: true })
      setFlight(updated)
    } catch (err) { alert(err.message) }
  }

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
  if (!flight) return <div className="text-center text-muted-foreground py-12">Flight not found</div>

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Link to="/flights" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="w-4 h-4" /> Back to Flights
        </Link>
        <div className="flex gap-2">
          {flight.review_status === 'needs_review' && isAdmin && (
            <button onClick={handleApprove} className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:opacity-90">
              Approve Flight
            </button>
          )}
          {isAdmin && !editing && (
            <button onClick={() => { initEditForm(flight); setEditing(true) }} className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90">
              Edit
            </button>
          )}
        </div>
      </div>

      {/* Flight Info */}
      <div className="bg-card border border-border rounded-xl p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-12 h-12 rounded-xl bg-primary/15 flex items-center justify-center text-primary">
            <Plane className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-foreground">Flight on {flight.date || 'Unknown Date'}</h2>
            <div className="flex items-center gap-3 text-sm text-muted-foreground">
              {flight.external_id && <span className="font-mono text-xs bg-secondary px-2 py-0.5 rounded" title={flight.external_id}>ID: {flight.external_id.slice(0, 12)}{flight.external_id.length > 12 ? '...' : ''}</span>}
              <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                flight.review_status === 'needs_review' ? 'bg-amber-500/15 text-amber-400' : 'bg-emerald-500/15 text-emerald-400'
              }`}>{flight.review_status === 'needs_review' ? 'Needs Review' : 'Reviewed'}</span>
              {flight.api_provider && <span>Source: {flight.api_provider}</span>}
            </div>
          </div>
        </div>

        {editing ? (
          <div className="space-y-3 border-t border-border pt-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Pilot</label>
                <select value={editForm.pilot_id} onChange={e => setEditForm({...editForm, pilot_id: e.target.value})}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
                  <option value="">Unassigned</option>
                  {pilots.map(p => <option key={p.id} value={p.id}>{p.full_name}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Vehicle</label>
                <select value={editForm.vehicle_id} onChange={e => setEditForm({...editForm, vehicle_id: e.target.value})}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
                  <option value="">Unassigned</option>
                  {vehicles.map(v => <option key={v.id} value={v.id}>{v.manufacturer} {v.model}</option>)}
                </select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Purpose</label>
                <select value={editForm.purpose} onChange={e => setEditForm({...editForm, purpose: e.target.value})}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
                  <option value="">None</option>
                  {purposes.map(p => <option key={p.id} value={p.name}>{p.name}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Date</label>
                <input type="date" value={editForm.date} onChange={e => setEditForm({...editForm, date: e.target.value})}
                  onBlur={e => { const n = normalizeDateValue(e.target.value); if (n !== e.target.value) setEditForm(prev => ({...prev, date: n})) }}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Takeoff Time</label>
                <input type="datetime-local" value={editForm.takeoff_time} onChange={e => setEditForm({...editForm, takeoff_time: e.target.value})}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Landing Time</label>
                <input type="datetime-local" value={editForm.landing_time} onChange={e => setEditForm({...editForm, landing_time: e.target.value})}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Duration (seconds)</label>
                <input type="number" value={editForm.duration_seconds} onChange={e => setEditForm({...editForm, duration_seconds: e.target.value})}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Status</label>
                <select value={editForm.review_status} onChange={e => setEditForm({...editForm, review_status: e.target.value})}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
                  <option value="needs_review">Needs Review</option>
                  <option value="reviewed">Reviewed</option>
                </select>
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Takeoff Address / Location</label>
              <input type="text" value={editForm.takeoff_address} onChange={e => setEditForm({...editForm, takeoff_address: e.target.value})}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Case Number</label>
              <input type="text" value={editForm.case_number} onChange={e => setEditForm({...editForm, case_number: e.target.value})}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Battery Serial</label>
                <input type="text" value={editForm.battery_serial} onChange={e => setEditForm({...editForm, battery_serial: e.target.value})}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Sensor Package</label>
                <input type="text" value={editForm.sensor_package} onChange={e => setEditForm({...editForm, sensor_package: e.target.value})}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Attachment (TOP)</label>
                <input type="text" value={editForm.attachment_top} onChange={e => setEditForm({...editForm, attachment_top: e.target.value})}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Attachment (BOTTOM)</label>
                <input type="text" value={editForm.attachment_bottom} onChange={e => setEditForm({...editForm, attachment_bottom: e.target.value})}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Attachment (LEFT)</label>
                <input type="text" value={editForm.attachment_left} onChange={e => setEditForm({...editForm, attachment_left: e.target.value})}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Attachment (RIGHT)</label>
                <input type="text" value={editForm.attachment_right} onChange={e => setEditForm({...editForm, attachment_right: e.target.value})}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Carrier(s)</label>
              <input type="text" value={editForm.carrier} onChange={e => setEditForm({...editForm, carrier: e.target.value})}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Notes</label>
              <textarea value={editForm.notes} onChange={e => setEditForm({...editForm, notes: e.target.value})}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm h-20 resize-none" />
            </div>
            <div className="flex gap-2">
              <button onClick={handleSave} className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90">
                <Save className="w-4 h-4" /> Save
              </button>
              <button onClick={() => { setEditing(false); initEditForm(flight) }} className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm">Cancel</button>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 border-t border-border pt-4">
            <div><p className="text-xs text-muted-foreground">Pilot</p><p className="text-sm text-foreground">{flight.pilot_name || 'Unassigned'}</p></div>
            <div><p className="text-xs text-muted-foreground">Vehicle</p><p className="text-sm text-foreground">{flight.vehicle_name || '—'}</p></div>
            <div><p className="text-xs text-muted-foreground">Purpose</p><p className="text-sm text-foreground">{flight.purpose || '—'}</p></div>
            <div><p className="text-xs text-muted-foreground">Duration</p><p className="text-sm text-foreground">{formatDuration(flight.duration_seconds)}</p></div>
            <div><p className="text-xs text-muted-foreground">Takeoff</p><p className="text-sm text-foreground">{flight.takeoff_address || '—'}</p></div>
            <div><p className="text-xs text-muted-foreground">Max Altitude</p><p className="text-sm text-foreground">{flight.max_altitude_m ? `${flight.max_altitude_m.toFixed(1)}m` : '—'}</p></div>
            <div><p className="text-xs text-muted-foreground">Max Speed</p><p className="text-sm text-foreground">{flight.max_speed_mps ? `${flight.max_speed_mps.toFixed(1)} m/s` : '—'}</p></div>
            <div><p className="text-xs text-muted-foreground">Case #</p><p className="text-sm text-foreground">{flight.case_number || '—'}</p></div>
            <div><p className="text-xs text-muted-foreground">Battery Serial</p><p className="text-sm text-foreground">{flight.battery_serial || '—'}</p></div>
            <div><p className="text-xs text-muted-foreground">Sensor Package</p><p className="text-sm text-foreground">{flight.sensor_package || '—'}</p></div>
            <div><p className="text-xs text-muted-foreground">Carrier(s)</p><p className="text-sm text-foreground">{flight.carrier || '—'}</p></div>
            <div><p className="text-xs text-muted-foreground">&nbsp;</p></div>
            {(flight.attachment_top || flight.attachment_bottom || flight.attachment_left || flight.attachment_right) && (
              <>
                <div><p className="text-xs text-muted-foreground">Attachment (TOP)</p><p className="text-sm text-foreground">{flight.attachment_top || '—'}</p></div>
                <div><p className="text-xs text-muted-foreground">Attachment (BOTTOM)</p><p className="text-sm text-foreground">{flight.attachment_bottom || '—'}</p></div>
                <div><p className="text-xs text-muted-foreground">Attachment (LEFT)</p><p className="text-sm text-foreground">{flight.attachment_left || '—'}</p></div>
                <div><p className="text-xs text-muted-foreground">Attachment (RIGHT)</p><p className="text-sm text-foreground">{flight.attachment_right || '—'}</p></div>
              </>
            )}
            {flight.notes && <div className="col-span-2 md:col-span-4"><p className="text-xs text-muted-foreground">Notes</p><p className="text-sm text-foreground">{flight.notes}</p></div>}
          </div>
        )}
      </div>

      {/* Telemetry Charts */}
      {telemetry.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="bg-card border border-border rounded-xl p-5">
            <h3 className="text-sm font-semibold text-foreground mb-4">Altitude (m)</h3>
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={telemetry}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                <XAxis dataKey="elapsed_s" stroke="var(--muted-fg)" fontSize={11} label={{ value: 'seconds', position: 'bottom', fill: 'var(--muted-fg)', fontSize: 11 }} />
                <YAxis stroke="var(--muted-fg)" fontSize={11} />
                <Tooltip {...tooltipStyle} />
                <Line type="monotone" dataKey="altitude_m" stroke="#6366f1" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="bg-card border border-border rounded-xl p-5">
            <h3 className="text-sm font-semibold text-foreground mb-4">Speed (m/s)</h3>
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={telemetry}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                <XAxis dataKey="elapsed_s" stroke="var(--muted-fg)" fontSize={11} />
                <YAxis stroke="var(--muted-fg)" fontSize={11} />
                <Tooltip {...tooltipStyle} />
                <Line type="monotone" dataKey="speed_mps" stroke="#3b82f6" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="bg-card border border-border rounded-xl p-5">
            <h3 className="text-sm font-semibold text-foreground mb-4">Battery (%)</h3>
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={telemetry}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                <XAxis dataKey="elapsed_s" stroke="var(--muted-fg)" fontSize={11} />
                <YAxis stroke="var(--muted-fg)" fontSize={11} domain={[0, 100]} />
                <Tooltip {...tooltipStyle} />
                <Line type="monotone" dataKey="battery_pct" stroke="#10b981" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="bg-card border border-border rounded-xl p-5">
            <h3 className="text-sm font-semibold text-foreground mb-4">Heading (deg)</h3>
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={telemetry}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                <XAxis dataKey="elapsed_s" stroke="var(--muted-fg)" fontSize={11} />
                <YAxis stroke="var(--muted-fg)" fontSize={11} domain={[0, 360]} />
                <Tooltip {...tooltipStyle} />
                <Line type="monotone" dataKey="heading_deg" stroke="#f59e0b" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {telemetry.length === 0 && (
        <div className="bg-card border border-border rounded-xl p-8 text-center text-muted-foreground">
          <MapPin className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p>No telemetry data available for this flight.</p>
          <p className="text-xs mt-1">Telemetry will be fetched automatically when Skydio API sync is configured.</p>
        </div>
      )}
    </div>
  )
}
