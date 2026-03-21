import { useState, useEffect } from 'react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { Search, Image, Video, Download, FileQuestion, Filter } from 'lucide-react'

export default function MediaPage() {
  const [media, setMedia] = useState([])
  const [count, setCount] = useState(0)
  const [search, setSearch] = useState('')
  const [kindFilter, setKindFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const { isAdmin } = useAuth()

  const load = () => {
    setLoading(true)
    const params = kindFilter ? `?kind=${kindFilter}` : ''
    Promise.all([
      api.get(`/media${params}`),
      api.get('/media/count'),
    ]).then(([m, c]) => {
      setMedia(m)
      setCount(typeof c === 'object' ? c.count : c)
    }).catch(console.error).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [kindFilter])

  const filtered = media.filter(m =>
    `${m.filename || ''} ${m.kind || ''}`
      .toLowerCase().includes(search.toLowerCase())
  )

  const formatFileSize = (bytes) => {
    if (!bytes) return '—'
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
  }

  const KindIcon = ({ kind }) => {
    if (kind === 'photo') return <Image className="w-8 h-8 text-blue-400" />
    if (kind === 'video') return <Video className="w-8 h-8 text-purple-400" />
    return <FileQuestion className="w-8 h-8 text-muted-foreground" />
  }

  if (loading) {
    return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search media..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground">{count} total files</span>
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-muted-foreground" />
            <select
              value={kindFilter}
              onChange={(e) => setKindFilter(e.target.value)}
              className="px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm"
            >
              <option value="">All Types</option>
              <option value="photo">Photos</option>
              <option value="video">Videos</option>
            </select>
          </div>
        </div>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {filtered.map(m => (
          <div key={m.id} className="bg-card border border-border rounded-xl overflow-hidden hover:border-primary/50 transition-colors">
            {/* Thumbnail area */}
            <div className="aspect-video bg-muted/30 flex items-center justify-center">
              {m.thumbnail_url ? (
                <img src={m.thumbnail_url} alt={m.filename} className="w-full h-full object-cover" />
              ) : (
                <KindIcon kind={m.kind} />
              )}
            </div>
            {/* Info */}
            <div className="p-3 space-y-2">
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm text-foreground font-medium truncate flex-1" title={m.filename}>
                  {m.filename || 'Untitled'}
                </p>
                <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium shrink-0 ${
                  m.kind === 'photo' ? 'bg-blue-500/15 text-blue-400' :
                  m.kind === 'video' ? 'bg-purple-500/15 text-purple-400' :
                  'bg-zinc-500/15 text-zinc-400'
                }`}>
                  {m.kind || 'unknown'}
                </span>
              </div>
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>{m.captured_time || '—'}</span>
                <span>{formatFileSize(m.file_size)}</span>
              </div>
              {m.download_url && (
                <a
                  href={m.download_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 text-xs text-primary hover:opacity-80 mt-1"
                >
                  <Download className="w-3.5 h-3.5" /> Download
                </a>
              )}
            </div>
          </div>
        ))}
        {filtered.length === 0 && (
          <div className="col-span-full text-center py-12 text-muted-foreground">No media files found</div>
        )}
      </div>
    </div>
  )
}
