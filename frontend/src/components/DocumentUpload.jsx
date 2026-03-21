import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { FileText, Upload, Trash2, Loader2, ExternalLink, Edit, Save, X } from 'lucide-react'

export default function DocumentUpload({ entityType, entityId }) {
  const [documents, setDocuments] = useState([])
  const [uploading, setUploading] = useState(false)
  const [showUpload, setShowUpload] = useState(false)
  const [title, setTitle] = useState('')
  const [docType, setDocType] = useState('general')
  const [selectedFile, setSelectedFile] = useState(null)
  const [editingDoc, setEditingDoc] = useState(null)
  const [editForm, setEditForm] = useState({ title: '', document_type: '' })
  const [editSaving, setEditSaving] = useState(false)
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

  const handleFileSelect = (e) => {
    const file = e.target.files[0]
    if (!file) return
    setSelectedFile(file)
    if (!title) setTitle(file.name)
  }

  const handleUpload = async () => {
    if (!selectedFile) return
    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', selectedFile)
      formData.append('entity_type', entityType)
      formData.append('entity_id', entityId)
      formData.append('document_type', docType)
      formData.append('title', title || selectedFile.name)
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
      setSelectedFile(null)
      setShowUpload(false)
      fetchDocs()
    } catch (err) {
      alert(err.message)
    } finally {
      setUploading(false)
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

  const startEditDoc = (doc) => {
    setEditingDoc(doc.id)
    setEditForm({ title: doc.title || '', document_type: doc.document_type || 'general' })
  }

  const cancelEditDoc = () => {
    setEditingDoc(null)
    setEditForm({ title: '', document_type: '' })
  }

  const saveEditDoc = async (docId) => {
    setEditSaving(true)
    try {
      const token = localStorage.getItem('token')
      const params = new URLSearchParams()
      if (editForm.title) params.set('title', editForm.title)
      if (editForm.document_type) params.set('document_type', editForm.document_type)
      const res = await fetch(`/api/documents/${docId}?${params.toString()}`, {
        method: 'PATCH',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!res.ok) throw new Error('Update failed')
      setEditingDoc(null)
      setEditForm({ title: '', document_type: '' })
      fetchDocs()
    } catch (err) {
      alert(err.message)
    } finally {
      setEditSaving(false)
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
            onClick={() => { setShowUpload(!showUpload); setSelectedFile(null); setTitle(''); setDocType('general') }}
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
            <Upload className="w-4 h-4 text-primary" />
            <span className="text-sm text-muted-foreground">
              {selectedFile ? selectedFile.name : 'Choose file...'}
            </span>
            <input
              type="file"
              className="hidden"
              onChange={handleFileSelect}
            />
          </label>
          {selectedFile && (
            <div className="flex gap-2">
              <button
                onClick={handleUpload}
                disabled={uploading}
                className="flex items-center gap-1.5 px-4 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-medium hover:opacity-90 disabled:opacity-50"
              >
                {uploading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                {uploading ? 'Uploading...' : 'Save'}
              </button>
              <button
                onClick={() => { setSelectedFile(null); setTitle('') }}
                className="px-4 py-1.5 bg-secondary text-secondary-foreground rounded-lg text-xs hover:opacity-90"
              >
                Cancel
              </button>
            </div>
          )}
        </div>
      )}

      <div className="divide-y divide-border/50">
        {documents.map(doc => (
          <div
            key={doc.id}
            className="flex items-center gap-3 px-4 py-3 hover:bg-accent/30 transition-colors"
          >
            <FileText className="w-4 h-4 text-muted-foreground shrink-0" />
            {editingDoc === doc.id ? (
              <div className="flex-1 min-w-0 space-y-1.5">
                <input
                  type="text"
                  value={editForm.title}
                  onChange={(e) => setEditForm({ ...editForm, title: e.target.value })}
                  className="w-full px-2 py-1 bg-secondary border border-border rounded text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                />
                <select
                  value={editForm.document_type}
                  onChange={(e) => setEditForm({ ...editForm, document_type: e.target.value })}
                  className="w-full px-2 py-1 bg-secondary border border-border rounded text-foreground text-sm"
                >
                  {DOC_TYPES.map(dt => (
                    <option key={dt.value} value={dt.value}>{dt.label}</option>
                  ))}
                </select>
                <div className="flex gap-1.5">
                  <button
                    onClick={() => saveEditDoc(doc.id)}
                    disabled={editSaving}
                    className="flex items-center gap-1 px-2.5 py-1 bg-primary text-primary-foreground rounded text-xs font-medium hover:opacity-90 disabled:opacity-50"
                  >
                    <Save className="w-3 h-3" /> {editSaving ? 'Saving...' : 'Save'}
                  </button>
                  <button
                    onClick={cancelEditDoc}
                    className="flex items-center gap-1 px-2.5 py-1 bg-secondary text-secondary-foreground rounded text-xs hover:opacity-90"
                  >
                    <X className="w-3 h-3" /> Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-foreground truncate">{doc.title || doc.filename}</p>
                <p className="text-xs text-muted-foreground">
                  {doc.document_type !== 'general' ? doc.document_type.replace(/_/g, ' ') + ' | ' : ''}
                  {doc.mime_type}
                </p>
              </div>
            )}
            {editingDoc !== doc.id && (
              <div className="flex items-center gap-1 shrink-0">
                <button
                  onClick={() => window.open(doc.view_url, '_blank')}
                  className="p-1.5 text-muted-foreground hover:text-foreground rounded hover:bg-accent/30"
                  title="View"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                </button>
                {isAdmin && (
                  <>
                    <button
                      onClick={() => startEditDoc(doc)}
                      className="p-1.5 text-muted-foreground hover:text-foreground rounded hover:bg-accent/30"
                      title="Edit"
                    >
                      <Edit className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => handleDelete(doc.id)}
                      className="p-1.5 text-muted-foreground hover:text-destructive rounded hover:bg-destructive/10"
                      title="Delete"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
        ))}
        {documents.length === 0 && (
          <div className="px-4 py-8 text-center text-muted-foreground text-sm">No documents uploaded</div>
        )}
      </div>
    </div>
  )
}
