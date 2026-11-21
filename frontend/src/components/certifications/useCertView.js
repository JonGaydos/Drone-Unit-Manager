import { useState } from 'react'

const STORAGE_KEY = 'certifications.view'
export const CERT_VIEWS = ['matrix', 'pilot', 'urgency']

function storedView() {
  try {
    const view = localStorage.getItem(STORAGE_KEY)
    return CERT_VIEWS.includes(view) ? view : null
  } catch {
    return null
  }
}

// Phones (under the sm breakpoint) start on By pilot; the matrix needs width.
function defaultView() {
  try {
    return globalThis.matchMedia('(min-width: 640px)').matches ? 'matrix' : 'pilot'
  } catch {
    return 'matrix'
  }
}

/** The Certifications view, remembered on this device. */
export function useCertView() {
  const [view, setView] = useState(() => storedView() || defaultView())
  const choose = (next) => {
    setView(next)
    try { localStorage.setItem(STORAGE_KEY, next) } catch { /* storage unavailable: the choice lasts this visit */ }
  }
  return [view, choose]
}
