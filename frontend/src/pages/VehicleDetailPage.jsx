import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { useConfirm } from '@/hooks/useConfirm'
import { formatHours, formatDuration, normalizeDateValue } from '@/lib/utils'
import { STATUS_COLORS } from '@/lib/constants'
import {
  ArrowLeft, Clock, Calendar, Battery, Edit,
  FileText, Wrench, Gamepad2, Cpu, Paperclip, Camera,
  ShieldCheck, Plus, Trash2, AlertTriangle, LogIn, LogOut,
  CheckCircle, User, Cog, X, Save
} from 'lucide-react'
import { QuadcopterIcon } from '@/components/icons/QuadcopterIcon'
import DocumentUpload from '@/components/DocumentUpload'

export default function VehicleDetailPage() {
  const { id } = useParams()
  const { isAdmin } = useAuth()
  const toast = useToast()
  const [confirmProps, requestConfirm] = useConfirm()
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
  const [checkouts, setCheckouts] = useState([])
  const [activeCheckout, setActiveCheckout] = useState(null)
  const [pilots, setPilots] = useState([])
  const [showCheckoutForm, setShowCheckoutForm] = useState(false)
  const [checkoutForm, setCheckoutForm] = useState({ pilot_id: '', condition_out: 'good', notes_out: '' })
  const [checkinForm, setCheckinForm] = useState({ condition_in: 'good', notes_in: '' })
  const [showCheckinForm, setShowCheckinForm] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editForm, setEditForm] = useState({})
  const [saving, setSaving] = useState(false)
  const [components, setComponents] = useState([])
  const [showComponentForm, setShowComponentForm] = useState(false)
  const [componentForm, setComponentForm] = useState({
    name: '', component_type: 'propeller', serial_number: '', manufacturer: '', model: '',
    status: 'active', install_date: '', flight_hours: 0, max_flight_hours: '', warranty_expiry: '',
    replacement_cost: '', notes: ''
  })

  // Auto-file documents to Maintenance folder
  const [maintenanceFolderId, setMaintenanceFolderId] = useState(null)
  useEffect(() => {
    api.get('/folders').then(folders => {
      const f = (Array.isArray(folders) ? folders : folders.folders || []).find(f => f.name === 'Maintenance')
      if (f) setMaintenanceFolderId(f.id)
    }).catch(() => {})
  }, [])

  const loadRegistrations = () => {
    api.get(`/vehicles/${id}/registrations`).then(setRegistrations).catch(() => [])
  }

  const loadComponents = () => {
    api.get(`/components?vehicle_id=${id}`).then(setComponents).catch(() => [])
  }

  const loadCheckouts = () => {
    api.get(`/equipment-checkouts?entity_type=vehicle&entity_id=${id}`).then(data => {
      setCheckouts(data)
      setActiveCheckout(data.find(c => !c.checked_in_at) || null)
    }).catch(() => {})
  }

  useEffect(() => {
    Promise.all([
      api.get(`/vehicles/${id}`),
      api.get(`/vehicles/${id}/stats`),
      api.get(`/flights?vehicle_id=${id}&per_page=50`),
      api.get('/batteries').catch(() => []),
      api.get('/controllers').catch(() => []),
      api.get('/sensors').catch(() => []),
      api.get('/attachments').catch(() => []),
      api.get(`/maintenance?entity_type=vehicle&entity_id=${id}`).catch(() => []),
      api.get(`/vehicles/${id}/registrations`).catch(() => []),
      api.get(`/equipment-checkouts?entity_type=vehicle&entity_id=${id}`).catch(() => []),
      api.get('/pilots').catch(() => []),
      api.get(`/components?vehicle_id=${id}`).catch(() => []),
    ]).then(([v, s, fData, bat, ctrl, sens, att, maint, regs, chk, pil, comp]) => {
      setVehicle(v)
      setStats(s)
      setFlights(fData.flights || fData)
      setBatteries(bat)
      setControllers(ctrl)
      setSensors(sens)
      setAttachments(att)
      setMaintenance(maint)
      setRegistrations(regs)
      setCheckouts(chk)
      setActiveCheckout(chk.find(c => !c.checked_in_at) || null)
      setPilots(Array.isArray(pil) ? pil : (pil.pilots || []))
      setComponents(comp)
    }).catch(() => {}).finally(() => setLoading(false))
  }, [id])

  const startEditing = () => {
    setEditForm({
      nickname: vehicle.nickname || '',
      manufacturer: vehicle.manufacturer || '',
      model: vehicle.model || '',
      serial_number: vehicle.serial_number || '',
      faa_registration: vehicle.faa_registration || '',
      status: vehicle.status || 'active',
      notes: vehicle.notes || '',
    })
    setEditing(true)
  }

  const cancelEditing = () => {
    setEditForm({})
    setEditing(false)
  }

  const handleSaveEdit = async () => {
    setSaving(true)
    try {
      const updated = await api.patch(`/vehicles/${id}`, editForm)
      setVehicle(updated)
      setEditing(false)
    } catch (err) {
      toast.error(err.message)
    } finally {
      setSaving(false)
    }
  }

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
    { key: 'attachments', label: 'Mounted Accessories', icon: Paperclip },
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
                <QuadcopterIcon className="w-8 h-8" />
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
                  try {
                    const result = await api.upload(`/vehicles/${id}/photo`, formData)
                    setVehicle({ ...vehicle, photo_url: result.photo_url + '?t=' + Date.now() })
                  } catch (err) { toast.error(err.message) }
                  e.target.value = ''
                }} />
              </label>
            )}
          </div>
          <div className="flex-1">
            {editing ? (
              <div className="space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Nickname</label>
                    <input type="text" value={editForm.nickname} onChange={e => setEditForm({...editForm, nickname: e.target.value})}
                      className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Manufacturer</label>
                    <input type="text" value={editForm.manufacturer} onChange={e => setEditForm({...editForm, manufacturer: e.target.value})}
                      className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Model</label>
                    <input type="text" value={editForm.model} onChange={e => setEditForm({...editForm, model: e.target.value})}
                      className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Serial Number</label>
                    <input type="text" value={editForm.serial_number} onChange={e => setEditForm({...editForm, serial_number: e.target.value})}
                      className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">FAA Registration</label>
                    <input type="text" value={editForm.faa_registration} onChange={e => setEditForm({...editForm, faa_registration: e.target.value})}
                      className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Status</label>
                    <select value={editForm.status} onChange={e => setEditForm({...editForm, status: e.target.value})}
                      className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm">
                      <option value="active">Active</option>
                      <option value="inactive">Inactive</option>
                      <option value="maintenance">Maintenance</option>
                      <option value="retired">Retired</option>
                    </select>
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1">Notes</label>
                  <textarea value={editForm.notes} onChange={e => setEditForm({...editForm, notes: e.target.value})}
                    className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm h-16 resize-none focus:outline-none focus:ring-2 focus:ring-ring" />
                </div>
                <div className="flex gap-2">
                  <button onClick={handleSaveEdit} disabled={saving}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50">
                    {saving ? <div className="w-4 h-4 border-2 border-primary-foreground border-t-transparent rounded-full animate-spin" /> : <Save className="w-4 h-4" />} Save
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
                  <h2 className="text-xl font-bold text-foreground">{displayName || 'Unnamed Vehicle'}</h2>
                  {isAdmin && (
                    <button onClick={startEditing} className="p-1.5 text-muted-foreground hover:text-foreground rounded-lg hover:bg-accent" aria-label="Edit">
                      <Edit className="w-4 h-4" />
                    </button>
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
              </>
            )}
          </div>
        </div>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary/15 flex items-center justify-center text-primary"><QuadcopterIcon className="w-5 h-5" /></div>
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
                  <Link to={`/flights/${f.id}`} className="text-primary hover:underline">{f.date || '—'}</Link>
                </td>
                <td className="px-4 py-2 text-muted-foreground">
                  {f.pilot_id ? (
                    <Link to={`/pilots/${f.pilot_id}`} className="text-primary hover:underline">{f.pilot_name || `Pilot #${f.pilot_id}`}</Link>
                  ) : '—'}
                </td>
                <td className="px-4 py-2 text-muted-foreground hidden md:table-cell">{f.purpose || '—'}</td>
                <td className="px-4 py-2 text-muted-foreground">{formatDuration(f.duration_seconds)}</td>
                <td className="px-4 py-2 text-muted-foreground hidden md:table-cell">{f.battery_serial ? (() => {
                  const bat = batteries.find(b => b.serial_number === f.battery_serial)
                  return bat ? <Link to={`/fleet/batteries/${bat.id}`} className="text-primary hover:underline">{f.battery_serial}</Link> : f.battery_serial
                })() : '—'}</td>
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
          const current = [...registrations].sort((a, b) => (b.registration_date || '').localeCompare(a.registration_date || ''))[0]
          if (current) {
            const today = new Date()
            const expiry = current.expiry_date ? new Date(current.expiry_date) : null
            const daysUntil = expiry ? Math.ceil((expiry - today) / (1000 * 60 * 60 * 24)) : null
            const isExpired = daysUntil !== null && daysUntil < 0
            const isUrgent = daysUntil !== null && daysUntil >= 0 && daysUntil < 30
            const isWarning = daysUntil !== null && daysUntil >= 30 && daysUntil <= 90
            const isGood = daysUntil !== null && daysUntil > 90
            return (
              <div className={`px-4 py-3 border-b border-border flex items-center gap-4 ${
                isExpired ? 'bg-red-900/10' : isUrgent ? 'bg-red-500/5' : isWarning ? 'bg-amber-500/5' : 'bg-emerald-500/5'
              }`}>
                <div className="flex-1">
                  <p className="text-lg font-semibold text-foreground">
                    Next Due: {current.expiry_date || 'N/A'}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {current.registration_number || 'No registration number'} | Registered: {current.registration_date || 'N/A'}
                  </p>
                </div>
                <div className="text-right">
                  {daysUntil !== null && (
                    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-semibold ${
                      isExpired ? 'bg-red-900/20 text-red-300' :
                      isUrgent ? 'bg-red-500/15 text-red-400' :
                      isWarning ? 'bg-amber-500/15 text-amber-400' :
                      'bg-emerald-500/15 text-emerald-400'
                    }`}>
                      {isExpired && <AlertTriangle className="w-3.5 h-3.5" />}
                      {isUrgent && <AlertTriangle className="w-3.5 h-3.5" />}
                      {isExpired ? `Overdue ${Math.abs(daysUntil)}d` :
                       `${daysUntil} days remaining`}
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
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
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
                  onBlur={e => { const n = normalizeDateValue(e.target.value); if (n !== e.target.value) setRegForm(prev => ({...prev, registration_date: n})) }}
                  className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Expiry (auto: +2 years)</label>
                <input type="text" readOnly
                  value={regForm.registration_date ? (() => {
                    const d = new Date(regForm.registration_date)
                    d.setDate(d.getDate() + 730)
                    return d.toISOString().split('T')[0]
                  })() : '--'}
                  className="w-full px-3 py-1.5 bg-muted border border-border rounded-lg text-muted-foreground text-sm cursor-not-allowed" />
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
                  } catch (err) { toast.error(err.message) }
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
                {registrations.map(r => {
                  const isExpired = r.expiry_date && new Date(r.expiry_date) < new Date()
                  const statusLabel = r.is_current ? (isExpired ? 'Expired' : 'Current') : (isExpired ? 'Expired' : 'Previous')
                  const statusColor = r.is_current && !isExpired
                    ? 'bg-emerald-500/15 text-emerald-400'
                    : isExpired ? 'bg-red-500/15 text-red-400' : 'bg-zinc-500/15 text-zinc-400'
                  return (
                  <tr key={r.id} className="border-b border-border/50 hover:bg-accent/30">
                    <td className="px-4 py-2 text-foreground font-medium">{r.registration_number || '--'}</td>
                    <td className="px-4 py-2 text-muted-foreground">{r.registration_date || '--'}</td>
                    <td className="px-4 py-2 text-muted-foreground">{r.expiry_date || '--'}</td>
                    <td className="px-4 py-2">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${statusColor}`}>
                        {statusLabel}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-muted-foreground hidden md:table-cell">{r.notes || '--'}</td>
                    {isAdmin && (
                      <td className="px-4 py-2 text-right">
                        <button onClick={() => {
                          requestConfirm({
                            title: 'Delete Registration',
                            message: 'Delete this registration?',
                            onConfirm: async () => {
                              try {
                                await api.delete(`/vehicle-registrations/${r.id}`)
                                loadRegistrations()
                              } catch (err) { toast.error(err.message) }
                            }
                          })
                        }} className="p-1.5 text-muted-foreground hover:text-destructive rounded hover:bg-destructive/10">
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    )}
                  </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="px-4 py-8 text-center text-muted-foreground text-sm">No FAA registrations recorded</div>
        )}
      </div>

      {/* Equipment Checkout Status */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <div className="flex items-center gap-2">
            <LogIn className="w-4 h-4 text-primary" />
            <h3 className="font-semibold text-foreground">Checkout Status</h3>
          </div>
          {!activeCheckout && (
            <button
              onClick={() => setShowCheckoutForm(!showCheckoutForm)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-medium hover:opacity-90"
            >
              <LogIn className="w-3.5 h-3.5" /> Check Out
            </button>
          )}
        </div>

        {/* Active checkout banner */}
        {activeCheckout && (
          <div className="px-4 py-3 border-b border-border bg-amber-500/5 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-amber-500/15 flex items-center justify-center">
                <User className="w-4 h-4 text-amber-400" />
              </div>
              <div>
                <p className="text-sm font-medium text-foreground">
                  Checked out by {activeCheckout.checked_out_by_name || `Pilot #${activeCheckout.checked_out_by_id}`}
                </p>
                <p className="text-xs text-muted-foreground">
                  Since {new Date(activeCheckout.checked_out_at).toLocaleString()}
                  {activeCheckout.condition_out && ` | Condition: ${activeCheckout.condition_out}`}
                  {activeCheckout.notes_out && ` | ${activeCheckout.notes_out}`}
                </p>
              </div>
            </div>
            <button
              onClick={() => setShowCheckinForm(!showCheckinForm)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 text-white rounded-lg text-xs font-medium hover:opacity-90 shrink-0"
            >
              <LogOut className="w-3.5 h-3.5" /> Check In
            </button>
          </div>
        )}

        {/* Check-in form */}
        {showCheckinForm && activeCheckout && (
          <div className="px-4 py-3 border-b border-border bg-muted/20 space-y-2">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Returning Pilot</label>
                <select
                  value={checkinForm.pilot_id || ''}
                  onChange={e => setCheckinForm({ ...checkinForm, pilot_id: e.target.value })}
                  className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm"
                >
                  <option value="">Select pilot...</option>
                  {pilots.map(p => (
                    <option key={p.id} value={p.id}>{p.first_name} {p.last_name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Condition</label>
                <select
                  value={checkinForm.condition_in}
                  onChange={e => setCheckinForm({ ...checkinForm, condition_in: e.target.value })}
                  className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm"
                >
                  <option value="good">Good</option>
                  <option value="fair">Fair</option>
                  <option value="needs_attention">Needs Attention</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Notes</label>
                <input type="text" value={checkinForm.notes_in}
                  onChange={e => setCheckinForm({ ...checkinForm, notes_in: e.target.value })}
                  placeholder="Optional"
                  className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
            </div>
            <div className="flex gap-2">
              <button
                onClick={async () => {
                  if (!checkinForm.pilot_id) { toast.error('Select a pilot'); return }
                  try {
                    await api.post(`/equipment-checkouts/${activeCheckout.id}/checkin`, {
                      checked_in_by_id: parseInt(checkinForm.pilot_id),
                      condition_in: checkinForm.condition_in,
                      notes_in: checkinForm.notes_in || null,
                    })
                    setShowCheckinForm(false)
                    setCheckinForm({ condition_in: 'good', notes_in: '' })
                    loadCheckouts()
                    toast.success('Equipment checked in')
                  } catch (err) { toast.error(err.message) }
                }}
                className="px-4 py-1.5 bg-emerald-600 text-white rounded-lg text-xs font-medium hover:opacity-90"
              >
                Confirm Check-In
              </button>
              <button onClick={() => setShowCheckinForm(false)}
                className="px-4 py-1.5 bg-secondary text-secondary-foreground rounded-lg text-xs hover:opacity-90">
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Checkout form */}
        {showCheckoutForm && !activeCheckout && (
          <div className="px-4 py-3 border-b border-border bg-muted/20 space-y-2">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Pilot</label>
                <select
                  value={checkoutForm.pilot_id}
                  onChange={e => setCheckoutForm({ ...checkoutForm, pilot_id: e.target.value })}
                  className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm"
                >
                  <option value="">Select pilot...</option>
                  {pilots.map(p => (
                    <option key={p.id} value={p.id}>{p.first_name} {p.last_name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Condition</label>
                <select
                  value={checkoutForm.condition_out}
                  onChange={e => setCheckoutForm({ ...checkoutForm, condition_out: e.target.value })}
                  className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm"
                >
                  <option value="good">Good</option>
                  <option value="fair">Fair</option>
                  <option value="needs_attention">Needs Attention</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Notes</label>
                <input type="text" value={checkoutForm.notes_out}
                  onChange={e => setCheckoutForm({ ...checkoutForm, notes_out: e.target.value })}
                  placeholder="Optional"
                  className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
            </div>
            <div className="flex gap-2">
              <button
                onClick={async () => {
                  if (!checkoutForm.pilot_id) { toast.error('Select a pilot'); return }
                  try {
                    await api.post('/equipment-checkouts', {
                      entity_type: 'vehicle',
                      entity_id: parseInt(id),
                      entity_name: displayName,
                      checked_out_by_id: parseInt(checkoutForm.pilot_id),
                      condition_out: checkoutForm.condition_out,
                      notes_out: checkoutForm.notes_out || null,
                    })
                    setShowCheckoutForm(false)
                    setCheckoutForm({ pilot_id: '', condition_out: 'good', notes_out: '' })
                    loadCheckouts()
                    toast.success('Equipment checked out')
                  } catch (err) { toast.error(err.message) }
                }}
                className="px-4 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-medium hover:opacity-90"
              >
                Confirm Check-Out
              </button>
              <button onClick={() => setShowCheckoutForm(false)}
                className="px-4 py-1.5 bg-secondary text-secondary-foreground rounded-lg text-xs hover:opacity-90">
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Checkout history */}
        {checkouts.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/30">
                  <th className="text-left px-4 py-2 text-muted-foreground font-medium">Checked Out By</th>
                  <th className="text-left px-4 py-2 text-muted-foreground font-medium">Out</th>
                  <th className="text-left px-4 py-2 text-muted-foreground font-medium">In</th>
                  <th className="text-left px-4 py-2 text-muted-foreground font-medium hidden md:table-cell">Condition Out</th>
                  <th className="text-left px-4 py-2 text-muted-foreground font-medium hidden md:table-cell">Condition In</th>
                  <th className="text-left px-4 py-2 text-muted-foreground font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {checkouts.map(c => (
                  <tr key={c.id} className="border-b border-border/50 hover:bg-accent/30">
                    <td className="px-4 py-2 text-foreground font-medium">{c.checked_out_by_name || '--'}</td>
                    <td className="px-4 py-2 text-muted-foreground text-xs">{c.checked_out_at ? new Date(c.checked_out_at).toLocaleString() : '--'}</td>
                    <td className="px-4 py-2 text-muted-foreground text-xs">
                      {c.checked_in_at ? new Date(c.checked_in_at).toLocaleString() : '--'}
                      {c.checked_in_by_name && <span className="block text-xs">by {c.checked_in_by_name}</span>}
                    </td>
                    <td className="px-4 py-2 text-muted-foreground hidden md:table-cell">{c.condition_out || '--'}</td>
                    <td className="px-4 py-2 text-muted-foreground hidden md:table-cell">{c.condition_in || '--'}</td>
                    <td className="px-4 py-2">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                        c.checked_in_at ? 'bg-emerald-500/15 text-emerald-400' : 'bg-amber-500/15 text-amber-400'
                      }`}>
                        {c.checked_in_at ? 'Returned' : 'Out'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="px-4 py-8 text-center text-muted-foreground text-sm">No checkout history</div>
        )}
      </div>

      {/* Components */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Cog className="w-4 h-4 text-primary" />
            <h3 className="font-semibold text-foreground">Components</h3>
          </div>
          <button
            onClick={() => setShowComponentForm(!showComponentForm)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-medium hover:opacity-90"
          >
            <Plus className="w-3.5 h-3.5" /> Add Component
          </button>
        </div>

        {/* Add Component Form */}
        {showComponentForm && (
          <div className="px-4 py-3 border-b border-border bg-muted/20 space-y-2">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Name *</label>
                <input type="text" value={componentForm.name}
                  onChange={e => setComponentForm({...componentForm, name: e.target.value})}
                  placeholder="e.g. Front Left Propeller"
                  className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Type *</label>
                <select value={componentForm.component_type}
                  onChange={e => setComponentForm({...componentForm, component_type: e.target.value})}
                  className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm">
                  <option value="propeller">Propeller</option>
                  <option value="motor">Motor</option>
                  <option value="esc">ESC</option>
                  <option value="gimbal">Gimbal</option>
                  <option value="camera">Camera</option>
                  <option value="frame">Frame</option>
                  <option value="landing_gear">Landing Gear</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Serial Number</label>
                <input type="text" value={componentForm.serial_number}
                  onChange={e => setComponentForm({...componentForm, serial_number: e.target.value})}
                  className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Manufacturer</label>
                <input type="text" value={componentForm.manufacturer}
                  onChange={e => setComponentForm({...componentForm, manufacturer: e.target.value})}
                  className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Model</label>
                <input type="text" value={componentForm.model}
                  onChange={e => setComponentForm({...componentForm, model: e.target.value})}
                  className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Status</label>
                <select value={componentForm.status}
                  onChange={e => setComponentForm({...componentForm, status: e.target.value})}
                  className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm">
                  <option value="active">Active</option>
                  <option value="needs_replacement">Needs Replacement</option>
                  <option value="replaced">Replaced</option>
                  <option value="retired">Retired</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Install Date</label>
                <input type="date" value={componentForm.install_date}
                  onChange={e => setComponentForm({...componentForm, install_date: e.target.value})}
                  className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Flight Hours</label>
                <input type="number" step="0.1" value={componentForm.flight_hours}
                  onChange={e => setComponentForm({...componentForm, flight_hours: parseFloat(e.target.value) || 0})}
                  className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Max Flight Hours</label>
                <input type="number" step="0.1" value={componentForm.max_flight_hours}
                  onChange={e => setComponentForm({...componentForm, max_flight_hours: e.target.value})}
                  placeholder="Optional"
                  className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Warranty Expiry</label>
                <input type="date" value={componentForm.warranty_expiry}
                  onChange={e => setComponentForm({...componentForm, warranty_expiry: e.target.value})}
                  className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Replacement Cost</label>
                <input type="number" step="0.01" value={componentForm.replacement_cost}
                  onChange={e => setComponentForm({...componentForm, replacement_cost: e.target.value})}
                  placeholder="$"
                  className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Notes</label>
                <input type="text" value={componentForm.notes}
                  onChange={e => setComponentForm({...componentForm, notes: e.target.value})}
                  className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
            </div>
            <div className="flex gap-2">
              <button
                onClick={async () => {
                  if (!componentForm.name) { toast.error('Name is required'); return }
                  try {
                    await api.post('/components', {
                      ...componentForm,
                      vehicle_id: parseInt(id),
                      max_flight_hours: componentForm.max_flight_hours ? parseFloat(componentForm.max_flight_hours) : null,
                      replacement_cost: componentForm.replacement_cost ? parseFloat(componentForm.replacement_cost) : null,
                      install_date: componentForm.install_date || null,
                      warranty_expiry: componentForm.warranty_expiry || null,
                      serial_number: componentForm.serial_number || null,
                      manufacturer: componentForm.manufacturer || null,
                      model: componentForm.model || null,
                      notes: componentForm.notes || null,
                    })
                    setComponentForm({
                      name: '', component_type: 'propeller', serial_number: '', manufacturer: '', model: '',
                      status: 'active', install_date: '', flight_hours: 0, max_flight_hours: '', warranty_expiry: '',
                      replacement_cost: '', notes: ''
                    })
                    setShowComponentForm(false)
                    loadComponents()
                    toast.success('Component added')
                  } catch (err) { toast.error(err.message) }
                }}
                className="px-4 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-medium hover:opacity-90"
              >
                Save Component
              </button>
              <button onClick={() => setShowComponentForm(false)}
                className="px-4 py-1.5 bg-secondary text-secondary-foreground rounded-lg text-xs hover:opacity-90">
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Components Table */}
        {components.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/30">
                  <th className="text-left px-4 py-2 text-muted-foreground font-medium">Name</th>
                  <th className="text-left px-4 py-2 text-muted-foreground font-medium">Type</th>
                  <th className="text-left px-4 py-2 text-muted-foreground font-medium hidden md:table-cell">Serial</th>
                  <th className="text-left px-4 py-2 text-muted-foreground font-medium">Status</th>
                  <th className="text-left px-4 py-2 text-muted-foreground font-medium hidden md:table-cell">Flight Hours</th>
                  <th className="text-left px-4 py-2 text-muted-foreground font-medium hidden lg:table-cell">Install Date</th>
                  <th className="text-left px-4 py-2 text-muted-foreground font-medium hidden lg:table-cell">Warranty</th>
                  {isAdmin && <th className="text-right px-4 py-2 text-muted-foreground font-medium">Actions</th>}
                </tr>
              </thead>
              <tbody>
                {components.map(c => {
                  const statusColors = {
                    active: 'bg-emerald-500/15 text-emerald-400',
                    needs_replacement: 'bg-amber-500/15 text-amber-400',
                    replaced: 'bg-zinc-500/15 text-zinc-400',
                    retired: 'bg-red-500/15 text-red-400',
                  }
                  const hoursDisplay = c.max_flight_hours
                    ? `${c.flight_hours} / ${c.max_flight_hours}h`
                    : `${c.flight_hours}h`
                  const hoursWarning = c.max_flight_hours && c.flight_hours >= c.max_flight_hours * 0.9
                  return (
                    <tr key={c.id} className="border-b border-border/50 hover:bg-accent/30">
                      <td className="px-4 py-2 text-foreground font-medium">{c.name}</td>
                      <td className="px-4 py-2 text-muted-foreground capitalize">{(c.component_type || '').replace(/_/g, ' ')}</td>
                      <td className="px-4 py-2 text-muted-foreground hidden md:table-cell">{c.serial_number || '--'}</td>
                      <td className="px-4 py-2">
                        <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${statusColors[c.status] || 'bg-zinc-500/15 text-zinc-400'}`}>
                          {(c.status || '').replace(/_/g, ' ')}
                        </span>
                      </td>
                      <td className={`px-4 py-2 hidden md:table-cell ${hoursWarning ? 'text-amber-400 font-medium' : 'text-muted-foreground'}`}>
                        {hoursDisplay}
                      </td>
                      <td className="px-4 py-2 text-muted-foreground hidden lg:table-cell">{c.install_date || '--'}</td>
                      <td className="px-4 py-2 text-muted-foreground hidden lg:table-cell">{c.warranty_expiry || '--'}</td>
                      {isAdmin && (
                        <td className="px-4 py-2 text-right">
                          <button onClick={() => {
                            requestConfirm({
                              title: 'Delete Component',
                              message: 'Delete this component?',
                              onConfirm: async () => {
                                try {
                                  await api.delete(`/components/${c.id}`)
                                  loadComponents()
                                } catch (err) { toast.error(err.message) }
                              }
                            })
                          }} className="p-1.5 text-muted-foreground hover:text-destructive rounded hover:bg-destructive/10">
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      )}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="px-4 py-8 text-center text-muted-foreground text-sm">No components tracked</div>
        )}
      </div>

      {/* Documents */}
      <DocumentUpload entityType="vehicle" entityId={id} folderId={maintenanceFolderId} />
      <ConfirmDialog {...confirmProps} />
    </div>
  )
}
