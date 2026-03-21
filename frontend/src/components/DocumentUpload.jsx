import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { FileText, Upload, Trash2, Loader2, ExternalLink } from 'lucide-react'

export default function DocumentUpload({ entityType, entityId }) {
  const [documents, setDocuments] = useState([])
  const [uploading, setUploading] = useState(false)
  const [showUpload, setShowUpload] = useState(false)
  const [title, setTitle] = useState('')
  const [docType, setDocType] = useState('general')
  const { isAdmin } = useAuth()

  const fetchDocs = useCallback(() => {
    const token = localStorage.getItem('token')
    fetch(`/api/documents?entity_type=${entityType}&entity_id=${entityId}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then(r => r.json())
      .then(setDocuments)
      .catch(console.error)
  }, [entityType, entityId])

  useEffect(() => {
    fetchDocs()
  }, [fetchDocs])

  const handleUpload = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('entity_type', entityType)
      formData.append('entity_id', entityId)
      formData.append('document_type', docType)
      formData.append('title', title || file.name)
      const token = localStorage.getItem('token')
      const res = await fetch('/api/documents/upload', {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Upload failed')
      }
      setTitle('')
      setDocType('general')
      setShowUpload(false)
      fetchDocs()
    } catch (err) {
      alert(err.message)
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  const handleDelete = async (docId) => {
    if (!confirm('Delete this document?')) return
    try {
      const token = localStorage.getItem('token')
      const res = await fetch(`/api/documents/${docId}`, {
        method: 'DELETE',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!res.ok) throw new Error('Delete failed')
      fetchDocs()
    } catch (err) {
      alert(err.message)
    }
  }

  const DOC_TYPES = [
    { value: 'general', label: 'General' },
    { value: 'part_107', label: 'Part 107' },
    { value: 'faa_registration', label: 'FAA Registration' },
    { value: 'insurance', label: 'Insurance' },
    { value: 'nist_cert', label: 'NIST Certificate' },
    { value: 'maintenance', label: 'Maintenance Record' },
    { value: 'training', label: 'Training Certificate' },
    { value: 'other', label: 'Other' },
  ]

  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileText className="w-4 h-4 text-primary" />
          <h3 className="font-semibold text-foreground">Documents</h3>
          <span className="text-xs text-muted-foreground">({documents.length})</span>
        </div>
        {isAdmin && (
          <button
            onClick={() => setShowUpload(!showUpload)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-medium hover:opacity-90"
          >
            <Upload className="w-3.5 h-3.5" /> Upload
          </button>
        )}
      </div>

      {showUpload && isAdmin && (
        <div className="px-4 py-3 border-b border-border bg-muted/20 space-y-2">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <div>
              <label className="block text-xs font-medium text-foreground mb-1">Title</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Document title (optional)"
                className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-foreground mb-1">Type</label>
              <select
                value={docType}
                onChange={(e) => setDocType(e.target.value)}
                className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm"
              >
                {DOC_TYPES.map(dt => (
                  <option key={dt.value} value={dt.value}>{dt.label}</option>
                ))}
              </select>
            </div>
          </div>
          <label className="flex items-center gap-2 px-3 py-2 bg-secondary border border-border border-dashed rounded-lg cursor-pointer hover:bg-accent/30 transition-colors">
            {uploading ? (
              <Loader2 className="w-4 h-4 text-primary animate-spin" />
            ) : (
              <Upload className="w-4 h-4 text-primary" />
            )}
            <span className="text-sm text-muted-foreground">
              {uploading ? 'Uploading...' : 'Choose file...'}
            </span>
            <input
              type="file"
              className="hidden"
              onChange={handleUpload}
              disabled={uploading}
            />
          </label>
        </div>
      )}

      <div className="divide-y divide-border/50">
        {documents.map(doc => (
          <div
            key={doc.id}
            className="flex items-center gap-3 px-4 py-3 hover:bg-accent/30 transition-colors"
          >
            <FileText className="w-4 h-4 text-muted-foreground shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-foreground truncate">{doc.title || doc.filename}</p>
              <p className="text-xs text-muted-foreground">
                {doc.document_type !== 'general' ? doc.document_type.replace(/_/g, ' ') + ' | ' : ''}
                {doc.mime_type}
              </p>
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <button
                onClick={() => window.open(doc.view_url, '_blank')}
                className="p-1.5 text-muted-foreground hover:text-foreground rounded hover:bg-accent/30"
                title="View"
              >
                <ExternalLink className="w-3.5 h-3.5" />
              </button>
              {isAdmin && (
                <button
                  onClick={() => handleDelete(doc.id)}
                  className="p-1.5 text-muted-foreground hover:text-destructive rounded hover:bg-destructive/10"
                  title="Delete"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>
        ))}
        {documents.length === 0 && (
          <div className="px-4 py-8 text-center text-muted-foreground text-sm">No documents uploaded</div>
        )}
      </div>
    </div>
  )
}
