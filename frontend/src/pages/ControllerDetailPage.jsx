import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { STATUS_COLORS } from '@/lib/constants'
import {
  ArrowLeft, Gamepad2, Wrench, Edit, Save, X, Loader2, User, Activity, Calendar
} from 'lucide-react'
import DocumentUpload from '@/components/DocumentUpload'

export default function ControllerDetailPage() {
  const { id } = useParams()
  const { isAdmin } = useAuth()
  const toast = useToast()
  const [controller, setController] = useState(null)
  const [maintenance, setMaintenance] = useState([])
  const [pilot, setPilot] = useState(null)
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [editForm, setEditForm] = useState({})
  const [saving, setSaving] = useState(false)
  const [pilots, setPilots] = useState([])

  useEffect(() => {
    Promise.all([
      api.get(`/controllers/${id}`),
      api.get(`/maintenance?entity_type=controller&entity_id=${id}`).catch(() => []),
      api.get('/pilots').catch(() => []),
    ]).then(([c, m, allPilots]) => {
      setController(c)
      setMaintenance(m)
      setPilots(allPilots)
      if (c.assigned_pilot_id && allPilots.length) {
        const found = allPilots.find(p => p.id === c.assigned_pilot_id)
        setPilot(found || null)
      }
    }).catch(() => {}).finally(() => setLoading(false))
  }, [id])

  const startEditing = () => {
    setEditForm({
      serial_number: controller.serial_number || '',
      nickname: controller.nickname || '',
      manufacturer: controller.manufacturer || '',
      model: controller.model || '',
      status: controller.status || 'active',
      assigned_pilot_id: controller.assigned_pilot_id || '',
      notes: controller.notes || '',
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
      if (payload.assigned_pilot_id === '') {
        payload.assigned_pilot_id = null
      } else {
        payload.assigned_pilot_id = Number.parseInt(payload.assigned_pilot_id, 10) || null
      }
      const updated = await api.patch(`/controllers/${id}`, payload)
      setController(updated)
      if (updated.assigned_pilot_id) {
        const found = pilots.find(p => p.id === updated.assigned_pilot_id)
        setPilot(found || null)
      } else {
        setPilot(null)
      }
      setEditing(false)
    } catch (err) {
      toast.error(err.message)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
  if (!controller) return <div className="text-center text-muted-foreground py-12">Controller not found</div>

  const displayName = controller.nickname || controller.serial_number
  const lastMaintenance = maintenance.length > 0
    ? [...maintenance].sort((a, b) => (b.date || b.performed_date || '').localeCompare(a.date || a.performed_date || ''))[0]
    : null
  const lastMaintenanceDate = lastMaintenance ? (lastMaintenance.date || lastMaintenance.performed_date || '--') : '--'

  return (
    <div className="space-y-6">
      <Link to="/fleet" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="w-4 h-4" /> Back to Fleet
      </Link>

      {/* Header */}
      <div className="bg-card border border-border rounded-xl p-6">
        <div className="flex items-start gap-4">
          <div className="w-16 h-16 rounded-2xl bg-primary/15 flex items-center justify-center text-primary shrink-0">
            <Gamepad2 className="w-8 h-8" />
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
                    <label htmlFor="assigned-pilot" className="block text-xs font-medium text-muted-foreground mb-1">Assigned Pilot</label>
                    <select id="assigned-pilot" value={editForm.assigned_pilot_id} onChange={e => setEditForm({...editForm, assigned_pilot_id: e.target.value})}
                      className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm">
                      <option value="">None</option>
                      {pilots.map(p => <option key={p.id} value={p.id}>{p.full_name || `${p.first_name || ''} ${p.last_name || ''}`.trim() || `Pilot #${p.id}`}</option>)}
                    </select>
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
                  {controller.manufacturer && <span>{controller.manufacturer}</span>}
                  {controller.model && <span>{controller.model}</span>}
                  <span>S/N: {controller.serial_number}</span>
                </div>
                <span className={`inline-flex mt-2 px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[controller.status] || 'bg-zinc-500/15 text-zinc-400'}`}>
                  {controller.status || 'unknown'}
                </span>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-500/15 flex items-center justify-center text-blue-400"><User className="w-5 h-5" /></div>
          <div>
            {pilot ? (
              <Link to={`/pilots/${pilot.id}`} className="text-base font-bold text-primary hover:underline">
                {pilot.full_name || `${pilot.first_name || ''} ${pilot.last_name || ''}`.trim() || `Pilot #${pilot.id}`}
              </Link>
            ) : (
              <p className="text-base font-bold text-foreground">--</p>
            )}
            <p className="text-xs text-muted-foreground">Assigned Pilot</p>
          </div>
        </div>
        <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-500/15 flex items-center justify-center text-emerald-400"><Activity className="w-5 h-5" /></div>
          <div>
            <p className="text-base font-bold text-foreground capitalize">{controller.status || 'unknown'}</p>
            <p className="text-xs text-muted-foreground">Status</p>
          </div>
        </div>
        <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-amber-500/15 flex items-center justify-center text-amber-400"><Calendar className="w-5 h-5" /></div>
          <div>
            <p className="text-base font-bold text-foreground">{lastMaintenanceDate}</p>
            <p className="text-xs text-muted-foreground">Last Maintenance</p>
          </div>
        </div>
      </div>

      {/* Assigned Pilot */}
      {pilot && (
        <div className="bg-card border border-border rounded-xl p-4">
          <h3 className="text-sm font-semibold text-foreground mb-2">Assigned Pilot</h3>
          <Link to={`/pilots/${pilot.id}`} className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-secondary rounded-lg text-sm text-foreground hover:bg-accent/30 transition-colors">
            <User className="w-4 h-4 text-primary" />
            {pilot.full_name || `${pilot.first_name || ''} ${pilot.last_name || ''}`.trim() || `Pilot #${pilot.id}`}
          </Link>
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
                  <td className="px-4 py-2 text-muted-foreground">{m.description || '--'}</td>
                  <td className="px-4 py-2 text-muted-foreground hidden md:table-cell">{m.maintenance_type || m.type || '--'}</td>
                  <td className="px-4 py-2 text-muted-foreground hidden md:table-cell">{m.performed_by || '--'}</td>
                  <td className="px-4 py-2 text-muted-foreground text-right">{m.cost == null ? '--' : `$${Number.parseFloat(m.cost).toFixed(2)}`}</td>
                </tr>
              ))}
              {maintenance.length === 0 && <tr><td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">No maintenance records</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {/* Notes */}
      {controller.notes && (
        <div className="bg-card border border-border rounded-xl p-4">
          <h3 className="text-sm font-semibold text-foreground mb-2">Notes</h3>
          <p className="text-sm text-muted-foreground whitespace-pre-wrap">{controller.notes}</p>
        </div>
      )}

      {/* Documents */}
      <DocumentUpload entityType="controller" entityId={id} />
    </div>
  )
}
