/**
 * Top navigation bar displaying the current page title and a theme selector dropdown.
 */
import { useTheme, THEMES } from '@/contexts/ThemeContext'
import { Palette, Search } from 'lucide-react'
import { useState, useRef, useEffect } from 'react'

/** Cross-platform shortcut hint (⌘K on Mac, Ctrl K elsewhere). */
const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)
const openPalette = () => globalThis.dispatchEvent(new CustomEvent('open-command-palette'))

/**
 * Sticky top bar with page title and theme picker dropdown.
 * Closes the dropdown when clicking outside via a mousedown listener.
 * @param {Object} props
 * @param {string} props.title - Page title to display.
 */
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
    <header className="h-16 border-b border-border bg-sidebar/80 backdrop-blur-sm flex items-center justify-between gap-4 px-6 sticky top-0 z-30">
      <h1 className="text-lg font-semibold text-foreground shrink-0">{title}</h1>

      <button
        onClick={openPalette}
        className="group flex items-center gap-2 flex-1 max-w-md px-3 py-1.5 rounded-lg bg-secondary/60 border border-border text-sm text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
        aria-label="Open search"
      >
        <Search className="w-4 h-4" />
        <span className="flex-1 text-left truncate">Search pilots, vehicles, flights…</span>
        <kbd className="hidden sm:inline text-[10px] border border-border rounded px-1.5 py-0.5 bg-background/50">{isMac ? '⌘K' : 'Ctrl K'}</kbd>
      </button>

      <div className="relative shrink-0" ref={ref}>
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
