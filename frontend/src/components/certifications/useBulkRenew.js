import { useState } from 'react'
import { api } from '@/api/client'
import { useToast } from '@/contexts/ToastContext'
import { todayLocal } from '@/lib/utils'

/**
 * Bulk renewal (e.g. a training day): multi-select certs in the matrix and
 * renew them all with one issue date.
 */
export function useBulkRenew(onRenewed) {
  const toast = useToast()
  const [selected, setSelected] = useState(() => new Set())
  const [open, setOpen] = useState(false)
  const [issueDate, setIssueDate] = useState('')
  const [notes, setNotes] = useState('')
  const [renewing, setRenewing] = useState(false)

  const toggle = (certId) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(certId)) next.delete(certId)
      else next.add(certId)
      return next
    })
  }

  const start = () => { setIssueDate(todayLocal()); setOpen(true) }

  const submit = async () => {
    if (!issueDate) { toast.error('Issue date is required'); return }
    setRenewing(true)
    try {
      const res = await api.post('/pilot-certifications/bulk-renew', {
        pilot_certification_ids: [...selected],
        issue_date: issueDate,
        notes: notes || null,
      })
      toast.success(`Renewed ${res.renewed} certification(s)`)
      setOpen(false); setSelected(new Set()); setIssueDate(''); setNotes(''); onRenewed()
    } catch (err) {
      toast.error(err.message)
    } finally {
      setRenewing(false)
    }
  }

  return {
    selected, toggle, clear: () => setSelected(new Set()),
    open, start, close: () => setOpen(false),
    issueDate, setIssueDate, notes, setNotes, renewing, submit,
  }
}
