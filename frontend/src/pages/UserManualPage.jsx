import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { BookOpen, Search } from 'lucide-react'
import { sections } from './manual/content'
import { filterSections, findTopic, flattenTopics } from './manual/topics'
import TopicsLayout from './manual/TopicsLayout'
import OnePageLayout from './manual/OnePageLayout'

const VIEW_KEY = 'dum.manual.view'

function readStoredView() {
  try {
    return localStorage.getItem(VIEW_KEY) === 'page' ? 'page' : 'topics'
  } catch {
    return 'topics'
  }
}

function storeView(view) {
  try {
    localStorage.setItem(VIEW_KEY, view)
  } catch {
    // Storage can be blocked; the choice then lasts only for this visit.
  }
}

export default function UserManualPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const topicParam = searchParams.get('topic')
  const topicParamValid = !!topicParam && !!findTopic(sections, topicParam)

  const [view, setView] = useState(() => (topicParamValid ? 'topics' : readStoredView()))
  const [search, setSearch] = useState('')

  // A link to a topic always opens the Topics view and makes it the stored choice.
  const [seenParam, setSeenParam] = useState(topicParam)
  if (topicParam !== seenParam) {
    setSeenParam(topicParam)
    if (topicParamValid) setView('topics')
  }
  useEffect(() => {
    if (topicParamValid && view === 'topics') storeView('topics')
  }, [topicParamValid, view])

  const filtered = filterSections(sections, search)
  const filteredTopics = flattenTopics(filtered)
  const currentKey = filteredTopics.some(e => e.key === topicParam)
    ? topicParam
    : filteredTopics[0]?.key ?? null

  // Bring the top of the topic area into view whenever the shown topic changes.
  const lastKey = useRef(currentKey)
  useEffect(() => {
    if (view !== 'topics' || lastKey.current === currentKey) {
      lastKey.current = currentKey
      return
    }
    lastKey.current = currentKey
    if (typeof window.scrollTo === 'function') window.scrollTo({ top: 0 })
  }, [currentKey, view])

  // When a search moves the shown topic, keep the address in step.
  const searching = search.trim() !== ''
  useEffect(() => {
    if (view === 'topics' && searching && currentKey && topicParam !== currentKey) {
      setSearchParams(prev => {
        const next = new URLSearchParams(prev)
        next.set('topic', currentKey)
        return next
      }, { replace: true })
    }
  }, [view, searching, currentKey, topicParam, setSearchParams])

  const chooseView = next => {
    setView(next)
    storeView(next)
    if (next === 'page' && topicParam) {
      setSearchParams(prev => {
        const params = new URLSearchParams(prev)
        params.delete('topic')
        return params
      }, { replace: true })
    }
  }

  const selectTopic = key => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      next.set('topic', key)
      return next
    })
  }

  const viewButton = (value, label) => (
    <button
      type="button"
      onClick={() => chooseView(value)}
      aria-pressed={view === value}
      className={`px-3 py-1.5 text-sm font-medium transition-colors ${
        view === value ? 'bg-accent text-primary' : 'text-muted-foreground hover:bg-accent'
      }`}
    >
      {label}
    </button>
  )

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary/15 flex items-center justify-center text-primary">
            <BookOpen className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">User Manual</h1>
            <p className="text-sm text-muted-foreground">How to use Drone Unit Manager</p>
          </div>
        </div>
        <div
          role="group"
          aria-label="Manual layout"
          className="inline-flex overflow-hidden rounded-lg border border-border bg-card"
        >
          {viewButton('topics', 'Topics')}
          {viewButton('page', 'One page')}
        </div>
      </div>

      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          type="text"
          placeholder="Search the manual..."
          aria-label="Search the manual"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="w-full pl-9 pr-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>

      {view === 'topics' ? (
        <TopicsLayout
          sections={filtered}
          currentKey={currentKey}
          onSelect={selectTopic}
          searching={searching}
        />
      ) : (
        <OnePageLayout sections={filtered} />
      )}
    </div>
  )
}
