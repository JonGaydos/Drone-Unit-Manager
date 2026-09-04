import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { formatDuration, normalizeDateValue, metersToFeet, mpsToMph, formatTime, utcIsoToZonedInput, zonedInputToUtcIso } from '@/lib/utils'
import { sortByName, sortVehicles, sortPilotsActiveFirst, vehicleDisplayName } from '@/lib/formatters'
import { ArrowLeft, MapPin, Save, RefreshCw, Loader2, Download } from 'lucide-react'
import { QuadcopterIcon } from '@/components/icons/QuadcopterIcon'
import { FlightPathMap } from '@/components/FlightMap'
import LinkedPhotos from '@/components/LinkedPhotos'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'

const tooltipStyle = {
  contentStyle: { background: 'var(--card)', border: '1px solid var(--border-color)', borderRadius: '8px', color: 'var(--fg)' },
}

// Shared control styling so an editable cell occupies the same box as the
// read-only value it replaces.
const CONTROL = 'w-full mt-0.5 px-2 py-1 bg-secondary border border-border rounded-lg text-foreground text-sm'

/** One cell of the flight info grid: a caption above a value or a control.
 *  Pass htmlFor when the cell holds a control, so the caption is a real label. */
function Field({ label, htmlFor, children, className = '' }) {
  const caption = 'block text-xs text-muted-foreground'
  return (
    <div className={className}>
      {htmlFor
        ? <label htmlFor={htmlFor} className={caption}>{label}</label>
        : <p className={caption}>{label}</p>}
      {children}
    </div>
  )
}

/** A datalist-backed text input, used for the serial/attachment cells. */
function PickerInput({ id, list, value, onChange }) {
  return (
    <input
      id={id} list={list} value={value} onChange={onChange}
      onFocus={e => { e.target.showPicker?.() }}
      placeholder="Select or type..." className={CONTROL}
    />
  )
}

function TelemetryCharts({ telemetry, flight }) {
  const chartData = telemetry.map(t => ({
    ...t,
    altitude_ft: t.altitude_m == null ? null : Math.round(t.altitude_m * 3.28084),
    speed_mph: t.speed_mps == null ? null : Math.round(t.speed_mps * 2.23694 * 10) / 10,
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
      takeoff_time: f.takeoff_time ? utcIsoToZonedInput(f.takeoff_time) : '',
      landing_time: f.landing_time ? utcIsoToZonedInput(f.landing_time) : '',
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
      counts_toward_totals: f.counts_toward_totals !== false,
    })
  }

  useEffect(() => {
    // Abort the in-flight load on unmount or when `id` changes, and guard with an
    // ignore flag so a slow earlier request can't resolve after navigation and
    // overwrite newer data or setState after unmount.
    const controller = new AbortController()
    const { signal } = controller
    let ignore = false
    setLoading(true)
    Promise.all([
      api.get(`/flights/${id}`, { signal }),
      api.get(`/telemetry/flight/${id}`, { signal }).catch(() => []),
      api.get('/pilots', { signal }),
      api.get('/vehicles', { signal }),
      api.get('/flights/purposes/list', { signal }),
      api.get('/batteries', { signal }).catch(() => []),
      api.get('/sensors', { signal }).catch(() => []),
      api.get('/attachments', { signal }).catch(() => []),
    ]).then(([f, t, p, v, pu, bats, sens, atts]) => {
      if (ignore) return
      setFlight(f)
      setTelemetry(Array.isArray(t) ? t : [])
      setPilots(p)
      setVehicles(v)
      setPurposes(pu)
      setBatteries(bats)
      setSensors(sens)
      setAttachments(atts)
      initEditForm(f)
    }).catch(err => {
      // A superseded load rejects with AbortError; ignore it (a newer load owns the UI).
      if (ignore || err.name === 'AbortError') return
    }).finally(() => {
      if (!ignore) setLoading(false)
    })
    return () => { ignore = true; controller.abort() }
  }, [id])

  const handleSave = async () => {
    try {
      const data = { ...editForm }
      if (data.pilot_id) data.pilot_id = Number.parseInt(data.pilot_id, 10)
      else data.pilot_id = null
      if (data.vehicle_id) data.vehicle_id = Number.parseInt(data.vehicle_id, 10)
      else data.vehicle_id = null
      if (data.duration_seconds) data.duration_seconds = Number.parseInt(data.duration_seconds, 10)
      else delete data.duration_seconds
      // Clean empty strings
      Object.keys(data).forEach(k => { if (data[k] === '') data[k] = null })
      if (data.takeoff_time) data.takeoff_time = zonedInputToUtcIso(data.takeoff_time)
      if (data.landing_time) data.landing_time = zonedInputToUtcIso(data.landing_time)
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
          {isAdmin && (editing ? (
            <>
              <button onClick={handleSave} className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90">
                <Save className="w-4 h-4" /> Save
              </button>
              <button onClick={() => { setEditing(false); initEditForm(flight) }} className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90">
                Cancel
              </button>
            </>
          ) : (
            <button onClick={() => { initEditForm(flight); setEditing(true) }} className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90">
              Edit
            </button>
          ))}
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
                    const nextValue = !flight.telemetry_synced
                    try {
                      await api.patch(`/flights/${flight.id}/telemetry-status`, { telemetry_synced: nextValue })
                      const updated = await api.get(`/flights/${id}`)
                      setFlight(updated)
                      toast.success(`Telemetry ${nextValue ? 'marked as synced' : 'marked as pending'}`)
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
                  {flight.data_source.replaceAll('_', ' ').replaceAll(/\b\w/g, c => c.toUpperCase())}
                </span>
              )}
              {flight.api_provider && <span>Source: {flight.api_provider}</span>}
            </div>
          </div>
        </div>

        {/* One grid for both modes: every cell keeps its position when editing,
            and swaps its read-only value for a control in place. */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 border-t border-border pt-4">
          <Field label="Pilot" htmlFor={editing ? 'pilot' : undefined}>
            {editing ? (
              <select id="pilot" value={editForm.pilot_id} onChange={e => setEditForm({ ...editForm, pilot_id: e.target.value })} className={CONTROL}>
                <option value="">Unassigned</option>
                {sortPilotsActiveFirst(pilots).map(p => <option key={p.id} value={p.id}>{p.full_name}</option>)}
              </select>
            ) : (
              <p className="text-sm text-foreground">{flight.pilot_id ? <Link to={`/pilots/${flight.pilot_id}`} className="text-primary hover:underline">{flight.pilot_name || 'Unassigned'}</Link> : (flight.pilot_name || 'Unassigned')}</p>
            )}
          </Field>

          <Field label="Vehicle" htmlFor={editing ? 'vehicle' : undefined}>
            {editing ? (
              <select id="vehicle" value={editForm.vehicle_id} onChange={e => setEditForm({ ...editForm, vehicle_id: e.target.value })} className={CONTROL}>
                <option value="">Unassigned</option>
                {sortVehicles(vehicles).map(v => <option key={v.id} value={v.id}>{vehicleDisplayName(v)}</option>)}
              </select>
            ) : (
              <p className="text-sm text-foreground">{flight.vehicle_id ? <Link to={`/fleet/vehicles/${flight.vehicle_id}`} className="text-primary hover:underline">{flight.vehicle_name || '—'}</Link> : (flight.vehicle_name || '—')}</p>
            )}
          </Field>

          <Field label="Purpose" htmlFor={editing ? 'purpose' : undefined}>
            {editing ? (
              <select id="purpose" value={editForm.purpose} onChange={e => setEditForm({ ...editForm, purpose: e.target.value })} className={CONTROL}>
                <option value="">None</option>
                {sortByName(purposes, 'name').map(p => <option key={p.id} value={p.name}>{p.name}</option>)}
              </select>
            ) : (
              <p className="text-sm text-foreground">{flight.purpose ? <Link to={`/flights?purpose=${encodeURIComponent(flight.purpose)}`} className="text-primary hover:underline">{flight.purpose}</Link> : '—'}</p>
            )}
          </Field>

          <Field label={editing ? 'Duration (seconds)' : 'Duration'} htmlFor={editing ? 'duration-seconds' : undefined}>
            {editing ? (
              <input id="duration-seconds" type="number" value={editForm.duration_seconds} onChange={e => setEditForm({ ...editForm, duration_seconds: e.target.value })} className={CONTROL} />
            ) : (
              <p className="text-sm text-foreground">{formatDuration(flight.duration_seconds)}</p>
            )}
          </Field>

          <Field label="Takeoff Time" htmlFor={editing ? 'takeoff-time' : undefined}>
            {editing ? (
              <input id="takeoff-time" type="datetime-local" value={editForm.takeoff_time} onChange={e => setEditForm({ ...editForm, takeoff_time: e.target.value })} className={CONTROL} />
            ) : (
              <p className="text-foreground">{formatTime(flight.takeoff_time)}</p>
            )}
          </Field>

          <Field label="Landing Time" htmlFor={editing ? 'landing-time' : undefined}>
            {editing ? (
              <input id="landing-time" type="datetime-local" value={editForm.landing_time} onChange={e => setEditForm({ ...editForm, landing_time: e.target.value })} className={CONTROL} />
            ) : (
              <p className="text-foreground">{formatTime(flight.landing_time)}</p>
            )}
          </Field>

          <Field label="Takeoff" htmlFor={editing ? 'takeoff-address-location' : undefined}>
            {editing ? (
              <input id="takeoff-address-location" type="text" value={editForm.takeoff_address} onChange={e => setEditForm({ ...editForm, takeoff_address: e.target.value })} className={CONTROL} />
            ) : (
              <p className="text-sm text-foreground">{flight.takeoff_address || '—'}</p>
            )}
          </Field>

          {/* Telemetry-derived, so read-only in both modes. */}
          <Field label="Max Altitude">
            <p className="text-sm text-foreground">{flight.max_altitude_m ? `${metersToFeet(flight.max_altitude_m)} ft` : '—'}</p>
          </Field>

          <Field label="Max Speed">
            <p className="text-sm text-foreground">{flight.max_speed_mps ? `${mpsToMph(flight.max_speed_mps)} mph` : '—'}</p>
          </Field>

          <Field label="Case #" htmlFor={editing ? 'case-number' : undefined}>
            {editing ? (
              <input id="case-number" type="text" value={editForm.case_number} onChange={e => setEditForm({ ...editForm, case_number: e.target.value })} className={CONTROL} />
            ) : (
              <p className="text-sm text-foreground">{flight.case_number || '—'}</p>
            )}
          </Field>

          <Field label="Battery Serial" htmlFor={editing ? 'battery-serial' : undefined}>
            {editing ? (
              <>
                <PickerInput id="battery-serial" list="detail-battery-list" value={editForm.battery_serial} onChange={e => setEditForm({ ...editForm, battery_serial: e.target.value })} />
                <datalist id="detail-battery-list">
                  {batteries.map(b => <option key={b.id} value={b.serial_number}>{b.nickname || b.serial_number}</option>)}
                </datalist>
              </>
            ) : (
              <p className="text-sm text-foreground">{flight.battery_serial ? (() => {
                const bat = batteries.find(b => b.serial_number === flight.battery_serial)
                return bat ? <Link to={`/fleet/batteries/${bat.id}`} className="text-primary hover:underline">{flight.battery_serial}</Link> : flight.battery_serial
              })() : '—'}</p>
            )}
          </Field>

          <Field label="Sensor Package" htmlFor={editing ? 'sensor-package' : undefined}>
            {editing ? (
              <>
                <PickerInput id="sensor-package" list="detail-sensor-list" value={editForm.sensor_package} onChange={e => setEditForm({ ...editForm, sensor_package: e.target.value })} />
                <datalist id="detail-sensor-list">
                  {sensors.map(s => <option key={s.id} value={s.serial_number}>{s.name || s.serial_number}</option>)}
                </datalist>
              </>
            ) : (
              <p className="text-sm text-foreground">{flight.sensor_package ? (
                <Link to="/fleet?tab=sensors" className="text-primary hover:underline">{flight.sensor_package}</Link>
              ) : '—'}</p>
            )}
          </Field>

          <Field label="Carrier(s)" htmlFor={editing ? 'carriers' : undefined}>
            {editing ? (
              <input id="carriers" type="text" value={editForm.carrier} onChange={e => setEditForm({ ...editForm, carrier: e.target.value })} className={CONTROL} />
            ) : (
              <p className="text-sm text-foreground">{flight.carrier || '—'}</p>
            )}
          </Field>

          {/* Date is shown in the heading when viewing, so this cell is the
              spacer the view already had; editing puts the date control in it
              rather than displacing anything below. */}
          {editing ? (
            <Field label="Date" htmlFor="date">
              <input id="date" type="date" value={editForm.date}
                onChange={e => setEditForm({ ...editForm, date: e.target.value })}
                onBlur={e => { const n = normalizeDateValue(e.target.value); if (n !== e.target.value) setEditForm(prev => ({ ...prev, date: n })) }}
                className={CONTROL} />
            </Field>
          ) : (
            <div><p className="text-xs text-muted-foreground">&nbsp;</p></div>
          )}

          {(editing || flight.attachment_top || flight.attachment_bottom || flight.attachment_left || flight.attachment_right) && (
            <>
              <Field label="Attachment (TOP)" htmlFor={editing ? 'attachment-top' : undefined}>
                {editing ? (
                  <>
                    <PickerInput id="attachment-top" list="detail-attach-list" value={editForm.attachment_top} onChange={e => setEditForm({ ...editForm, attachment_top: e.target.value })} />
                    <datalist id="detail-attach-list">
                      {attachments.map(a => <option key={a.id} value={a.serial_number}>{a.name || a.serial_number}</option>)}
                    </datalist>
                  </>
                ) : (
                  <p className="text-sm text-foreground">{flight.attachment_top ? <Link to="/fleet?tab=attachments" className="text-primary hover:underline">{flight.attachment_top}</Link> : '—'}</p>
                )}
              </Field>
              <Field label="Attachment (BOTTOM)" htmlFor={editing ? 'attachment-bottom' : undefined}>
                {editing ? (
                  <PickerInput id="attachment-bottom" list="detail-attach-list" value={editForm.attachment_bottom} onChange={e => setEditForm({ ...editForm, attachment_bottom: e.target.value })} />
                ) : (
                  <p className="text-sm text-foreground">{flight.attachment_bottom ? <Link to="/fleet?tab=attachments" className="text-primary hover:underline">{flight.attachment_bottom}</Link> : '—'}</p>
                )}
              </Field>
              <Field label="Attachment (LEFT)" htmlFor={editing ? 'attachment-left' : undefined}>
                {editing ? (
                  <PickerInput id="attachment-left" list="detail-attach-list" value={editForm.attachment_left} onChange={e => setEditForm({ ...editForm, attachment_left: e.target.value })} />
                ) : (
                  <p className="text-sm text-foreground">{flight.attachment_left ? <Link to="/fleet?tab=attachments" className="text-primary hover:underline">{flight.attachment_left}</Link> : '—'}</p>
                )}
              </Field>
              <Field label="Attachment (RIGHT)" htmlFor={editing ? 'attachment-right' : undefined}>
                {editing ? (
                  <PickerInput id="attachment-right" list="detail-attach-list" value={editForm.attachment_right} onChange={e => setEditForm({ ...editForm, attachment_right: e.target.value })} />
                ) : (
                  <p className="text-sm text-foreground">{flight.attachment_right ? <Link to="/fleet?tab=attachments" className="text-primary hover:underline">{flight.attachment_right}</Link> : '—'}</p>
                )}
              </Field>
            </>
          )}

          {/* Review status is a badge beside the heading when viewing. Editing puts
              it in the trailing gap of the attachment row, which is empty in both
              modes, so it costs no extra row and still displaces nothing. */}
          {editing && (
            <Field label="Status" htmlFor="status">
              <select id="status" value={editForm.review_status} onChange={e => setEditForm({ ...editForm, review_status: e.target.value })} className={CONTROL}>
                <option value="needs_review">Needs Review</option>
                <option value="reviewed">Reviewed</option>
              </select>
            </Field>
          )}

          {/* Per-flight override of the pilot-level rule, for a one-off that is
              not the unit's own activity: a vendor demo flown by one of ours, a
              test flight. Shown when editing, and when viewing only if it is
              off, so a flight missing from the totals says why. */}
          {(editing || flight.counts_toward_totals === false) && (
            <Field label="Unit totals" htmlFor={editing ? 'counts-toward-totals' : undefined}>
              {editing ? (
                <span className="flex items-center gap-2 mt-1.5 text-sm text-foreground">
                  <input
                    id="counts-toward-totals"
                    type="checkbox"
                    checked={editForm.counts_toward_totals !== false}
                    onChange={e => setEditForm({ ...editForm, counts_toward_totals: e.target.checked })}
                    className="rounded border-border"
                  />
                  <span>Counts</span>
                </span>
              ) : (
                <span className="px-2 py-0.5 text-xs rounded-full bg-amber-500/15 text-amber-400">Not counted</span>
              )}
            </Field>
          )}

          {(editing || flight.notes) && (
            <Field label="Notes" htmlFor={editing ? 'notes' : undefined} className="col-span-2 md:col-span-4">
              {editing ? (
                <textarea id="notes" value={editForm.notes} onChange={e => setEditForm({ ...editForm, notes: e.target.value })}
                  className={`${CONTROL} h-20 resize-none`} />
              ) : (
                <p className="text-sm text-foreground">{flight.notes}</p>
              )}
            </Field>
          )}
        </div>
      </div>

      {/* Telemetry Charts */}
      {telemetry.length > 0 && (
        <TelemetryCharts telemetry={telemetry} flight={flight} />
      )}

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

      <LinkedPhotos entityType="flight" entityId={id} />
    </div>
  )
}
