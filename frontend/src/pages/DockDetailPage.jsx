import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { STATUS_COLORS } from '@/lib/constants'
import {
  ArrowLeft, Warehouse, Wrench, Edit, Save, X, Loader2, MapPin
} from 'lucide-react'
import { MapContainer, TileLayer, Marker } from 'react-leaflet'
import L from 'leaflet'
import DocumentUpload from '@/components/DocumentUpload'

// Fix default marker icon paths for bundled Leaflet builds
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

function hasValidCoords(dock) {
  if (dock.lat == null || dock.lon == null) return false
  const lat = Number(dock.lat)
  const lon = Number(dock.lon)
  return !Number.isNaN(lat) && !Number.isNaN(lon)
}

export default function DockDetailPage() {
  const { id } = useParams()
  const { isAdmin } = useAuth()
  const toast = useToast()
  const [dock, setDock] = useState(null)
  const [maintenance, setMaintenance] = useState([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [editForm, setEditForm] = useState({})
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    Promise.all([
      api.get(`/docks/${id}`),
      api.get(`/maintenance?entity_type=dock&entity_id=${id}`).catch(() => []),
    ]).then(([d, m]) => {
      setDock(d)
      setMaintenance(Array.isArray(m) ? m : [])
    }).catch(() => {}).finally(() => setLoading(false))
  }, [id])

  const startEditing = () => {
    setEditForm({
      serial_number: dock.serial_number || '',
      name: dock.name || '',
      location_name: dock.location_name || '',
      lat: dock.lat ?? '',
      lon: dock.lon ?? '',
      status: dock.status || 'active',
      notes: dock.notes || '',
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
      if (payload.lat === '') {
        delete payload.lat
      } else {
        payload.lat = Number.parseFloat(payload.lat)
      }
      if (payload.lon === '') {
        delete payload.lon
      } else {
        payload.lon = Number.parseFloat(payload.lon)
      }
      const updated = await api.patch(`/docks/${id}`, payload)
      setDock(updated)
      setEditing(false)
    } catch (err) {
      toast.error(err.message)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
  if (!dock) return <div className="text-center text-muted-foreground py-12">Dock not found</div>

  const displayName = dock.name || dock.serial_number
  const showMap = hasValidCoords(dock)

  return (
    <div className="space-y-6">
      <Link to="/fleet?tab=docks" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="w-4 h-4" /> Back to Fleet
      </Link>

      {/* Header */}
      <div className="bg-card border border-border rounded-xl p-6">
        <div className="flex items-start gap-4">
          <div className="w-16 h-16 rounded-2xl bg-primary/15 flex items-center justify-center text-primary shrink-0">
            <Warehouse className="w-8 h-8" />
          </div>
          <div className="flex-1">
            {editing ? (
              <div className="space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label htmlFor="edit-serial-number" className="block text-xs font-medium text-muted-foreground mb-1">Serial Number</label>
                    <input id="edit-serial-number" type="text" value={editForm.serial_number} onChange={e => setEditForm({...editForm, serial_number: e.target.value})}
                      className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                  </div>
                  <div>
                    <label htmlFor="edit-name" className="block text-xs font-medium text-muted-foreground mb-1">Name</label>
                    <input id="edit-name" type="text" value={editForm.name} onChange={e => setEditForm({...editForm, name: e.target.value})}
                      className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                  </div>
                  <div>
                    <label htmlFor="edit-location-name" className="block text-xs font-medium text-muted-foreground mb-1">Location Name</label>
                    <input id="edit-location-name" type="text" value={editForm.location_name} onChange={e => setEditForm({...editForm, location_name: e.target.value})}
                      className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                  </div>
                  <div>
                    <label htmlFor="edit-lat" className="block text-xs font-medium text-muted-foreground mb-1">Latitude</label>
                    <input id="edit-lat" type="text" value={editForm.lat} onChange={e => setEditForm({...editForm, lat: e.target.value})}
                      className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                  </div>
                  <div>
                    <label htmlFor="edit-lon" className="block text-xs font-medium text-muted-foreground mb-1">Longitude</label>
                    <input id="edit-lon" type="text" value={editForm.lon} onChange={e => setEditForm({...editForm, lon: e.target.value})}
                      className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                  </div>
                  <div>
                    <label htmlFor="edit-status" className="block text-xs font-medium text-muted-foreground mb-1">Status</label>
                    <select id="edit-status" value={editForm.status} onChange={e => setEditForm({...editForm, status: e.target.value})}
                      className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm">
                      <option value="active">Active</option>
                      <option value="inactive">Inactive</option>
                      <option value="maintenance">Maintenance</option>
                      <option value="retired">Retired</option>
                    </select>
                  </div>
                </div>
                <div>
                  <label htmlFor="edit-notes" className="block text-xs font-medium text-muted-foreground mb-1">Notes</label>
                  <textarea id="edit-notes" value={editForm.notes} onChange={e => setEditForm({...editForm, notes: e.target.value})}
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
                  <span>S/N: {dock.serial_number}</span>
                  {dock.location_name && <span><MapPin className="w-3 h-3 inline mr-1" />{dock.location_name}</span>}
                  {showMap && <span>{Number(dock.lat).toFixed(5)}, {Number(dock.lon).toFixed(5)}</span>}
                </div>
                <span className={`inline-flex mt-2 px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[dock.status] || 'bg-zinc-500/15 text-zinc-400'}`}>
                  {dock.status || 'unknown'}
                </span>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Location Map */}
      {showMap && (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-border flex items-center gap-2">
            <MapPin className="w-4 h-4 text-primary" />
            <h3 className="font-semibold text-foreground">Location</h3>
          </div>
          <div style={{ height: 300 }}>
            <MapContainer center={[Number(dock.lat), Number(dock.lon)]} zoom={15} style={{ height: '100%', width: '100%' }} scrollWheelZoom={true}>
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
              <Marker position={[Number(dock.lat), Number(dock.lon)]} />
            </MapContainer>
          </div>
        </div>
      )}

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
                  <td className="px-4 py-2 text-foreground">{m.description || '--'}</td>
                  <td className="px-4 py-2 text-foreground hidden md:table-cell">{m.maintenance_type || m.type || '--'}</td>
                  <td className="px-4 py-2 text-foreground hidden md:table-cell">{m.performed_by || '--'}</td>
                  <td className="px-4 py-2 text-foreground text-right">{m.cost == null ? '--' : `$${Number.parseFloat(m.cost).toFixed(2)}`}</td>
                </tr>
              ))}
              {maintenance.length === 0 && <tr><td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">No maintenance records</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {/* Notes */}
      {dock.notes && (
        <div className="bg-card border border-border rounded-xl p-4">
          <h3 className="text-sm font-semibold text-foreground mb-2">Notes</h3>
          <p className="text-sm text-muted-foreground whitespace-pre-wrap">{dock.notes}</p>
        </div>
      )}

      {/* Documents */}
      <DocumentUpload entityType="dock" entityId={id} />
    </div>
  )
}
