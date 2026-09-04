/**
 * Smooth cross-fade between pages using the View Transitions API.
 *
 * Triggers on every pathname change. Falls back to no animation on browsers
 * without document.startViewTransition (Firefox as of mid-2025). The
 * transition itself is styled via index.css ::view-transition-* rules.
 */
import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

export function useViewTransition() {
  const location = useLocation()
  useEffect(() => {
    if (typeof document === 'undefined') return
    if (!document.startViewTransition) return
    // Kick off the transition. The Promise body intentionally resolves
    // immediately — the router has already swapped the DOM by the time this
    // effect runs, and we just want the browser's automatic before/after
    // snapshot cross-fade.
    document.startViewTransition(() => Promise.resolve())
  }, [location.pathname])
}
