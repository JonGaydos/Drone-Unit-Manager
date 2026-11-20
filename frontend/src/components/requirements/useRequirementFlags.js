import { useEffect, useState } from 'react'
import { getSection } from '@/api/client'

/** Per pilot id, the open requirement misses; {} when not allowed or on failure.
 *  A new `version` reads them again. */
export function useRequirementFlags(allowed, version = 0) {
  const [flags, setFlags] = useState({})
  useEffect(() => {
    let alive = true
    getSection(allowed, '/requirements/flags', {}).then(found => { if (alive) setFlags(found || {}) })
    return () => { alive = false }
  }, [allowed, version])
  return flags
}
