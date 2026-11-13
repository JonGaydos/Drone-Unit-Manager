import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import TopicView from './TopicView'

export default function OnePageLayout({ sections }) {
  const [collapsed, setCollapsed] = useState(() => new Set())

  const toggle = id =>
    setCollapsed(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  if (sections.length === 0) {
    return <p className="text-sm text-muted-foreground">No topics match your search.</p>
  }

  return (
    <div className="space-y-6">
      {sections.map(section => {
        const open = !collapsed.has(section.id)
        return (
          <div key={section.id} className="bg-card border border-border rounded-xl overflow-hidden">
            <button
              type="button"
              onClick={() => toggle(section.id)}
              aria-expanded={open}
              className="w-full flex items-center justify-between p-5 text-left hover:bg-accent transition-colors"
            >
              <h2 className="text-lg font-semibold text-foreground">{section.title}</h2>
              {open ? (
                <ChevronDown className="w-5 h-5 text-muted-foreground shrink-0" />
              ) : (
                <ChevronRight className="w-5 h-5 text-muted-foreground shrink-0" />
              )}
            </button>
            {open && (
              <div className="px-5 pb-5 space-y-8">
                {section.topics.map(topic => (
                  <TopicView key={topic.id} section={section} topic={topic} />
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
