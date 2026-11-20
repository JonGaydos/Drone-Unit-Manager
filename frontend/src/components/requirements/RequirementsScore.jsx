/**
 * The Requirements score, shown next to the compliance score on the
 * Compliance page: the share of saved requirement results met in the last 12
 * months. It is separate from the compliance score and never changes it.
 * Renders nothing without requirements.view.
 */
import { useEffect, useState } from 'react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'

function scoreTone(percent) {
  if (percent == null) return 'text-muted-foreground border-border bg-card'
  if (percent > 80) return 'text-success border-success/40 bg-success-bg'
  if (percent > 60) return 'text-warning border-warning/40 bg-warning-bg'
  return 'text-danger border-danger/40 bg-danger-bg'
}

export default function RequirementsScore() {
  // null while loading, false when it could not be read, else { percent }.
  const [result, setResult] = useState(null)
  const allowed = useAuth().can('requirements.view')

  useEffect(() => {
    if (!allowed) return undefined
    let alive = true
    api.get('/requirements/status')
      .then(status => {
        if (alive) setResult({ percent: status.score == null ? null : Math.round(status.score * 100) })
      })
      .catch(() => { if (alive) setResult(false) })
    return () => { alive = false }
  }, [allowed])

  if (!allowed || !result) return null
  const { percent } = result
  return (
    <figure aria-label="Requirements score" className="flex flex-col items-center gap-2">
      <div className={`w-28 h-28 rounded-full border-2 flex items-center justify-center text-center ${scoreTone(percent)}`}>
        {percent == null
          ? <span className="text-xs px-4 leading-snug">No results yet</span>
          : <span className="text-3xl font-bold tabular-nums">{percent}%</span>}
      </div>
      <figcaption className="text-sm font-medium text-muted-foreground">Requirements Score</figcaption>
    </figure>
  )
}
