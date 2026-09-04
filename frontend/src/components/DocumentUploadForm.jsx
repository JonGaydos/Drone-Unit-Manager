/**
 * Standalone document upload form. Used by DocumentUpload (entity detail
 * pages) and DocumentStoragePage (general documents uploaded into a folder).
 */
import { useState } from 'react'
import { api } from '@/api/client'
import { useToast } from '@/contexts/ToastContext'
import { DOC_TYPES } from '@/lib/constants'
import { Upload, Save, Loader2 } from 'lucide-react'

/**
 * @param {Object} props
 * @param {string} props.entityType - Parent entity type, or "general" for standalone documents.
 * @param {number|string|null} [props.entityId] - Parent entity ID (omit for "general").
 * @param {number|string|null} [props.folderId] - Optional folder to file the document into.
 * @param {Function} [props.onUploaded] - Called after a successful upload.
 * @param {Function} [props.onCancel] - Called when the user cancels; hides the cancel button if omitted.
 */
export default function DocumentUploadForm({ entityType, entityId, folderId, onUploaded, onCancel }) {
  const toast = useToast()
  const [uploading, setUploading] = useState(false)
  const [title, setTitle] = useState('')
  const [docType, setDocType] = useState('general')
  const [selectedFile, setSelectedFile] = useState(null)

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
      if (entityId !== null && entityId !== undefined) formData.append('entity_id', entityId)
      formData.append('document_type', docType)
      formData.append('title', title || selectedFile.name)
      if (folderId) formData.append('folder_id', folderId)
      await api.upload('/documents/upload', formData)
      setTitle('')
      setDocType('general')
      setSelectedFile(null)
      onUploaded?.()
    } catch (err) {
      toast.error(err.message)
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <div>
          <label htmlFor="doc-upload-title" className="block text-xs font-medium text-foreground mb-1">Title</label>
          <input id="doc-upload-title"
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Document title (optional)"
            className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
        <div>
          <label htmlFor="doc-upload-type" className="block text-xs font-medium text-foreground mb-1">Type</label>
          <select id="doc-upload-type"
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
      {(selectedFile || onCancel) && (
        <div className="flex gap-2">
          {selectedFile && (
            <button
              onClick={handleUpload}
              disabled={uploading}
              className="flex items-center gap-1.5 px-4 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-medium hover:opacity-90 disabled:opacity-50"
            >
              {uploading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
              {uploading ? 'Uploading...' : 'Save'}
            </button>
          )}
          {(selectedFile || onCancel) && (
            <button
              onClick={() => { setSelectedFile(null); setTitle(''); onCancel?.() }}
              className="px-4 py-1.5 bg-secondary text-secondary-foreground rounded-lg text-xs hover:opacity-90"
            >
              Cancel
            </button>
          )}
        </div>
      )}
    </div>
  )
}
