import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { formatDuration } from '@/lib/utils'
import { STATUS_COLORS } from '@/lib/constants'
import {
  ArrowLeft, Paperclip, Clock, Wrench, Edit, Save, X, Loader2, Users
} from 'lucide-react'
import { QuadcopterIcon } from '@/components/icons/QuadcopterIcon'
import DocumentUpload from '@/components/DocumentUpload'

export default function AttachmentDetailPage() {
  const { id } = useParams()
  const { isAdmin } = useAuth()
  const toast = useToast()
  const [attachment, setAttachment] = useState(null)
  const [stats, setStats] = useState(null)
  const [flights, setFlights] = useState([])
  const [maintenance, setMaintenance] = useState([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [editForm, setEditForm] = useState({})
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    Promise.all([
      api.get(`/attachments/${id}`),
      api.get(`/attachments/${id}/stats`).catch(() => null),
      api.get(`/attachments/${id}/flights`).catch(() => []),
      api.get(`/maintenance?entity_type=attachment&entity_id=${id}`).catch(() => []),
    ]).then(([a, st, fl, m]) => {
      setAttachment(a)
      setStats(st)
      setFlights(Array.isArray(fl) ? fl : [])
      setMaintenance(Array.isArray(m) ? m : [])
    }).catch(() => {}).finally(() => setLoading(false))
  }, [id])

  const startEditing = () => {
    setEditForm({
      serial_number: attachment.serial_number || '',
      name: attachment.name || '',
      type: attachment.type || '',
      manufacturer: attachment.manufacturer || '',
      model: attachment.model || '',
      status: attachment.status || 'active',
      notes: attachment.notes || '',
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
      const updated = await api.patch(`/attachments/${id}`, payload)
      setAttachment(updated)
      setEditing(false)
    } catch (err) {
      toast.error(err.message)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
  if (!attachment) return <div className="text-center text-muted-foreground py-12">Attachment not found</div>

  const displayName = attachment.name || attachment.serial_number

  return (
    <div className="space-y-6">
      <Link to="/fleet?tab=attachments" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="w-4 h-4" /> Back to Fleet
      </Link>

      {/* Header */}
      <div className="bg-card border border-border rounded-xl p-6">
        <div className="flex items-start gap-4">
          <div className="w-16 h-16 rounded-2xl bg-primary/15 flex items-center justify-center text-primary shrink-0">
            <Paperclip className="w-8 h-8" />
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
                    <label htmlFor="edit-type" className="block text-xs font-medium text-muted-foreground mb-1">Type</label>
                    <input id="edit-type" type="text" value={editForm.type} onChange={e => setEditForm({...editForm, type: e.target.value})}
                      className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                  </div>
                  <div>
                    <label htmlFor="edit-manufacturer" className="block text-xs font-medium text-muted-foreground mb-1">Manufacturer</label>
                    <input id="edit-manufacturer" type="text" value={editForm.manufacturer} onChange={e => setEditForm({...editForm, manufacturer: e.target.value})}
                      className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                  </div>
                  <div>
                    <label htmlFor="edit-model" className="block text-xs font-medium text-muted-foreground mb-1">Model</label>
                    <input id="edit-model" type="text" value={editForm.model} onChange={e => setEditForm({...editForm, model: e.target.value})}
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
                  {attachment.manufacturer && <span>{attachment.manufacturer}</span>}
                  {attachment.model && <span>{attachment.model}</span>}
                  {attachment.type && <span>Type: {attachment.type}</span>}
                  <span>S/N: {attachment.serial_number}</span>
                </div>
                <span className={`inline-flex mt-2 px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[attachment.status] || 'bg-zinc-500/15 text-zinc-400'}`}>
                  {attachment.status || 'unknown'}
                </span>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-500/15 flex items-center justify-center text-blue-400"><QuadcopterIcon className="w-5 h-5" /></div>
          <div><p className="text-2xl font-bold text-foreground">{stats?.total_flights || 0}</p><p className="text-xs text-muted-foreground">Total Flights</p></div>
        </div>
        <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-amber-500/15 flex items-center justify-center text-amber-400"><Clock className="w-5 h-5" /></div>
          <div><p className="text-2xl font-bold text-foreground">{stats?.total_hours == null ? '--' : `${stats.total_hours}h`}</p><p className="text-xs text-muted-foreground">Total Hours</p></div>
        </div>
        <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-500/15 flex items-center justify-center text-emerald-400"><Users className="w-5 h-5" /></div>
          <div><p className="text-2xl font-bold text-foreground">{stats?.unique_pilots || 0}</p><p className="text-xs text-muted-foreground">Unique Pilots</p></div>
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
                <th className="text-left px-4 py-2 text-muted-foreground font-medium hidden md:table-cell">Vehicle</th>
                <th className="text-left px-4 py-2 text-muted-foreground font-medium hidden md:table-cell">Purpose</th>
                <th className="text-left px-4 py-2 text-muted-foreground font-medium">Duration</th>
                <th className="text-left px-4 py-2 text-muted-foreground font-medium hidden lg:table-cell">Position</th>
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
                  <td className="px-4 py-2 text-foreground hidden md:table-cell">
                    {f.vehicle_id ? (
                      <Link to={`/fleet/vehicles/${f.vehicle_id}`} className="text-primary hover:underline">{f.vehicle_name || `Vehicle #${f.vehicle_id}`}</Link>
                    ) : '--'}
                  </td>
                  <td className="px-4 py-2 text-foreground hidden md:table-cell">{f.purpose || '--'}</td>
                  <td className="px-4 py-2 text-foreground">{formatDuration(f.duration_seconds)}</td>
                  <td className="px-4 py-2 text-foreground hidden lg:table-cell">{f.position || '--'}</td>
                </tr>
              ))}
              {flights.length === 0 && <tr><td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">No flights recorded for this attachment</td></tr>}
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
      {attachment.notes && (
        <div className="bg-card border border-border rounded-xl p-4">
          <h3 className="text-sm font-semibold text-foreground mb-2">Notes</h3>
          <p className="text-sm text-muted-foreground whitespace-pre-wrap">{attachment.notes}</p>
        </div>
      )}

      {/* Documents */}
      <DocumentUpload entityType="attachment" entityId={id} />
    </div>
  )
}
