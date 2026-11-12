import { useEffect, useRef, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import TopicView from './TopicView'
import { flattenTopics, neighbors, topicKey } from './topics'

function TopicList({ sections, currentKey, openIds, onToggle, onPick }) {
  return sections.map(section => {
    const open = openIds.has(section.id)
    return (
      <div key={section.id} className="mb-1">
        <button
          type="button"
          onClick={() => onToggle(section.id)}
          aria-expanded={open}
          className="flex w-full items-center gap-1 rounded-md px-2 py-1.5 text-left text-sm font-medium text-foreground hover:bg-accent"
        >
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          {section.title}
        </button>
        {open && (
          <div className="ml-4 border-l border-border pl-2">
            {section.topics.map(topic => {
              const key = topicKey(section.id, topic.id)
              const current = key === currentKey
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => onPick(key)}
                  aria-current={current ? 'page' : undefined}
                  className={`block w-full rounded-md px-2 py-1 text-left text-sm hover:bg-accent ${
                    current ? 'bg-accent font-medium text-primary' : 'text-muted-foreground'
                  }`}
                >
                  {topic.title}
                </button>
              )
            })}
          </div>
        )}
      </div>
    )
  })
}

export default function TopicsLayout({ sections, currentKey, onSelect }) {
  const [pickerOpen, setPickerOpen] = useState(false)
  const [openIds, setOpenIds] = useState(() => new Set())
  const pickerRef = useRef(null)

  const all = flattenTopics(sections)
  const current = all.find(entry => entry.key === currentKey) || all[0] || null
  const activeKey = current?.key ?? null
  const activeSectionId = current?.section.id
  const { prev, next } = activeKey ? neighbors(sections, activeKey) : { prev: null, next: null }

  // Keep the current topic's section open when the current topic moves.
  const [seenSectionId, setSeenSectionId] = useState(null)
  if (activeSectionId !== seenSectionId) {
    setSeenSectionId(activeSectionId)
    if (activeSectionId && !openIds.has(activeSectionId)) {
      setOpenIds(new Set(openIds).add(activeSectionId))
    }
  }

  useEffect(() => {
    if (!pickerOpen) return undefined
    const onKey = e => { if (e.key === 'Escape') setPickerOpen(false) }
    const onDown = e => {
      if (pickerRef.current && !pickerRef.current.contains(e.target)) setPickerOpen(false)
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onDown)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onDown)
    }
  }, [pickerOpen])

  if (!current) {
    return <p className="text-sm text-muted-foreground">No topics match your search.</p>
  }

  const toggle = id =>
    setOpenIds(ids => {
      const nextIds = new Set(ids)
      if (nextIds.has(id)) nextIds.delete(id)
      else nextIds.add(id)
      return nextIds
    })

  const pick = key => {
    setPickerOpen(false)
    onSelect(key)
  }

  return (
    <div className="md:flex md:gap-6">
      <nav
        aria-label="Manual topics"
        className="hidden md:block md:w-60 md:shrink-0 md:sticky md:top-4 md:self-start md:max-h-[calc(100vh-2rem)] md:overflow-y-auto"
      >
        <TopicList sections={sections} currentKey={activeKey} openIds={openIds} onToggle={toggle} onPick={onSelect} />
      </nav>

      <div ref={pickerRef} className="relative mb-4 md:hidden">
        <button
          type="button"
          onClick={() => setPickerOpen(o => !o)}
          aria-expanded={pickerOpen}
          className="flex w-full items-center justify-between rounded-lg border border-border bg-card px-3 py-2 text-left text-sm text-foreground"
        >
          <span>{current.section.title} › {current.topic.title}</span>
          <ChevronDown size={16} />
        </button>
        {pickerOpen && (
          <div
            role="region"
            aria-label="Choose a topic"
            className="absolute left-0 right-0 z-10 mt-1 max-h-80 overflow-y-auto rounded-lg border border-border bg-card p-2 shadow-lg"
          >
            <TopicList sections={sections} currentKey={activeKey} openIds={openIds} onToggle={toggle} onPick={pick} />
          </div>
        )}
      </div>

      <div className="min-w-0 flex-1">
        <div className="rounded-lg border border-border bg-card p-4 md:p-6">
          <TopicView section={current.section} topic={current.topic} />
        </div>
        <div className="mt-4 flex items-center justify-between gap-2">
          {prev ? (
            <button
              type="button"
              onClick={() => onSelect(prev.key)}
              className="rounded-md border border-border px-3 py-1.5 text-sm text-foreground hover:bg-accent"
            >
              ← {prev.topic.title}
            </button>
          ) : <span />}
          {next ? (
            <button
              type="button"
              onClick={() => onSelect(next.key)}
              className="rounded-md border border-border px-3 py-1.5 text-sm text-foreground hover:bg-accent"
            >
              {next.topic.title} →
            </button>
          ) : <span />}
        </div>
      </div>
    </div>
  )
}
