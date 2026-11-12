import { useState } from 'react'
import { BookOpen, ChevronRight, ChevronDown, Search } from 'lucide-react'
import { sections } from './manual/content'
import ManualText from './manual/ManualText'

export default function UserManualPage() {
  const [expandedSections, setExpandedSections] = useState(new Set(sections.map(s => s.id)))
  const [search, setSearch] = useState('')

  const toggleSection = (id) => {
    setExpandedSections(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const filteredSections = search
    ? sections.filter(s =>
        s.title.toLowerCase().includes(search.toLowerCase()) ||
        s.topics.some(c =>
          c.title.toLowerCase().includes(search.toLowerCase()) ||
          c.summary.toLowerCase().includes(search.toLowerCase())
        )
      )
    : sections

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center gap-3 mb-2">
        <div className="w-10 h-10 rounded-xl bg-primary/15 flex items-center justify-center text-primary">
          <BookOpen className="w-5 h-5" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-foreground">User Manual</h1>
          <p className="text-sm text-muted-foreground">Complete guide to using Drone Unit Manager</p>
        </div>
      </div>

      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          type="text"
          placeholder="Search manual..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-9 pr-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>

      {filteredSections.length === 0 && (
        <div className="text-center py-12 text-muted-foreground">
          No sections match your search.
        </div>
      )}

      {filteredSections.map(section => (
        <div key={section.id} className="bg-card border border-border rounded-xl overflow-hidden">
          <button
            onClick={() => toggleSection(section.id)}
            className="w-full flex items-center justify-between p-5 text-left hover:bg-muted/30 transition-colors"
          >
            <h2 className="text-lg font-semibold text-foreground">{section.title}</h2>
            {expandedSections.has(section.id) ? (
              <ChevronDown className="w-5 h-5 text-muted-foreground shrink-0" />
            ) : (
              <ChevronRight className="w-5 h-5 text-muted-foreground shrink-0" />
            )}
          </button>
          {expandedSections.has(section.id) && (
            <div className="px-5 pb-5 space-y-4">
              {section.topics.map((item) => (
                <div key={item.id}>
                  <h3 className="text-sm font-semibold text-foreground mb-1.5">{item.title}</h3>
                  <div className="text-sm text-muted-foreground leading-relaxed">
                    <ManualText text={item.summary} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
