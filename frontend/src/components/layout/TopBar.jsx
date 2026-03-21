import { useTheme, THEMES } from '@/contexts/ThemeContext'
import { Palette } from 'lucide-react'
import { useState, useRef, useEffect } from 'react'

export function TopBar({ title }) {
  const { theme, setTheme } = useTheme()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <header className="h-16 border-b border-border bg-card/50 backdrop-blur-sm flex items-center justify-between px-6 sticky top-0 z-30">
      <h1 className="text-lg font-semibold text-foreground">{title}</h1>

      <div className="relative" ref={ref}>
        <button
          onClick={() => setOpen(!open)}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
        >
          <Palette className="w-4 h-4" />
          <span className="hidden sm:inline">{THEMES.find(t => t.id === theme)?.name}</span>
        </button>

        {open && (
          <div className="absolute right-0 top-full mt-1 w-40 bg-popover border border-border rounded-lg shadow-lg py-1 z-50">
            {THEMES.map((t) => (
              <button
                key={t.id}
                onClick={() => { setTheme(t.id); setOpen(false) }}
                className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                  theme === t.id
                    ? 'text-primary bg-primary/10'
                    : 'text-popover-foreground hover:bg-accent'
                }`}
              >
                {t.name}
              </button>
            ))}
          </div>
        )}
      </div>
    </header>
  )
}
