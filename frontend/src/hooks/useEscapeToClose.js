import { useEffect } from 'react'

/**
 * Close a hand-built popup on Escape, the way the shared Modal does. Mount it
 * in the popup component itself, so it only listens while the popup is open.
 * @param {() => void} onClose
 */
export function useEscapeToClose(onClose) {
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])
}
