import { useState, useEffect } from 'react'

/** True while the media query matches; updates when the viewport crosses it. */
export function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => globalThis.matchMedia(query).matches)

  useEffect(() => {
    const list = globalThis.matchMedia(query)
    const update = () => setMatches(list.matches)
    update()
    list.addEventListener('change', update)
    return () => list.removeEventListener('change', update)
  }, [query])

  return matches
}
