/**
 * Global command palette (Ctrl/Cmd+K): jump to any page or search pilots,
 * vehicles, and flights from anywhere. Opens on the keyboard shortcut or via
 * the `open-command-palette` window event (fired by the top bar search button).
 */
import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '@/api/client'
import { Search, CornerDownLeft } from 'lucide-react'

/** Static navigation targets (mirror the sidebar). */
const NAV = [
  { label: 'Dashboard', url: '/' },
  { label: 'Analytics', url: '/analytics' },
  { label: 'Flights', url: '/flights' },
  { label: 'Flight Plans', url: '/flight-plans' },
  { label: 'Checklists', url: '/checklists' },
  { label: 'Mission Log', url: '/missions' },
  { label: 'Training Log', url: '/training' },
  { label: 'Pilots', url: '/pilots' },
  { label: 'Fleet', url: '/fleet' },
  { label: 'Fleet Health', url: '/fleet-health' },
  { label: 'Certifications', url: '/certifications' },
  { label: 'Maintenance', url: '/maintenance' },
  { label: 'Photo Gallery', url: '/media' },
  { label: 'Documents', url: '/documents' },
  { label: 'Reports', url: '/reports' },
  { label: 'Compliance', url: '/compliance' },
  { label: 'Operating Authority', url: '/operating-authority' },
  { label: 'Alerts', url: '/alerts' },
  { label: 'Activity Reports', url: '/incidents' },
  { label: 'Weather', url: '/weather' },
  { label: 'Airspace', url: '/airspace' },
  { label: 'Settings', url: '/settings' },
  { label: 'User Manual', url: '/manual' },
]

const TYPE_STYLES = {
  pilot: 'bg-blue-500/15 text-blue-400',
  vehicle: 'bg-amber-500/15 text-amber-400',
  flight: 'bg-emerald-500/15 text-emerald-400',
  page: 'bg-indigo-500/15 text-indigo-400',
  recent: 'bg-muted text-muted-foreground',
}

/** Entity-type filter chips shown above search results. */
const TYPE_FILTERS = [
  { label: 'All', value: null },
  { label: 'Pilots', value: 'pilot' },
  { label: 'Vehicles', value: 'vehicle' },
  { label: 'Flights', value: 'flight' },
]

const RECENTS_KEY = 'dum_command_recents'

/** Read persisted recent jumps from localStorage (used as lazy initial state). */
function loadRecents() {
  try {
    const stored = JSON.parse(localStorage.getItem(RECENTS_KEY) || '[]')
    return Array.isArray(stored) ? stored : []
  } catch {
    return []
  }
}

export function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [typeFilter, setTypeFilter] = useState(null)
  const [active, setActive] = useState(0)
  const [recents, setRecents] = useState(loadRecents)
  const inputRef = useRef(null)
  const navigate = useNavigate()

  const close = useCallback(() => { setOpen(false); setQuery(''); setResults([]); setTypeFilter(null); setActive(0) }, [])

  // Open via Ctrl/Cmd+K, or the top-bar button event. Close on Escape.
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen(o => !o)
      } else if (e.key === 'Escape') {
        setOpen(false)
      }
    }
    const onOpen = () => setOpen(true)
    globalThis.addEventListener('keydown', onKey)
    globalThis.addEventListener('open-command-palette', onOpen)
    return () => {
      globalThis.removeEventListener('keydown', onKey)
      globalThis.removeEventListener('open-command-palette', onOpen)
    }
  }, [])

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 20)
    else { setQuery(''); setResults([]); setTypeFilter(null); setActive(0) }
  }, [open])

  // Debounced entity search.
  useEffect(() => {
    const q = query.trim()
    if (q.length < 2) { setResults([]); setTypeFilter(null); return }
    const t = setTimeout(() => {
      api.get(`/search?q=${encodeURIComponent(q)}`)
        .then(d => setResults(d.results || []))
        .catch(() => setResults([]))
    }, 180)
    return () => clearTimeout(t)
  }, [query])

  const pages = useMemo(() => {
    const q = query.trim().toLowerCase()
    const list = q ? NAV.filter(n => n.label.toLowerCase().includes(q)) : NAV
    return list.map(n => ({ ...n, type: 'page', title: n.label }))
  }, [query])

  // Recent jumps shown when the query is empty, rendered like other rows.
  const recentItems = useMemo(
    () => recents.map(r => ({ ...r, type: 'recent', title: r.label })),
    [recents],
  )

  // Active entity-type filter applied to search results (pages stay unfiltered).
  const filteredResults = useMemo(
    () => (typeFilter ? results.filter(r => r.type === typeFilter) : results),
    [typeFilter, results],
  )

  // Flat, ordered list of selectable items for keyboard nav (must match render order).
  const items = useMemo(
    () => (query.trim() ? [...pages, ...filteredResults] : [...recentItems, ...pages]),
    [query, pages, filteredResults, recentItems],
  )

  const go = useCallback((item) => {
    if (!item) return
    const label = item.title || item.label
    setRecents(prev => {
      const next = [{ label, url: item.url }, ...prev.filter(r => r.url !== item.url)].slice(0, 5)
      try { localStorage.setItem(RECENTS_KEY, JSON.stringify(next)) } catch { /* ignore */ }
      return next
    })
    navigate(item.url)
    close()
  }, [navigate, close])

  const onKeyDown = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive(a => Math.min(a + 1, items.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(a => Math.max(a - 1, 0)) }
    else if (e.key === 'Enter') { e.preventDefault(); go(items[active]) }
  }

  if (!open) return null

  const renderItem = (item, i) => {
    const isActive = i === active
    return (
      <button
        key={`${item.type}-${item.url}-${i}`}
        type="button"
        onClick={() => go(item)}
        onMouseEnter={() => setActive(i)}
        className={`flex items-center gap-3 w-full text-left px-3 py-2 rounded-lg text-sm ${isActive ? 'bg-accent' : ''}`}
      >
        <span className={`text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded font-medium shrink-0 ${TYPE_STYLES[item.type] || TYPE_STYLES.page}`}>
          {item.type}
        </span>
        <span className="flex-1 min-w-0">
          <span className="block truncate text-foreground">{item.title}</span>
          {item.subtitle && <span className="block truncate text-xs text-muted-foreground">{item.subtitle}</span>}
        </span>
        {isActive && <CornerDownLeft className="w-3.5 h-3.5 text-muted-foreground shrink-0" />}
      </button>
    )
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center pt-[12vh] px-4">
      <button className="absolute inset-0 bg-black/50 backdrop-blur-sm cursor-default" onClick={close} aria-label="Close search" />
      <div className="relative w-full max-w-xl bg-popover border border-border rounded-xl shadow-2xl overflow-hidden">
        <div className="flex items-center gap-3 px-4 border-b border-border">
          <Search className="w-4 h-4 text-muted-foreground shrink-0" />
          <input
            ref={inputRef}
            value={query}
            onChange={e => { setQuery(e.target.value); setActive(0) }}
            onKeyDown={onKeyDown}
            placeholder="Search pilots, vehicles, flights, or jump to a page…"
            className="flex-1 bg-transparent py-3.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
          />
          <kbd className="text-[10px] text-muted-foreground border border-border rounded px-1.5 py-0.5">ESC</kbd>
        </div>

        <div className="max-h-[60vh] overflow-y-auto p-2">
          {!query.trim() && recentItems.length > 0 && (
            <>
              <div className="px-2 py-1 text-[10px] uppercase tracking-wider text-muted-foreground font-medium">Recent</div>
              {recentItems.map((item, i) => renderItem(item, i))}
            </>
          )}
          {pages.length > 0 && (
            <>
              <div className="px-2 py-1 mt-1 text-[10px] uppercase tracking-wider text-muted-foreground font-medium">Go to</div>
              {pages.map((item, i) => renderItem(item, (query.trim() ? 0 : recentItems.length) + i))}
            </>
          )}
          {query.trim() && results.length > 0 && (
            <div className="flex flex-wrap gap-1.5 px-2 py-1.5 mt-1">
              {TYPE_FILTERS.map(f => {
                const isActive = typeFilter === f.value
                return (
                  <button
                    key={f.label}
                    type="button"
                    onClick={() => { setTypeFilter(f.value); setActive(0) }}
                    className={`text-[11px] px-2 py-0.5 rounded-full border transition-colors ${isActive ? 'bg-accent border-border text-foreground' : 'border-border text-muted-foreground hover:text-foreground'}`}
                  >
                    {f.label}
                  </button>
                )
              })}
            </div>
          )}
          {query.trim() && results.length > 0 && (
            <>
              <div className="px-2 py-1 mt-1 text-[10px] uppercase tracking-wider text-muted-foreground font-medium">
                {typeFilter ? `Results — ${typeFilter}` : 'Results'}
              </div>
              {filteredResults.length === 0 ? (
                <div className="px-3 py-2 text-sm text-muted-foreground">No matches for this type.</div>
              ) : (
                filteredResults.map((item, i) => renderItem(item, pages.length + i))
              )}
            </>
          )}
          {items.length === 0 && (
            <div className="px-3 py-8 text-center text-sm text-muted-foreground">
              {query.trim().length < 2 ? 'Type to search across the app.' : 'No matches.'}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
