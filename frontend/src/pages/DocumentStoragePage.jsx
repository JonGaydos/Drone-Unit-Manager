import { useState, useEffect, useCallback } from 'react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import {
  FolderOpen, FolderPlus, FileText, ChevronRight, ChevronDown,
  Upload, Trash2, Edit2, X, File, Search, Home, MoreVertical,
  FileImage, FileSpreadsheet
} from 'lucide-react'

export default function DocumentStoragePage() {
  const [folders, setFolders] = useState([])
  const [selectedFolder, setSelectedFolder] = useState(null)
  const [documents, setDocuments] = useState([])
  const [allDocuments, setAllDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [docsLoading, setDocsLoading] = useState(false)
  const [showCreateFolder, setShowCreateFolder] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const [newFolderParent, setNewFolderParent] = useState(null)
  const [editingFolder, setEditingFolder] = useState(null)
  const [editName, setEditName] = useState('')
  const [expandedFolders, setExpandedFolders] = useState(new Set())
  const [search, setSearch] = useState('')
  const { isAdmin } = useAuth()

  const loadFolders = useCallback(async () => {
    try {
      const f = await api.get('/folders')
      setFolders(f)
      // Expand all folders by default
      setExpandedFolders(new Set(f.map(folder => folder.id)))
    } catch (err) {
      console.error(err)
    }
  }, [])

  const loadDocuments = useCallback(async (folderId) => {
    setDocsLoading(true)
    try {
      if (folderId) {
        const docs = await api.get(`/folders/${folderId}/documents`)
        setDocuments(docs)
      } else {
        setDocuments([])
      }
    } catch (err) {
      console.error(err)
    } finally {
      setDocsLoading(false)
    }
  }, [])

  const loadAllDocuments = useCallback(async () => {
    try {
      const docs = await api.get('/documents')
      setAllDocuments(Array.isArray(docs) ? docs : [])
    } catch {
      setAllDocuments([])
    }
  }, [])

  useEffect(() => {
    Promise.all([loadFolders(), loadAllDocuments()]).finally(() => setLoading(false))
  }, [loadFolders, loadAllDocuments])

  useEffect(() => {
    if (selectedFolder === 'unfiled') {
      // Show documents without a folder
      setDocsLoading(true)
      api.get('/documents').then(docs => {
        const unfiled = (Array.isArray(docs) ? docs : []).filter(d => !d.folder_id)
        setDocuments(unfiled)
      }).catch(console.error).finally(() => setDocsLoading(false))
    } else if (selectedFolder) {
      loadDocuments(selectedFolder)
    } else {
      setDocuments([])
    }
  }, [selectedFolder, loadDocuments])

  // Build folder tree
  const buildTree = (parentId = null) => {
    return folders
      .filter(f => f.parent_id === parentId)
      .sort((a, b) => a.name.localeCompare(b.name))
  }

  const toggleExpand = (id) => {
    setExpandedFolders(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const getBreadcrumbs = () => {
    if (!selectedFolder) return []
    const crumbs = []
    let current = folders.find(f => f.id === selectedFolder)
    while (current) {
      crumbs.unshift(current)
      current = current.parent_id ? folders.find(f => f.id === current.parent_id) : null
    }
    return crumbs
  }

  const handleCreateFolder = async () => {
    if (!newFolderName.trim()) return
    try {
      await api.post('/folders', { name: newFolderName.trim(), parent_id: newFolderParent })
      setNewFolderName('')
      setShowCreateFolder(false)
      setNewFolderParent(null)
      loadFolders()
    } catch (err) {
      console.error(err)
    }
  }

  const handleRenameFolder = async () => {
    if (!editName.trim() || !editingFolder) return
    try {
      await api.patch(`/folders/${editingFolder}`, { name: editName.trim() })
      setEditingFolder(null)
      setEditName('')
      loadFolders()
    } catch (err) {
      console.error(err)
    }
  }

  const handleDeleteFolder = async (id) => {
    if (!confirm('Delete this folder? Documents will be moved to "Unfiled".')) return
    try {
      await api.delete(`/folders/${id}`)
      if (selectedFolder === id) setSelectedFolder(null)
      loadFolders()
    } catch (err) {
      console.error(err)
    }
  }

  const handleMoveDocument = async (docId, folderId) => {
    try {
      await api.patch(`/documents/${docId}`, { folder_id: folderId })
      loadDocuments(selectedFolder)
      loadFolders()
      loadAllDocuments()
    } catch (err) {
      console.error(err)
    }
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

  const getFileIcon = (mime) => {
    if (!mime) return <File className="w-5 h-5 text-muted-foreground" />
    if (mime.includes('pdf')) return <FileText className="w-5 h-5 text-red-400" />
    if (mime.includes('image')) return <FileImage className="w-5 h-5 text-blue-400" />
    if (mime.includes('spreadsheet') || mime.includes('excel')) return <FileSpreadsheet className="w-5 h-5 text-green-400" />
    return <FileText className="w-5 h-5 text-muted-foreground" />
  }

  // Documents displayed - either from selected folder or unfiled search results
  const displayDocs = selectedFolder ? documents : []
  const filteredDocs = search
    ? displayDocs.filter(d => (d.title || d.filename || '').toLowerCase().includes(search.toLowerCase()))
    : displayDocs

  // Count unfiled documents
  const unfiledCount = allDocuments.filter(d => !d.folder_id).length

  if (loading) {
    return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
  }

  const renderFolderNode = (folder, depth = 0) => {
    const children = buildTree(folder.id)
    const hasChildren = children.length > 0
    const isExpanded = expandedFolders.has(folder.id)
    const isSelected = selectedFolder === folder.id

    return (
      <div key={folder.id}>
        <div
          className={`flex items-center gap-1.5 px-2 py-1.5 rounded-lg cursor-pointer group transition-colors ${
            isSelected ? 'bg-primary/15 text-primary' : 'text-foreground hover:bg-muted/50'
          }`}
          style={{ paddingLeft: `${depth * 16 + 8}px` }}
          onClick={() => {
            setSelectedFolder(folder.id)
            if (hasChildren) toggleExpand(folder.id)
          }}
        >
          {hasChildren ? (
            <button
              onClick={(e) => { e.stopPropagation(); toggleExpand(folder.id) }}
              className="p-0.5 shrink-0"
            >
              {isExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
            </button>
          ) : (
            <span className="w-4.5 shrink-0" />
          )}
          <FolderOpen className={`w-4 h-4 shrink-0 ${isSelected ? 'text-primary' : 'text-yellow-500'}`} />
          <span className="text-sm truncate flex-1">{folder.name}</span>
          <span className="text-xs text-muted-foreground shrink-0">{folder.document_count}</span>
          {isAdmin && !folder.is_system && (
            <div className="hidden group-hover:flex items-center gap-0.5 shrink-0">
              <button
                onClick={(e) => { e.stopPropagation(); setEditingFolder(folder.id); setEditName(folder.name) }}
                className="p-0.5 text-muted-foreground hover:text-primary"
              >
                <Edit2 className="w-3 h-3" />
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); handleDeleteFolder(folder.id) }}
                className="p-0.5 text-muted-foreground hover:text-destructive"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          )}
        </div>
        {isExpanded && children.map(child => renderFolderNode(child, depth + 1))}
      </div>
    )
  }

  const selectedFolderObj = folders.find(f => f.id === selectedFolder)

  return (
    <div className="flex gap-4 h-[calc(100vh-8rem)]">
      {/* Sidebar - Folder Tree */}
      <div className="w-64 shrink-0 bg-card border border-border rounded-xl flex flex-col overflow-hidden">
        <div className="flex items-center justify-between p-3 border-b border-border">
          <h2 className="text-sm font-semibold text-foreground">Folders</h2>
          {isAdmin && (
            <button
              onClick={() => { setShowCreateFolder(true); setNewFolderParent(selectedFolder) }}
              className="p-1 text-muted-foreground hover:text-primary transition-colors"
              title="New Folder"
            >
              <FolderPlus className="w-4 h-4" />
            </button>
          )}
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
          {buildTree(null).map(f => renderFolderNode(f))}

          {/* Unfiled section */}
          <div
            className={`flex items-center gap-1.5 px-2 py-1.5 rounded-lg cursor-pointer mt-2 border-t border-border pt-3 transition-colors ${
              selectedFolder === 'unfiled' ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:bg-muted/50'
            }`}
            onClick={() => setSelectedFolder('unfiled')}
          >
            <span className="w-4.5 shrink-0" />
            <FileText className="w-4 h-4 shrink-0" />
            <span className="text-sm flex-1">Unfiled</span>
            <span className="text-xs">{unfiledCount}</span>
          </div>
        </div>

        {/* Create folder inline */}
        {showCreateFolder && (
          <div className="p-3 border-t border-border space-y-2">
            <input
              autoFocus
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleCreateFolder(); if (e.key === 'Escape') setShowCreateFolder(false) }}
              placeholder="Folder name"
              className="w-full px-2 py-1.5 bg-secondary border border-border rounded-lg text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <div className="flex gap-1">
              <button
                onClick={handleCreateFolder}
                className="flex-1 px-2 py-1 bg-primary text-primary-foreground rounded text-xs font-medium"
              >
                Create
              </button>
              <button
                onClick={() => setShowCreateFolder(false)}
                className="flex-1 px-2 py-1 bg-muted text-muted-foreground rounded text-xs"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Rename folder inline */}
        {editingFolder && (
          <div className="p-3 border-t border-border space-y-2">
            <p className="text-xs text-muted-foreground">Rename folder</p>
            <input
              autoFocus
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleRenameFolder(); if (e.key === 'Escape') setEditingFolder(null) }}
              className="w-full px-2 py-1.5 bg-secondary border border-border rounded-lg text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <div className="flex gap-1">
              <button onClick={handleRenameFolder} className="flex-1 px-2 py-1 bg-primary text-primary-foreground rounded text-xs font-medium">
                Save
              </button>
              <button onClick={() => setEditingFolder(null)} className="flex-1 px-2 py-1 bg-muted text-muted-foreground rounded text-xs">
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Main Content */}
      <div className="flex-1 bg-card border border-border rounded-xl flex flex-col overflow-hidden">
        {/* Breadcrumb + Search */}
        <div className="flex items-center justify-between p-3 border-b border-border gap-4">
          <div className="flex items-center gap-1.5 text-sm min-w-0">
            <button
              onClick={() => setSelectedFolder(null)}
              className="text-muted-foreground hover:text-foreground transition-colors shrink-0"
            >
              <Home className="w-4 h-4" />
            </button>
            {getBreadcrumbs().map((crumb, i) => (
              <div key={crumb.id} className="flex items-center gap-1.5 min-w-0">
                <ChevronRight className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                <button
                  onClick={() => setSelectedFolder(crumb.id)}
                  className={`truncate ${
                    i === getBreadcrumbs().length - 1 ? 'text-foreground font-medium' : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {crumb.name}
                </button>
              </div>
            ))}
            {selectedFolder === 'unfiled' && (
              <>
                <ChevronRight className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                <span className="text-foreground font-medium">Unfiled</span>
              </>
            )}
          </div>
          {selectedFolder && (
            <div className="relative shrink-0">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
              <input
                type="text"
                placeholder="Search..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-8 pr-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-xs focus:outline-none focus:ring-2 focus:ring-ring w-48"
              />
            </div>
          )}
        </div>

        {/* Document list */}
        <div className="flex-1 overflow-y-auto">
          {!selectedFolder ? (
            <div className="flex flex-col items-center justify-center h-full text-center p-8">
              <FolderOpen className="w-16 h-16 text-muted-foreground/30 mb-4" />
              <h3 className="text-lg font-semibold text-foreground mb-2">Document Storage</h3>
              <p className="text-sm text-muted-foreground max-w-md">
                Select a folder from the sidebar to view its documents. Use folders to organize
                certifications, insurance documents, maintenance records, and more.
              </p>
            </div>
          ) : docsLoading ? (
            <div className="flex items-center justify-center h-32">
              <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            </div>
          ) : filteredDocs.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center p-8">
              <FileText className="w-12 h-12 text-muted-foreground/30 mb-3" />
              <p className="text-sm text-muted-foreground">
                {search ? 'No matching documents found.' : 'No documents in this folder yet.'}
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                Upload documents from the Documents page and assign them to folders.
              </p>
            </div>
          ) : (
            <table className="w-full">
              <thead className="sticky top-0 bg-card border-b border-border">
                <tr className="text-xs text-muted-foreground">
                  <th className="text-left px-4 py-2.5 font-medium">Name</th>
                  <th className="text-left px-4 py-2.5 font-medium w-28">Type</th>
                  <th className="text-right px-4 py-2.5 font-medium w-24">Size</th>
                  <th className="text-left px-4 py-2.5 font-medium w-32">Date</th>
                  <th className="text-right px-4 py-2.5 font-medium w-20">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredDocs.map(doc => (
                  <tr key={doc.id} className="border-b border-border/50 hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        {getFileIcon(doc.mime_type)}
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-foreground truncate">{doc.title || doc.filename}</p>
                          {doc.title && doc.filename && doc.title !== doc.filename && (
                            <p className="text-xs text-muted-foreground truncate">{doc.filename}</p>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-muted text-muted-foreground">
                        {doc.document_type || doc.entity_type || '—'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right text-sm text-muted-foreground">
                      {formatSize(doc.file_size_bytes)}
                    </td>
                    <td className="px-4 py-3 text-sm text-muted-foreground">
                      {formatDate(doc.uploaded_at)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <a
                        href={`${import.meta.env.VITE_API_URL || '/api'}/documents/${doc.id}/view`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-primary hover:opacity-80"
                      >
                        View
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Footer */}
        {selectedFolder && selectedFolderObj && (
          <div className="flex items-center justify-between px-4 py-2 border-t border-border text-xs text-muted-foreground">
            <span>{filteredDocs.length} document{filteredDocs.length !== 1 ? 's' : ''}</span>
            {selectedFolderObj.description && <span>{selectedFolderObj.description}</span>}
          </div>
        )}
      </div>
    </div>
  )
}
