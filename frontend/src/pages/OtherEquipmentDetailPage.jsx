import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { STATUS_COLORS } from '@/lib/constants'
import { ArrowLeft, Package, Edit } from 'lucide-react'
import DocumentUpload from '@/components/DocumentUpload'
import MaintenanceHistoryCard from '@/components/MaintenanceHistoryCard'
import EditActions from '@/components/EditActions'

const STATUS_OPTIONS = [
  { value: 'active', label: 'Active' },
  { value: 'maintenance', label: 'Maintenance' },
  { value: 'retired', label: 'Retired' },
  { value: 'damaged', label: 'Damaged' },
]

// Inline edit form definition; the fields render from this config.
const EDIT_FIELDS = [
  { key: 'name', label: 'Name' },
  { key: 'category', label: 'Category' },
  { key: 'serial_number', label: 'Serial Number' },
  { key: 'status', label: 'Status', type: 'select', options: STATUS_OPTIONS },
  { key: 'acquired_date', label: 'Acquired Date', type: 'date' },
  { key: 'decommissioned_date', label: 'Decommissioned Date', type: 'date' },
]

export default function OtherEquipmentDetailPage() {
  const { id } = useParams()
  const { isAdmin } = useAuth()
  const toast = useToast()
  const [item, setItem] = useState(null)
  const [maintenance, setMaintenance] = useState([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [editForm, setEditForm] = useState({})
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    Promise.all([
      api.get(`/other-equipment/${id}`),
      api.get(`/maintenance?entity_type=other&entity_id=${id}`).catch(() => []),
    ]).then(([o, m]) => {
      setItem(o)
      setMaintenance(Array.isArray(m) ? m : [])
    }).catch(() => {}).finally(() => setLoading(false))
  }, [id])

  const startEditing = () => {
    const form = { notes: item.notes || '' }
    EDIT_FIELDS.forEach(f => { form[f.key] = item[f.key] || (f.type === 'select' ? 'active' : '') })
    setEditForm(form)
    setEditing(true)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const payload = { ...editForm }
      if (!payload.acquired_date) delete payload.acquired_date
      if (!payload.decommissioned_date) delete payload.decommissioned_date
      const updated = await api.patch(`/other-equipment/${id}`, payload)
      setItem(updated)
      setEditing(false)
    } catch (err) {
      toast.error(err.message)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
  if (!item) return <div className="text-center text-muted-foreground py-12">Equipment item not found</div>

  const inputClass = 'w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring'

  return (
    <div className="space-y-6">
      <Link to="/fleet?tab=other" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="w-4 h-4" /> Back to Fleet
      </Link>

      {/* Header */}
      <div className="bg-card border border-border rounded-xl p-6">
        <div className="flex items-start gap-4">
          <div className="w-16 h-16 rounded-2xl bg-primary/15 flex items-center justify-center text-primary shrink-0">
            <Package className="w-8 h-8" />
          </div>
          <div className="flex-1">
            {editing ? (
              <div className="space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {EDIT_FIELDS.map(f => (
                    <div key={f.key}>
                      <label htmlFor={`edit-${f.key}`} className="block text-xs font-medium text-muted-foreground mb-1">{f.label}</label>
                      {f.type === 'select' ? (
                        <select id={`edit-${f.key}`} value={editForm[f.key]} onChange={e => setEditForm({ ...editForm, [f.key]: e.target.value })} className={inputClass}>
                          {f.options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                        </select>
                      ) : (
                        <input id={`edit-${f.key}`} type={f.type || 'text'} value={editForm[f.key]} onChange={e => setEditForm({ ...editForm, [f.key]: e.target.value })} className={inputClass} />
                      )}
                    </div>
                  ))}
                </div>
                <div>
                  <label htmlFor="edit-notes" className="block text-xs font-medium text-muted-foreground mb-1">Notes</label>
                  <textarea id="edit-notes" value={editForm.notes} onChange={e => setEditForm({ ...editForm, notes: e.target.value })} className={`${inputClass} h-16 resize-none`} />
                </div>
                <EditActions saving={saving} onSave={handleSave} onCancel={() => setEditing(false)} />
              </div>
            ) : (
              <>
                <div className="flex items-center gap-3">
                  <h2 className="text-xl font-bold text-foreground">{item.name}</h2>
                  {isAdmin && (
                    <button onClick={startEditing} className="p-1.5 text-muted-foreground hover:text-foreground rounded-lg hover:bg-accent">
                      <Edit className="w-4 h-4" />
                    </button>
                  )}
                </div>
                <div className="flex flex-wrap gap-4 mt-2 text-sm text-muted-foreground">
                  {item.category && <span>Category: {item.category}</span>}
                  {item.serial_number && <span>S/N: {item.serial_number}</span>}
                  {item.acquired_date && <span>Acquired: {item.acquired_date}</span>}
                  {item.decommissioned_date && <span>Decommissioned: {item.decommissioned_date}</span>}
                </div>
                <span className={`inline-flex mt-2 px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[item.status] || 'bg-zinc-500/15 text-zinc-400'}`}>
                  {item.status || 'unknown'}
                </span>
              </>
            )}
          </div>
        </div>
      </div>

      <MaintenanceHistoryCard records={maintenance} />

      {/* Notes */}
      {item.notes && (
        <div className="bg-card border border-border rounded-xl p-4">
          <h3 className="text-sm font-semibold text-foreground mb-2">Notes</h3>
          <p className="text-sm text-muted-foreground whitespace-pre-wrap">{item.notes}</p>
        </div>
      )}

      {/* Documents */}
      <DocumentUpload entityType="other" entityId={id} />
    </div>
  )
}
