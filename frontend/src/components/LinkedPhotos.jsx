import { useState, useEffect, useCallback } from 'react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { Image as ImageIcon, Plus, X, Loader2 } from 'lucide-react'

const API_BASE = '/api'

/** Thumbnail URL for a photo, falling back to the by-id endpoint. */
function thumbSrc(photo) {
  const path = photo.thumbnail_url || `/photos/${photo.id}/thumbnail`
  return `${API_BASE}${path}`
}

/**
 * Linked-photos section for a flight or incident. Shows attached photo
 * thumbnails and, for supervisors and above, lets you attach existing photos
 * (from the Media gallery) or unlink them.
 * @param {{ entityType: 'flight'|'incident', entityId: number|string }} props
 */
export default function LinkedPhotos({ entityType, entityId }) {
  const { isSupervisor } = useAuth()
  const toast = useToast()
  const [linked, setLinked] = useState([])
  const [loading, setLoading] = useState(true)
  const [pickerOpen, setPickerOpen] = useState(false)

  const loadLinked = useCallback(() => {
    api.get(`/photos?${entityType}_id=${entityId}`)
      .then(p => setLinked(Array.isArray(p) ? p : []))
      .catch(() => setLinked([]))
      .finally(() => setLoading(false))
  }, [entityType, entityId])

  useEffect(() => { loadLinked() }, [loadLinked])

  const unlink = async (photoId) => {
    try {
      await api.delete(`/photos/${photoId}/${entityType}/${entityId}`)
      loadLinked()
    } catch (err) { toast.error(err.message) }
  }

  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-border flex items-center gap-2">
        <ImageIcon className="w-4 h-4 text-primary" />
        <h3 className="font-semibold text-foreground">Photos</h3>
        {linked.length > 0 && <span className="text-xs text-muted-foreground">({linked.length})</span>}
        {isSupervisor && (
          <button onClick={() => setPickerOpen(true)}
            className="ml-auto flex items-center gap-1 px-2.5 py-1 bg-secondary text-secondary-foreground rounded-lg text-xs font-medium hover:opacity-90">
            <Plus className="w-3.5 h-3.5" /> Attach photos
          </button>
        )}
      </div>
      <div className="p-4">
        {linkedBody({ loading, linked, isSupervisor, unlink })}
      </div>
      {pickerOpen && (
        <PhotoPicker entityType={entityType} entityId={entityId} linkedIds={linked.map(p => p.id)}
          onClose={() => setPickerOpen(false)} onAttached={() => { setPickerOpen(false); loadLinked() }} />
      )}
    </div>
  )
}

// Loading, then nothing attached, then the grid.
function linkedBody({ loading, linked, isSupervisor, unlink }) {
  if (loading) {
    return <div className="flex justify-center py-6"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /></div>
  }
  if (linked.length === 0) {
    return <p className="text-sm text-muted-foreground">No photos linked.</p>
  }
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
      {linked.map(photo => (
        <div key={photo.id} className="relative group">
          <img src={thumbSrc(photo)}
            alt={photo.title || photo.filename}
            className="w-full h-28 object-cover rounded-lg border border-border" />
          {isSupervisor && (
            <button onClick={() => unlink(photo.id)} title="Unlink" aria-label="Unlink photo"
              className="absolute top-1 right-1 p-1 bg-black/60 text-white rounded-full opacity-0 group-hover:opacity-100 transition-opacity hover:bg-black/80">
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      ))}
    </div>
  )
}

// Loading, then nothing left to attach, then the pickable grid.
function pickerBody({ loading, available, selected, toggle }) {
  if (loading) {
    return <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>
  }
  if (available.length === 0) {
    return <p className="text-sm text-muted-foreground py-6 text-center">No more photos to attach. Upload photos on the Media page first.</p>
  }
  return (
    <div className="grid grid-cols-3 sm:grid-cols-4 gap-3">
      {available.map(photo => {
        const isSel = selected.has(photo.id)
        return (
          <button key={photo.id} type="button" onClick={() => toggle(photo.id)}
            className={`relative rounded-lg overflow-hidden border-2 ${isSel ? 'border-primary' : 'border-border'}`}>
            <img src={thumbSrc(photo)}
              alt={photo.title || photo.filename} className="w-full h-24 object-cover" />
            {isSel && <span className="absolute top-1 right-1 w-4 h-4 bg-primary rounded-full border-2 border-white" />}
          </button>
        )
      })}
    </div>
  )
}

function PhotoPicker({ entityType, entityId, linkedIds, onClose, onAttached }) {
  const toast = useToast()
  const [all, setAll] = useState([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(() => new Set())
  const [saving, setSaving] = useState(false)
  const attachLabel = selected.size > 0 ? `Attach ${selected.size}` : 'Attach'

  useEffect(() => {
    api.get('/photos')
      .then(p => setAll(Array.isArray(p) ? p : []))
      .catch(() => setAll([]))
      .finally(() => setLoading(false))
  }, [])

  const linkedSet = new Set(linkedIds)
  const available = all.filter(p => !linkedSet.has(p.id))

  const toggle = (id) => setSelected(prev => {
    const next = new Set(prev)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  })

  const attach = async () => {
    setSaving(true)
    const ids = [...selected]
    try {
      const results = await Promise.allSettled(
        ids.map(id => api.post(`/photos/${id}/${entityType}/${entityId}`))
      )
      const failed = results.filter(r => r.status === 'rejected')
      if (failed.length > 0) {
        toast.error(`${failed.length} of ${ids.length} photo${ids.length === 1 ? '' : 's'} failed to attach`)
      }
    } finally {
      setSaving(false)
      onAttached()
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <button className="absolute inset-0 bg-transparent cursor-default" onClick={onClose} aria-label="Close dialog" />
      <div className="relative bg-popover border border-border rounded-xl p-6 w-full max-w-2xl shadow-xl max-h-[80vh] flex flex-col">
        <h2 className="text-lg font-semibold text-foreground mb-3">Attach photos</h2>
        <div className="flex-1 overflow-y-auto">
          {pickerBody({ loading, available, selected, toggle })}
        </div>
        <div className="flex gap-2 mt-4">
          <button onClick={attach} disabled={selected.size === 0 || saving}
            className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : attachLabel}
          </button>
          <button onClick={onClose} className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm">Cancel</button>
        </div>
      </div>
    </div>
  )
}
