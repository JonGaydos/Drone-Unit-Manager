import { Loader2 } from 'lucide-react'
import { Modal } from '@/components/ui/Modal'

/** The action bar shown while certifications are selected in the matrix. */
export function BulkRenewBar({ bulk }) {
  if (bulk.selected.size === 0) return null
  return (
    <div className="flex items-center gap-3 bg-primary/10 border border-primary/30 rounded-lg px-4 py-2">
      <span className="text-sm font-medium text-foreground">{bulk.selected.size} selected</span>
      <button onClick={bulk.start} className="px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90">
        Renew selected
      </button>
      <button onClick={bulk.clear} className="text-sm text-muted-foreground hover:text-foreground">
        Clear
      </button>
    </div>
  )
}

export function BulkRenewModal({ bulk }) {
  const count = bulk.selected.size
  return (
    <Modal
      open
      onClose={bulk.close}
      title={`Renew ${count} Certification${count === 1 ? '' : 's'}`}
      className="max-w-md"
    >
        <p className="text-sm text-muted-foreground mb-4">
          Each selected certification is archived and replaced with a new record. Expiration is auto-calculated per certification type. Already-renewed certs are skipped.
        </p>
        <div className="space-y-3">
          <div>
            <label htmlFor="bulk-issue-date" className="block text-sm font-medium text-foreground mb-1">Issue date</label>
            <input id="bulk-issue-date" type="date" value={bulk.issueDate} onChange={e => bulk.setIssueDate(e.target.value)}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
          </div>
          <div>
            <label htmlFor="bulk-notes" className="block text-sm font-medium text-foreground mb-1">Notes (optional)</label>
            <input id="bulk-notes" type="text" value={bulk.notes} onChange={e => bulk.setNotes(e.target.value)}
              placeholder="e.g. Recurrent training day" className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
          </div>
        </div>
        <div className="flex gap-2 mt-4">
          <button onClick={bulk.submit} disabled={!bulk.issueDate || bulk.renewing}
            className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2">
            {bulk.renewing ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Renew All'}
          </button>
          <button onClick={bulk.close} className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm">Cancel</button>
        </div>
    </Modal>
  )
}
