import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { useConfirm } from '@/hooks/useConfirm'
import {
  Search, Upload, X, ChevronLeft, ChevronRight, Edit2, Trash2,
  Camera, User, Info, ZoomIn, Image as ImageIcon
} from 'lucide-react'
import { sortPilotsActiveFirst } from '@/lib/formatters'

const API_BASE = import.meta.env.VITE_API_URL || '/api'

export default function MediaPage() {
  const [photos, setPhotos] = useState([])
  const [pilots, setPilots] = useState([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [showUpload, setShowUpload] = useState(false)
  const [showEdit, setShowEdit] = useState(null)
  const [lightbox, setLightbox] = useState(null)
  const { isPilot } = useAuth()
  const [confirmProps, requestConfirm] = useConfirm()

  const load = useCallback(() => {
    setLoading(true)
    Promise.all([
      api.get('/photos'),
      api.get('/pilots'),
    ]).then(([p, pl]) => {
      setPhotos(p)
      setPilots(pl)
    }).catch(() => {}).finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const filtered = photos.filter(p => {
    const text = `${p.title || ''} ${p.filename || ''} ${(p.pilot_names || []).join(' ')}`.toLowerCase()
    return text.includes(search.toLowerCase())
  })

  const grouped = useMemo(() => {
    const groups = {}
    filtered.forEach(p => {
      const dateStr = p.date_taken ? new Date(p.date_taken).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }) : 'Undated'
      if (!groups[dateStr]) groups[dateStr] = []
      groups[dateStr].push(p)
    })
    return Object.entries(groups).sort((a, b) => {
      if (a[0] === 'Undated') return 1
      if (b[0] === 'Undated') return -1
      return new Date(b[0]) - new Date(a[0])
    })
  }, [filtered])

  // Lightbox keyboard nav
  useEffect(() => {
    if (lightbox === null) return
    const handler = (e) => {
      if (e.key === 'Escape') setLightbox(null)
      if (e.key === 'ArrowLeft') setLightbox(i => i > 0 ? i - 1 : filtered.length - 1)
      if (e.key === 'ArrowRight') setLightbox(i => i < filtered.length - 1 ? i + 1 : 0)
    }
    globalThis.addEventListener('keydown', handler)
    return () => globalThis.removeEventListener('keydown', handler)
  }, [lightbox, filtered.length])

  const handleDelete = (id) => {
    requestConfirm({
      title: 'Delete Photo',
      message: 'Delete this photo permanently?',
      onConfirm: async () => {
        await api.delete(`/photos/${id}`)
        load()
      }
    })
  }

  const formatSize = (bytes) => {
    if (!bytes) return ''
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1048576).toFixed(1)} MB`
  }

  const formatDate = (iso) => {
    if (!iso) return ''
    return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  }

  if (loading) {
    return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <Camera className="w-6 h-6 text-primary" />
          <h1 className="text-xl font-semibold text-foreground">Photo Gallery</h1>
          <span className="text-sm text-muted-foreground">({photos.length} photos)</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search photos..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 pr-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring w-64"
            />
          </div>
          {isPilot && (
            <button
              onClick={() => setShowUpload(true)}
              className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 transition-opacity"
            >
              <Upload className="w-4 h-4" /> Upload
            </button>
          )}
        </div>
      </div>

      {/* Grid */}
      {filtered.length === 0 ? (
        <div className="bg-card border border-border rounded-xl p-12 text-center">
          <ImageIcon className="w-16 h-16 mx-auto text-muted-foreground/40 mb-4" />
          <h3 className="text-lg font-semibold mb-2">No Photos Yet</h3>
          <p className="text-muted-foreground max-w-md mx-auto mb-4">
            Upload photos from flights, training, or equipment inspections to build your gallery.
          </p>
          {isPilot && (
            <button
              onClick={() => setShowUpload(true)}
              className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90"
            >
              <Upload className="w-4 h-4" /> Upload First Photo
            </button>
          )}
        </div>
      ) : (
        <div>
          {grouped.map(([dateLabel, datePhotos]) => (
            <div key={dateLabel}>
              <h3 className="text-sm font-medium text-muted-foreground mb-2 mt-4">{dateLabel}</h3>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
                {datePhotos.map((photo) => {
                  const idx = filtered.indexOf(photo)
                  return (
                    <div
                      key={photo.id}
                      className="group bg-card border border-border rounded-xl overflow-hidden hover:border-primary/50 transition-all hover:shadow-lg hover:shadow-primary/5"
                    >
                      {/* Thumbnail */}
                      <button
                        type="button"
                        className="aspect-[4/3] bg-muted/30 relative cursor-pointer overflow-hidden w-full block"
                        onClick={() => setLightbox(idx)}
                      >
                        <img
                          src={`${API_BASE}/photos/${photo.id}/thumbnail`}
                          alt={photo.title || photo.filename}
                          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                          loading="lazy"
                        />
                        <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors flex items-center justify-center">
                          <ZoomIn className="w-8 h-8 text-white opacity-0 group-hover:opacity-100 transition-opacity drop-shadow-lg" />
                        </div>
                      </button>
                      {/* Info */}
                      <div className="p-3 space-y-1.5">
                        <p className="text-sm font-medium text-foreground truncate" title={photo.title || photo.filename}>
                          {photo.title || photo.filename}
                        </p>
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          {photo.file_size && <span>{formatSize(photo.file_size)}</span>}
                        </div>
                        {photo.pilot_names && photo.pilot_names.length > 0 && (
                          <div className="flex items-center gap-1 text-xs text-muted-foreground">
                            <User className="w-3 h-3 shrink-0" />
                            <span className="truncate">{photo.pilot_names.join(', ')}</span>
                          </div>
                        )}
                        {isPilot && (
                          <div className="flex items-center gap-1 pt-1">
                            <button
                              onClick={(e) => { e.stopPropagation(); setShowEdit(photo) }}
                              className="p-1.5 text-muted-foreground hover:text-primary rounded-md hover:bg-primary/10 transition-colors"
                              title="Edit"
                              aria-label="Edit"
                            >
                              <Edit2 className="w-3.5 h-3.5" />
                            </button>
                            <button
                              onClick={(e) => { e.stopPropagation(); handleDelete(photo.id) }}
                              className="p-1.5 text-muted-foreground hover:text-destructive rounded-md hover:bg-destructive/10 transition-colors"
                              title="Delete"
                              aria-label="Delete"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Lightbox */}
      {lightbox !== null && filtered[lightbox] && (
        <LightboxModal
          photos={filtered}
          index={lightbox}
          onClose={() => setLightbox(null)}
          onPrev={() => setLightbox(i => i > 0 ? i - 1 : filtered.length - 1)}
          onNext={() => setLightbox(i => i < filtered.length - 1 ? i + 1 : 0)}
          formatDate={formatDate}
          formatSize={formatSize}
        />
      )}

      {/* Upload Modal */}
      {showUpload && (
        <UploadModal
          pilots={pilots}
          onClose={() => setShowUpload(false)}
          onSuccess={() => { setShowUpload(false); load() }}
        />
      )}

      {/* Edit Modal */}
      {showEdit && (
        <EditModal
          photo={showEdit}
          pilots={pilots}
          onClose={() => setShowEdit(null)}
          onSuccess={() => { setShowEdit(null); load() }}
        />
      )}
      <ConfirmDialog {...confirmProps} />
    </div>
  )
}

function LightboxModal({ photos, index, onClose, onPrev, onNext, formatDate, formatSize }) {
  const photo = photos[index]
  const [showInfo, setShowInfo] = useState(false)
  const API = import.meta.env.VITE_API_URL || '/api'

  return (
    <div className="fixed inset-0 z-[100] bg-black/90 flex items-center justify-center">
      <button className="absolute inset-0 bg-transparent cursor-default" onClick={onClose} aria-label="Close dialog" />
      <div className="absolute top-4 right-4 flex items-center gap-2 z-10">
        <button
          onClick={() => setShowInfo(s => !s)}
          className="p-2 text-white/70 hover:text-white bg-black/40 rounded-lg transition-colors"
        >
          <Info className="w-5 h-5" />
        </button>
        <button
          onClick={onClose}
          className="p-2 text-white/70 hover:text-white bg-black/40 rounded-lg transition-colors"
          aria-label="Close"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Nav arrows */}
      {photos.length > 1 && (
        <>
          <button
            onClick={onPrev}
            className="absolute left-4 top-1/2 -translate-y-1/2 p-3 text-white/70 hover:text-white bg-black/40 rounded-full transition-colors z-10"
          >
            <ChevronLeft className="w-6 h-6" />
          </button>
          <button
            onClick={onNext}
            className="absolute right-4 top-1/2 -translate-y-1/2 p-3 text-white/70 hover:text-white bg-black/40 rounded-full transition-colors z-10"
          >
            <ChevronRight className="w-6 h-6" />
          </button>
        </>
      )}

      {/* Image */}
      <div className="relative max-w-[90vw] max-h-[85vh] flex items-center justify-center">
        <img
          src={`${API}/photos/${photo.id}/view`}
          alt={photo.title || photo.filename}
          className="max-w-full max-h-[85vh] object-contain rounded-lg shadow-2xl"
        />
      </div>

      {/* Info panel */}
      {showInfo && (
        <div
          className="absolute bottom-0 left-0 right-0 bg-black/80 backdrop-blur-sm p-6 text-white z-10"
        >
          <div className="max-w-2xl mx-auto space-y-2">
            <h3 className="text-lg font-semibold">{photo.title || photo.filename}</h3>
            {photo.description && <p className="text-white/70 text-sm">{photo.description}</p>}
            <div className="flex flex-wrap gap-4 text-sm text-white/60">
              {photo.date_taken && <span>Date: {formatDate(photo.date_taken)}</span>}
              {photo.file_size && <span>Size: {formatSize(photo.file_size)}</span>}
              {photo.pilot_names?.length > 0 && <span>Pilots: {photo.pilot_names.join(', ')}</span>}
            </div>
            <div className="text-xs text-white/40">{index + 1} / {photos.length}</div>
          </div>
        </div>
      )}
    </div>
  )
}

function UploadModal({ pilots, onClose, onSuccess }) {
  const toast = useToast()
  const [files, setFiles] = useState([])
  const [preview, setPreview] = useState(null)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [dateTaken, setDateTaken] = useState('')
  const [selectedPilots, setSelectedPilots] = useState([])
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState('')
  const fileRef = useRef(null)

  const handleFiles = (fileList) => {
    const arr = Array.from(fileList)
    setFiles(arr)
    if (arr.length > 0) {
      const reader = new FileReader()
      reader.onload = (e) => setPreview(e.target.result)
      reader.readAsDataURL(arr[0])
    } else {
      setPreview(null)
    }
  }

  const handleSubmit = async () => {
    if (files.length === 0) return
    setUploading(true)
    try {
      for (let i = 0; i < files.length; i++) {
        setUploadProgress(`Uploading ${i + 1} of ${files.length}...`)
        const fd = new FormData()
        fd.append('file', files[i])
        fd.append('title', title || files[i].name)
        if (description) fd.append('description', description)
        if (dateTaken) fd.append('date_taken', dateTaken)
        if (selectedPilots.length > 0) fd.append('pilot_ids', selectedPilots.join(','))
        await api.upload('/photos/upload', fd)
      }
      onSuccess()
    } catch (err) {
      toast.error('Error uploading: ' + (err.message || 'Unknown error'))
    } finally {
      setUploading(false)
      setUploadProgress('')
    }
  }

  const togglePilot = (id) => {
    setSelectedPilots(prev =>
      prev.includes(id) ? prev.filter(p => p !== id) : [...prev, id]
    )
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
      <button className="absolute inset-0 bg-transparent cursor-default" onClick={onClose} aria-label="Close dialog" />
      <div
        className="relative bg-card border border-border rounded-xl w-full max-w-lg max-h-[90vh] overflow-y-auto"
      >
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h2 className="text-lg font-semibold text-foreground">Upload Photo</h2>
          <button onClick={onClose} className="p-1 text-muted-foreground hover:text-foreground"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-4 space-y-4">
          {/* File drop */}
          <button
            type="button" onClick={() => fileRef.current?.click()}
            className="border-2 border-dashed border-border rounded-xl p-6 text-center cursor-pointer hover:border-primary/50 transition-colors w-full"
          >
            {preview ? (
              <div>
                <img src={preview} alt="Preview" className="max-h-48 mx-auto rounded-lg object-contain" />
                {files.length > 1 && (
                  <p className="text-xs text-muted-foreground mt-2">{files.length} files selected</p>
                )}
              </div>
            ) : (
              <div className="space-y-2">
                <Camera className="w-10 h-10 mx-auto text-muted-foreground/50" />
                <p className="text-sm text-muted-foreground">Click to select photos (multiple supported)</p>
              </div>
            )}
            <input ref={fileRef} type="file" accept="image/*" multiple className="hidden" onChange={(e) => handleFiles(e.target.files)} />
          </button>

          <div>
            <label htmlFor="title" className="block text-sm font-medium text-foreground mb-1">Title</label>
            <input id="title"
              value={title} onChange={(e) => setTitle(e.target.value)}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder="Optional title"
            />
          </div>

          <div>
            <label htmlFor="description" className="block text-sm font-medium text-foreground mb-1">Description</label>
            <textarea id="description"
              value={description} onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring resize-none"
              placeholder="Optional description"
            />
          </div>

          <div>
            <label htmlFor="date-taken" className="block text-sm font-medium text-foreground mb-1">Date Taken</label>
            <input id="date-taken"
              type="date" value={dateTaken} onChange={(e) => setDateTaken(e.target.value)}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>

          {/* Pilot multi-select */}
          <div>
            <p className="block text-sm font-medium text-foreground mb-1">Associated Pilots</p>
            <div className="flex flex-wrap gap-2 max-h-32 overflow-y-auto p-2 bg-secondary border border-border rounded-lg">
              {sortPilotsActiveFirst(pilots).map(p => {
                const name = `${p.first_name} ${p.last_name}`.trim()
                const sel = selectedPilots.includes(p.id)
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => togglePilot(p.id)}
                    className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
                      sel ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground hover:bg-muted/80'
                    }`}
                  >
                    {name}
                  </button>
                )
              })}
              {pilots.length === 0 && <span className="text-xs text-muted-foreground">No pilots available</span>}
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-2 p-4 border-t border-border">
          <button onClick={onClose} className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors">Cancel</button>
          <button
            onClick={handleSubmit}
            disabled={files.length === 0 || uploading}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            {(() => {
              if (uploading) return uploadProgress || 'Uploading...'
              if (files.length > 1) return `Upload ${files.length} Photos`
              return 'Upload'
            })()}
          </button>
        </div>
      </div>
    </div>
  )
}

function EditModal({ photo, pilots, onClose, onSuccess }) {
  const [title, setTitle] = useState(photo.title || '')
  const [description, setDescription] = useState(photo.description || '')
  const [dateTaken, setDateTaken] = useState(photo.date_taken ? photo.date_taken.split('T')[0] : '')
  const [selectedPilots, setSelectedPilots] = useState(photo.pilot_ids || [])
  const [saving, setSaving] = useState(false)

  const togglePilot = (id) => {
    setSelectedPilots(prev =>
      prev.includes(id) ? prev.filter(p => p !== id) : [...prev, id]
    )
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const fd = new FormData()
      fd.append('title', title)
      fd.append('description', description)
      if (dateTaken) fd.append('date_taken', dateTaken)
      fd.append('pilot_ids', selectedPilots.join(','))

      const token = localStorage.getItem('token')
      const API_URL = import.meta.env.VITE_API_URL || '/api'
      const res = await fetch(`${API_URL}/photos/${photo.id}`, {
        method: 'PATCH',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      })
      if (res.status === 401) {
        localStorage.removeItem('token')
        localStorage.removeItem('user')
        globalThis.location.href = '/login'
        throw new Error('Unauthorized')
      }
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || 'Update failed')
      }
      onSuccess()
    } catch (err) {
      // Error is handled by caller
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
      <button className="absolute inset-0 bg-transparent cursor-default" onClick={onClose} aria-label="Close dialog" />
      <div
        className="relative bg-card border border-border rounded-xl w-full max-w-lg"
      >
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h2 className="text-lg font-semibold text-foreground">Edit Photo</h2>
          <button onClick={onClose} className="p-1 text-muted-foreground hover:text-foreground"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-4 space-y-4">
          <div>
            <label htmlFor="title-1" className="block text-sm font-medium text-foreground mb-1">Title</label>
            <input id="title-1"
              value={title} onChange={(e) => setTitle(e.target.value)}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          <div>
            <label htmlFor="description-1" className="block text-sm font-medium text-foreground mb-1">Description</label>
            <textarea id="description-1"
              value={description} onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring resize-none"
            />
          </div>
          <div>
            <label htmlFor="date-taken-1" className="block text-sm font-medium text-foreground mb-1">Date Taken</label>
            <input id="date-taken-1"
              type="date" value={dateTaken} onChange={(e) => setDateTaken(e.target.value)}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          <div>
            <p className="block text-sm font-medium text-foreground mb-1">Associated Pilots</p>
            <div className="flex flex-wrap gap-2 max-h-32 overflow-y-auto p-2 bg-secondary border border-border rounded-lg">
              {sortPilotsActiveFirst(pilots).map(p => {
                const name = `${p.first_name} ${p.last_name}`.trim()
                const sel = selectedPilots.includes(p.id)
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => togglePilot(p.id)}
                    className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
                      sel ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground hover:bg-muted/80'
                    }`}
                  >
                    {name}
                  </button>
                )
              })}
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-2 p-4 border-t border-border">
          <button onClick={onClose} className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors">Cancel</button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}
