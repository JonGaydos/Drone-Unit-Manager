import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { formatDuration, normalizeDateValue, metersToFeet, mpsToMph } from '@/lib/utils'
import { sortByName, sortVehicles, sortPilotsActiveFirst, vehicleDisplayName } from '@/lib/formatters'
import { ArrowLeft, MapPin, Clock, Gauge, Battery, Save, RefreshCw, Loader2, Download } from 'lucide-react'
import { QuadcopterIcon } from '@/components/icons/QuadcopterIcon'
import { FlightPathMap } from '@/components/FlightMap'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'

const tooltipStyle = {
  contentStyle: { background: 'var(--card)', border: '1px solid var(--border-color)', borderRadius: '8px', color: 'var(--fg)' },
}

export default function FlightDetailPage() {
  const { id } = useParams()
  const toast = useToast()
  const [flight, setFlight] = useState(null)
  const [telemetry, setTelemetry] = useState([])
  const [pilots, setPilots] = useState([])
  const [vehicles, setVehicles] = useState([])
  const [purposes, setPurposes] = useState([])
  const [batteries, setBatteries] = useState([])
  const [sensors, setSensors] = useState([])
  const [attachments, setAttachments] = useState([])
  const [editing, setEditing] = useState(false)
  const [editForm, setEditForm] = useState({})
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshResult, setRefreshResult] = useState(null)
  const { isAdmin, isSupervisor } = useAuth()

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
      api.get('/batteries').catch(() => []),
      api.get('/sensors').catch(() => []),
      api.get('/attachments').catch(() => []),
    ]).then(([f, t, p, v, pu, bats, sens, atts]) => {
      setFlight(f)
      setTelemetry(Array.isArray(t) ? t : [])
      setPilots(p)
      setVehicles(v)
      setPurposes(pu)
      setBatteries(bats)
      setSensors(sens)
      setAttachments(atts)
      initEditForm(f)
    }).catch(() => {}).finally(() => setLoading(false))
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
    } catch (err) { toast.error(err.message) }
  }

  const handleApprove = async () => {
    try {
      const updated = await api.patch(`/flights/${id}`, { review_status: 'reviewed', pilot_confirmed: true })
      setFlight(updated)
    } catch (err) { toast.error(err.message) }
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
          {flight.has_telemetry && (
            <>
              <button
                onClick={() => api.download(`/export/flights/${flight.id}/gpx`)}
                className="flex items-center gap-1.5 px-3 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90"
                title="Download flight path as GPX"
              >
                <Download className="w-4 h-4" /> GPX
              </button>
              <button
                onClick={() => api.download(`/export/flights/${flight.id}/kml`)}
                className="flex items-center gap-1.5 px-3 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90"
                title="Download flight path as KML for Google Earth"
              >
                <Download className="w-4 h-4" /> KML
              </button>
            </>
          )}
          {flight.review_status === 'needs_review' && isAdmin && (
            <button onClick={handleApprove} className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:opacity-90">
              Approve Flight
            </button>
          )}
          {isAdmin && !editing && flight.external_id && (
            <button
              onClick={async () => {
                setRefreshing(true)
                setRefreshResult(null)
                try {
                  const result = await api.post(`/flights/${flight.id}/refresh`, {})
                  setRefreshResult(result)
                  toast.success(`Refreshed: ${result.updated_fields.length} fields updated, ${result.telemetry_points} telemetry points`)
                  // Reload flight data
                  const [fData, tData] = await Promise.all([
                    api.get(`/flights/${id}`),
                    api.get(`/telemetry/flight/${id}`).catch(() => []),
                  ])
                  setFlight(fData)
                  setTelemetry(tData)
                } catch (err) {
                  toast.error(err.message)
                } finally {
                  setRefreshing(false)
                }
              }}
              disabled={refreshing}
              className="flex items-center gap-2 px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90 disabled:opacity-50"
              title="Fetch latest data from Skydio API for this flight"
            >
              {refreshing ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
              Refresh from API
            </button>
          )}
          {isAdmin && !editing && (
            <button onClick={() => { initEditForm(flight); setEditing(true) }} className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90">
              Edit
            </button>
          )}
        </div>
      </div>

      {refreshResult && (
        <div className="bg-blue-500/10 border border-blue-500/30 text-blue-400 rounded-lg p-4">
          <p className="font-medium mb-1">API Refresh Result</p>
          <p className="text-sm">Updated: {refreshResult.updated_fields.join(', ') || 'none'}</p>
          <p className="text-sm">Telemetry points: {refreshResult.telemetry_points}</p>
          <p className="text-sm mt-1 text-xs text-muted-foreground">API keys returned: {refreshResult.api_keys_returned?.join(', ')}</p>
        </div>
      )}

      {/* Flight Info */}
      <div className="bg-card border border-border rounded-xl p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-12 h-12 rounded-xl bg-primary/15 flex items-center justify-center text-primary">
            <QuadcopterIcon className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-foreground">Flight on {flight.date || 'Unknown Date'}</h2>
            <div className="flex items-center gap-3 text-sm text-muted-foreground">
              {flight.external_id && <span className="font-mono text-xs bg-secondary px-2 py-0.5 rounded" title={flight.external_id}>ID: {flight.external_id.slice(0, 12)}{flight.external_id.length > 12 ? '...' : ''}</span>}
              <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                flight.review_status === 'needs_review' ? 'bg-amber-500/15 text-amber-400' : 'bg-emerald-500/15 text-emerald-400'
              }`}>{flight.review_status === 'needs_review' ? 'Needs Review' : 'Reviewed'}</span>
              {isSupervisor && (
                <button
                  onClick={async () => {
                    try {
                      await api.patch(`/flights/${flight.id}/telemetry-status`, { telemetry_synced: !flight.telemetry_synced })
                      const updated = await api.get(`/flights/${id}`)
                      setFlight(updated)
                      toast.success(`Telemetry ${!flight.telemetry_synced ? 'marked as synced' : 'marked as pending'}`)
                    } catch (err) { toast.error(err.message) }
                  }}
                  className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium cursor-pointer transition-colors ${
                    flight.telemetry_synced
                      ? 'bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25'
                      : 'bg-zinc-500/15 text-zinc-400 hover:bg-zinc-500/25'
                  }`}
                  title={flight.telemetry_synced ? 'Click to mark telemetry as pending' : 'Click to mark telemetry as synced'}
                >
                  <span className={`w-2 h-2 rounded-full ${flight.telemetry_synced ? 'bg-emerald-400' : 'bg-zinc-500'}`} />
                  {flight.telemetry_synced ? 'Telemetry Synced' : 'Telemetry Pending'}
                </button>
              )}
              {flight.data_source && (
                <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-blue-500/15 text-blue-400">
                  {flight.data_source.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                </span>
              )}
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
                  {sortPilotsActiveFirst(pilots).map(p => <option key={p.id} value={p.id}>{p.full_name}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Vehicle</label>
                <select value={editForm.vehicle_id} onChange={e => setEditForm({...editForm, vehicle_id: e.target.value})}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
                  <option value="">Unassigned</option>
                  {sortVehicles(vehicles).map(v => <option key={v.id} value={v.id}>{vehicleDisplayName(v)}</option>)}
                </select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Purpose</label>
                <select value={editForm.purpose} onChange={e => setEditForm({...editForm, purpose: e.target.value})}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
                  <option value="">None</option>
                  {sortByName(purposes, 'name').map(p => <option key={p.id} value={p.name}>{p.name}</option>)}
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
                <input list="detail-battery-list" value={editForm.battery_serial} onChange={e => setEditForm({...editForm, battery_serial: e.target.value})}
                  placeholder="Select or type..." className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
                <datalist id="detail-battery-list">
                  {batteries.map(b => <option key={b.id} value={b.serial_number}>{b.nickname || b.serial_number}</option>)}
                </datalist>
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Sensor Package</label>
                <input list="detail-sensor-list" value={editForm.sensor_package} onChange={e => setEditForm({...editForm, sensor_package: e.target.value})}
                  placeholder="Select or type..." className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
                <datalist id="detail-sensor-list">
                  {sensors.map(s => <option key={s.id} value={s.serial_number}>{s.name || s.serial_number}</option>)}
                </datalist>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Attachment (TOP)</label>
                <input list="detail-attach-list" value={editForm.attachment_top} onChange={e => setEditForm({...editForm, attachment_top: e.target.value})}
                  placeholder="Select or type..." className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
                <datalist id="detail-attach-list">
                  {attachments.map(a => <option key={a.id} value={a.serial_number}>{a.name || a.serial_number}</option>)}
                </datalist>
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Attachment (BOTTOM)</label>
                <input list="detail-attach-list" value={editForm.attachment_bottom} onChange={e => setEditForm({...editForm, attachment_bottom: e.target.value})}
                  placeholder="Select or type..." className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Attachment (LEFT)</label>
                <input list="detail-attach-list" value={editForm.attachment_left} onChange={e => setEditForm({...editForm, attachment_left: e.target.value})}
                  placeholder="Select or type..." className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Attachment (RIGHT)</label>
                <input list="detail-attach-list" value={editForm.attachment_right} onChange={e => setEditForm({...editForm, attachment_right: e.target.value})}
                  placeholder="Select or type..." className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
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
            <div>
              <p className="text-xs text-muted-foreground">Takeoff Time</p>
              <p className="text-foreground">{flight.takeoff_time ? new Date(flight.takeoff_time).toLocaleTimeString() : '—'}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Landing Time</p>
              <p className="text-foreground">{flight.landing_time ? new Date(flight.landing_time).toLocaleTimeString() : '—'}</p>
            </div>
            <div><p className="text-xs text-muted-foreground">Takeoff</p><p className="text-sm text-foreground">{flight.takeoff_address || '—'}</p></div>
            <div><p className="text-xs text-muted-foreground">Max Altitude</p><p className="text-sm text-foreground">{flight.max_altitude_m ? `${metersToFeet(flight.max_altitude_m)} ft` : '—'}</p></div>
            <div><p className="text-xs text-muted-foreground">Max Speed</p><p className="text-sm text-foreground">{flight.max_speed_mps ? `${mpsToMph(flight.max_speed_mps)} mph` : '—'}</p></div>
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
      {telemetry.length > 0 && (() => {
        const chartData = telemetry.map(t => ({
          ...t,
          altitude_ft: t.altitude_m != null ? Math.round(t.altitude_m * 3.28084) : null,
          speed_mph: t.speed_mps != null ? Math.round(t.speed_mps * 2.23694 * 10) / 10 : null,
        }))
        return (
        <div className="space-y-4">
          {(flight.takeoff_lat || chartData.some(p => p.lat)) && (
            <div className="bg-card border border-border rounded-xl p-4">
              <h3 className="text-sm font-semibold text-foreground mb-3">Flight Path</h3>
              <FlightPathMap
                telemetry={chartData}
                takeoffLat={flight.takeoff_lat}
                takeoffLon={flight.takeoff_lon}
                landingLat={flight.landing_lat}
                landingLon={flight.landing_lon}
              />
            </div>
          )}
          <div className="bg-card border border-border rounded-xl p-5">
            <h3 className="text-sm font-semibold text-foreground mb-4">Altitude (ft)</h3>
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                <XAxis dataKey="elapsed_s" stroke="var(--muted-fg)" fontSize={11} label={{ value: 'seconds', position: 'bottom', fill: 'var(--muted-fg)', fontSize: 11 }} />
                <YAxis stroke="var(--muted-fg)" fontSize={11} />
                <Tooltip {...tooltipStyle} />
                <Line type="monotone" dataKey="altitude_ft" stroke="#6366f1" strokeWidth={2} dot={false} connectNulls={true} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="bg-card border border-border rounded-xl p-5">
              <h3 className="text-sm font-semibold text-foreground mb-4">Speed (mph)</h3>
              <ResponsiveContainer width="100%" height={250}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                  <XAxis dataKey="elapsed_s" stroke="var(--muted-fg)" fontSize={11} />
                  <YAxis stroke="var(--muted-fg)" fontSize={11} />
                  <Tooltip {...tooltipStyle} />
                  <Line type="monotone" dataKey="speed_mph" stroke="#3b82f6" strokeWidth={2} dot={false} connectNulls={true} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="bg-card border border-border rounded-xl p-5">
              <h3 className="text-sm font-semibold text-foreground mb-4">Battery (%)</h3>
              <ResponsiveContainer width="100%" height={250}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                  <XAxis dataKey="elapsed_s" stroke="var(--muted-fg)" fontSize={11} />
                  <YAxis stroke="var(--muted-fg)" fontSize={11} domain={[0, 100]} />
                  <Tooltip {...tooltipStyle} />
                  <Line type="monotone" dataKey="battery_pct" stroke="#10b981" strokeWidth={2} dot={false} connectNulls={true} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
        )
      })()}

      {telemetry.length === 0 && (
        <>
          {flight.takeoff_lat && (
            <div className="bg-card border border-border rounded-xl p-4">
              <h3 className="text-sm font-semibold text-foreground mb-3">Flight Location</h3>
              <FlightPathMap takeoffLat={flight.takeoff_lat} takeoffLon={flight.takeoff_lon} height="300px" />
            </div>
          )}
          <div className="bg-card border border-border rounded-xl p-8 text-center text-muted-foreground">
            <MapPin className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p>No telemetry data available for this flight.</p>
            <p className="text-xs mt-1">Click "Refresh from API" to fetch telemetry data.</p>
          </div>
        </>
      )}
    </div>
  )
}
