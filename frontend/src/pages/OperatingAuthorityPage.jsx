/**
 * Operating Authority: the unit's own COAs and Part 107 waivers.
 *
 * Org-level, so unlike a pilot certification it belongs to nobody in
 * particular. Supporting PDFs go through the normal document storage.
 */
import { useState, useEffect, useCallback } from 'react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { DocumentsModal } from '@/components/DocumentsModal'
import { useConfirm } from '@/hooks/useConfirm'
import { FileText, Paperclip, Pencil, Plus, Stamp, Trash2 } from 'lucide-react'

const AUTHORITY_TYPES = [
  { value: 'coa', label: 'COA' },
  { value: 'part_107_waiver', label: 'Part 107 Waiver' },
]

const RECORD_STATUSES = [
  { value: 'active', label: 'Active' },
  { value: 'superseded', label: 'Superseded' },
  { value: 'not_applicable', label: 'Not applicable' },
]

const STATUS_BADGES = {
  active: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  expiring: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  expired: 'bg-red-500/15 text-red-400 border-red-500/30',
  retired: 'bg-secondary text-muted-foreground border-border',
}

const EMPTY_FORM = {
  authority_type: 'coa',
  title: '',
  identifier: '',
  issue_date: '',
  expiry_date: '',
  record_status: 'active',
  grounds_unit: true,
  notes: '',
}

const typeLabel = (value) => AUTHORITY_TYPES.find(t => t.value === value)?.label || value
const fmtDate = (s) => (s ? new Date(`${s}T00:00:00`).toLocaleDateString() : '—')

/**
 * The badge a row shows: the hand-set record status when it is not "active",
 * otherwise the status derived from the expiry date.
 */
function statusBadge(authority) {
  if (authority.record_status !== 'active') {
    const label = RECORD_STATUSES.find(s => s.value === authority.record_status)?.label || authority.record_status
    return { label, className: STATUS_BADGES.retired }
  }
  if (authority.status === 'expired') return { label: 'Expired', className: STATUS_BADGES.expired }
  if (authority.status === 'expiring') {
    return { label: `Expires in ${authority.days_remaining}d`, className: STATUS_BADGES.expiring }
  }
  return { label: 'Active', className: STATUS_BADGES.active }
}

export default function OperatingAuthorityPage() {
  const { isSupervisor } = useAuth()
  const toast = useToast()
  const [confirmProps, requestConfirm] = useConfirm()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [docsTarget, setDocsTarget] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.get('/operating-authorities')
      setRows(Array.isArray(data) ? data : [])
    } catch (err) {
      toast.error(err.message)
    } finally {
      setLoading(false)
    }
    // toast is stable for the lifetime of the provider; excluded to keep load()
    // from re-creating on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => { load() }, [load])

  const openCreate = () => {
    setEditing(null)
    setForm(EMPTY_FORM)
    setFormOpen(true)
  }

  const openEdit = (row) => {
    setEditing(row)
    setForm({
      authority_type: row.authority_type,
      title: row.title || '',
      identifier: row.identifier || '',
      issue_date: row.issue_date || '',
      expiry_date: row.expiry_date || '',
      record_status: row.record_status,
      grounds_unit: row.grounds_unit,
      notes: row.notes || '',
    })
    setFormOpen(true)
  }

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    const body = {
      authority_type: form.authority_type,
      title: form.title,
      identifier: form.identifier || null,
      issue_date: form.issue_date || null,
      expiry_date: form.expiry_date || null,
      record_status: form.record_status,
      grounds_unit: form.grounds_unit,
      notes: form.notes || null,
    }
    try {
      if (editing) {
        await api.patch(`/operating-authorities/${editing.id}`, body)
      } else {
        await api.post('/operating-authorities', body)
      }
      setFormOpen(false)
      load()
    } catch (err) {
      toast.error(err.message)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = (row) => {
    requestConfirm({
      title: 'Delete operating authority',
      message: `Permanently delete "${row.title}"? To keep it on file for the reports without it counting against compliance, set its status to Superseded or Not applicable instead.`,
      onConfirm: async () => {
        try {
          await api.delete(`/operating-authorities/${row.id}`)
          load()
        } catch (err) {
          toast.error(err.message)
        }
      },
    })
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold text-foreground flex items-center gap-2">
            <Stamp className="w-5 h-5 text-primary" /> Operating Authority
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            The unit&apos;s COAs and Part 107 waivers. An expired authority the unit
            depends on caps the compliance score.
          </p>
        </div>
        {isSupervisor && (
          <Button onClick={openCreate}><Plus className="w-4 h-4 mr-1" /> Add Authority</Button>
        )}
      </div>

      <section className="bg-card border border-border rounded-xl overflow-hidden">
        {/* Three states, as sibling guards rather than a ternary chain. */}
        {loading && (
          <div className="p-4 text-sm text-muted-foreground">Loading…</div>
        )}
        {!loading && rows.length === 0 && (
          <div className="p-8 text-center">
            <Stamp className="w-10 h-10 mx-auto mb-3 text-muted-foreground/50" />
            <p className="font-medium text-foreground">No operating authorities on file</p>
            <p className="text-sm text-muted-foreground mt-1">
              Nothing is being tracked, so the compliance score is unaffected.
            </p>
          </div>
        )}
        {!loading && rows.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-muted-foreground border-b border-border">
                  <th className="px-4 py-2 font-medium">Authority</th>
                  <th className="px-4 py-2 font-medium">Type</th>
                  <th className="px-4 py-2 font-medium">Issued</th>
                  <th className="px-4 py-2 font-medium">Expires</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Documents</th>
                  <th className="px-4 py-2"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {rows.map(row => {
                  const badge = statusBadge(row)
                  return (
                    <tr key={row.id}>
                      <td className="px-4 py-2">
                        <div className="text-foreground font-medium">{row.title}</div>
                        <div className="text-xs text-muted-foreground">{row.identifier || 'No number'}</div>
                      </td>
                      <td className="px-4 py-2 text-muted-foreground">{typeLabel(row.authority_type)}</td>
                      <td className="px-4 py-2 text-muted-foreground">{fmtDate(row.issue_date)}</td>
                      <td className="px-4 py-2 text-muted-foreground">
                        {row.expiry_date ? fmtDate(row.expiry_date) : 'No expiry'}
                      </td>
                      <td className="px-4 py-2">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${badge.className}`}>
                          {badge.label}
                        </span>
                        {row.record_status === 'active' && !row.grounds_unit && (
                          <div className="text-[10px] text-muted-foreground mt-1">Does not ground the unit</div>
                        )}
                      </td>
                      <td className="px-4 py-2">
                        {row.document_count > 0 ? (
                          <span className="inline-flex items-center gap-1 text-muted-foreground">
                            <Paperclip className="w-3.5 h-3.5" /> {row.document_count}
                          </span>
                        ) : (
                          <span className="text-xs text-amber-400">None attached</span>
                        )}
                      </td>
                      <td className="px-4 py-2">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => setDocsTarget(row)}
                            className="p-1.5 text-muted-foreground hover:text-foreground rounded hover:bg-accent/30"
                            title="Documents"
                            aria-label={`Documents for ${row.title}`}
                          >
                            <FileText className="w-4 h-4" />
                          </button>
                          {isSupervisor && (
                            <>
                              <button
                                onClick={() => openEdit(row)}
                                className="p-1.5 text-muted-foreground hover:text-foreground rounded hover:bg-accent/30"
                                title="Edit"
                                aria-label={`Edit ${row.title}`}
                              >
                                <Pencil className="w-4 h-4" />
                              </button>
                              <button
                                onClick={() => handleDelete(row)}
                                className="p-1.5 text-muted-foreground hover:text-destructive rounded hover:bg-destructive/10"
                                title="Delete"
                                aria-label={`Delete ${row.title}`}
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <Modal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        title={editing ? 'Edit Operating Authority' : 'Add Operating Authority'}
      >
        <form onSubmit={submit} className="space-y-3">
          <div>
            <label htmlFor="oa-type" className="text-sm font-medium text-foreground">Type</label>
            <select
              id="oa-type"
              className="flex h-10 w-full rounded-lg border border-border bg-secondary px-3 text-sm text-foreground"
              value={form.authority_type}
              onChange={e => setForm({ ...form, authority_type: e.target.value })}
            >
              {AUTHORITY_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
          <Input
            label="Title"
            value={form.title}
            onChange={e => setForm({ ...form, title: e.target.value })}
            placeholder="Blanket public safety COA"
            required
          />
          <Input
            label="COA / waiver number"
            value={form.identifier}
            onChange={e => setForm({ ...form, identifier: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Issue date"
              type="date"
              value={form.issue_date}
              onChange={e => setForm({ ...form, issue_date: e.target.value })}
            />
            <Input
              label="Expiry date"
              type="date"
              value={form.expiry_date}
              onChange={e => setForm({ ...form, expiry_date: e.target.value })}
            />
          </div>
          <div>
            <label htmlFor="oa-record-status" className="text-sm font-medium text-foreground">Record status</label>
            <select
              id="oa-record-status"
              className="flex h-10 w-full rounded-lg border border-border bg-secondary px-3 text-sm text-foreground"
              value={form.record_status}
              onChange={e => setForm({ ...form, record_status: e.target.value })}
            >
              {RECORD_STATUSES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
            <p className="text-xs text-muted-foreground mt-1">
              Superseded and not-applicable records stay in the reports but stop
              counting against compliance.
            </p>
          </div>
          <div>
            <label className="flex items-start gap-2 text-sm text-foreground cursor-pointer">
              <input
                type="checkbox"
                className="mt-1"
                checked={form.grounds_unit}
                onChange={e => setForm({ ...form, grounds_unit: e.target.checked })}
              />
              <span>
                Expiry grounds the unit{' '}
                <span className="block text-xs text-muted-foreground">
                  On for an authority the unit flies under. Off for one whose lapse
                  restricts a kind of operation, such as a night waiver.
                </span>
              </span>
            </label>
          </div>
          <div>
            <label htmlFor="oa-notes" className="text-sm font-medium text-foreground">Notes</label>
            <textarea
              id="oa-notes"
              rows={3}
              className="flex w-full rounded-lg border border-border bg-secondary px-3 py-2 text-sm text-foreground"
              value={form.notes}
              onChange={e => setForm({ ...form, notes: e.target.value })}
              placeholder="Conditions, provisions, altitude ceilings"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="secondary" onClick={() => setFormOpen(false)}>Cancel</Button>
            <Button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save'}</Button>
          </div>
        </form>
      </Modal>

      {docsTarget && (
        <DocumentsModal
          entityType="operating_authority"
          entityId={docsTarget.id}
          title={docsTarget.title}
          onClose={() => { setDocsTarget(null); load() }}
        />
      )}

      <ConfirmDialog {...confirmProps} />
    </div>
  )
}
