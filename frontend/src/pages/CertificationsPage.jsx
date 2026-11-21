import { useState, useEffect } from 'react'
import { api, getSection } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { ownsPilot } from '@/lib/ownership'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { Modal } from '@/components/ui/Modal'
import { useConfirm } from '@/hooks/useConfirm'
import { addMonths, emptiedToNull, normalizeDateValue } from '@/lib/utils'
import { CERT_STATUS_COLORS } from '@/lib/constants'
import { sortByName, sortPilotsActiveFirst } from '@/lib/formatters'
import { Plus, Download, Loader2 } from 'lucide-react'
import DocumentUpload from '@/components/DocumentUpload'
import { DEFAULT_FILTERS, canOpenCert, reorderedTypes } from '@/components/certifications/certStatus'
import { useCertView } from '@/components/certifications/useCertView'
import { useBulkRenew } from '@/components/certifications/useBulkRenew'
import { BulkRenewModal } from '@/components/certifications/BulkRenew'
import { CertViews } from '@/components/certifications/CertViews'
import { CertTypesGrid } from '@/components/certifications/CertTypesGrid'

function CertTypeModal({ certType, onSave, onClose }) {
  const [form, setForm] = useState(certType || {
    name: '', category: 'custom', has_expiration: true, renewal_period_months: '', description: '', sort_order: 0
  })
  const [saving, setSaving] = useState(false)
  const handleSubmit = async (e) => {
    e.preventDefault()
    const data = { ...form }
    if (data.renewal_period_months === '') data.renewal_period_months = null
    else data.renewal_period_months = Number.parseInt(data.renewal_period_months, 10)
    setSaving(true)
    try { await onSave(data) } finally { setSaving(false) }
  }
  return (
    <Modal
      open
      onClose={onClose}
      title={certType ? 'Edit Certification Type' : 'Add Certification Type'}
      className="max-w-md"
    >
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label htmlFor="name" className="block text-sm font-medium text-foreground mb-1">Name</label>
            <input id="name" type="text" value={form.name} onChange={e => setForm({...form, name: e.target.value})} required
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
          </div>
          <div>
            <label htmlFor="category" className="block text-sm font-medium text-foreground mb-1">Category</label>
            <select id="category" value={form.category} onChange={e => setForm({...form, category: e.target.value})}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
              <option value="faa">FAA</option>
              <option value="nist">NIST</option>
              <option value="equipment">Equipment</option>
              <option value="insurance">Insurance</option>
              <option value="training">Training</option>
              <option value="custom">Custom</option>
            </select>
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-sm text-foreground">
              <input type="checkbox" checked={form.has_expiration} onChange={e => setForm({...form, has_expiration: e.target.checked})}
                className="rounded border-border" />{' '}
              Has Expiration Date
            </label>
          </div>
          {form.has_expiration && (
            <div>
              <label htmlFor="renewal-period-months" className="block text-sm font-medium text-foreground mb-1">Renewal Period (months)</label>
              <input id="renewal-period-months" type="number" value={form.renewal_period_months || ''} onChange={e => setForm({...form, renewal_period_months: e.target.value})}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" placeholder="e.g. 24" />
            </div>
          )}
          <div>
            <label htmlFor="description" className="block text-sm font-medium text-foreground mb-1">Description</label>
            <textarea id="description" value={form.description || ''} onChange={e => setForm({...form, description: e.target.value})}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm h-16 resize-none" />
          </div>
          <div className="flex gap-2 pt-2">
            <button type="submit" disabled={saving} className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2">
              {saving && <Loader2 className="w-4 h-4 animate-spin" />}
              {!saving && (certType ? 'Update' : 'Add')}
            </button>
            <button type="button" onClick={onClose} className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm">Cancel</button>
          </div>
        </form>
    </Modal>
  )
}

function AssignCertModal({ pilots, certTypes, existingCert, defaults, onSave, onRenew, onDelete, onClose, certFolderId }) {
  const { user, canRecord } = useAuth()
  const [form, setForm] = useState(existingCert ? {
    pilot_id: String(existingCert.pilot_id || ''),
    certification_type_id: String(existingCert.certification_type_id || ''),
    status: existingCert.status || 'not_started',
    issue_date: existingCert.issue_date || '',
    expiration_date: existingCert.expiration_date || '',
    certificate_number: existingCert.certificate_number || '',
    nist_level: existingCert.nist_level == null ? '' : String(existingCert.nist_level),
    notes: existingCert.notes || '',
  } : {
    pilot_id: defaults?.pilot_id ? String(defaults.pilot_id) : '',
    certification_type_id: defaults?.certification_type_id ? String(defaults.certification_type_id) : '',
    status: 'not_started', issue_date: '', expiration_date: '', certificate_number: '', nist_level: '', notes: ''
  })
  const isEditing = !!existingCert
  const [saving, setSaving] = useState(false)
  const [showRenew, setShowRenew] = useState(false)
  const [renewForm, setRenewForm] = useState({ issue_date: '', expiration_date: '', certificate_number: existingCert?.certificate_number || '', notes: '' })
  const [history, setHistory] = useState([])
  const toast = useToast()

  // Load renewal history when editing
  useEffect(() => {
    if (isEditing && existingCert?.id) {
      api.get(`/pilot-certifications/${existingCert.id}/history`).then(setHistory).catch(() => {})
    }
  }, [isEditing, existingCert?.id])

  // Check if this cert type has expiration (for showing Renew button)
  const certType = certTypes.find(c => c.id === Number(form.certification_type_id))
  const hasExpiration = certType?.has_expiration !== false

  // Auto-calculate expiry when renewal issue_date changes
  useEffect(() => {
    if (showRenew && renewForm.issue_date && certType?.renewal_period_months) {
      const expiration = addMonths(renewForm.issue_date, certType.renewal_period_months)
      setRenewForm(prev => ({ ...prev, expiration_date: expiration }))
    }
  }, [renewForm.issue_date, showRenew])

  const handleSubmit = async (e) => {
    e.preventDefault()
    const data = { ...form }
    data.pilot_id = Number.parseInt(data.pilot_id, 10)
    data.certification_type_id = Number.parseInt(data.certification_type_id, 10)
    if (data.nist_level) data.nist_level = Number.parseInt(data.nist_level, 10)
    else data.nist_level = null
    emptiedToNull(data, existingCert)
    setSaving(true)
    try { await onSave(data, isEditing ? existingCert.id : null) } finally { setSaving(false) }
  }

  const handleRenew = async () => {
    if (!renewForm.issue_date) { toast.error('Issue date is required for renewal'); return }
    setSaving(true)
    try {
      const data = { ...renewForm }
      Object.keys(data).forEach(k => { if (data[k] === '') delete data[k] })
      await onRenew(existingCert.id, data)
    } finally { setSaving(false) }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={isEditing ? 'Edit Certification' : 'Assign Certification'}
      className="max-w-md max-h-[90vh] overflow-y-auto"
    >
        {/* Renewal Form */}
        {showRenew ? (
          <div className="space-y-3">
            <div className="bg-primary/10 border border-primary/30 rounded-lg p-3 text-sm text-foreground">
              Renewing certification. The current record will be archived and a new one created with updated dates.
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="renew-issue" className="block text-sm font-medium text-foreground mb-1">New Issue Date</label>
                <input id="renew-issue" type="date" value={renewForm.issue_date} onChange={e => setRenewForm({...renewForm, issue_date: e.target.value})}
                  onBlur={e => { const n = normalizeDateValue(e.target.value); if (n !== e.target.value) setRenewForm(prev => ({...prev, issue_date: n})) }}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
              <div>
                <label htmlFor="renew-expiry" className="block text-sm font-medium text-foreground mb-1">New Expiration{certType?.renewal_period_months ? ` (auto: +${certType.renewal_period_months}mo)` : ''}</label>
                <input id="renew-expiry" type="date" value={renewForm.expiration_date} onChange={e => setRenewForm({...renewForm, expiration_date: e.target.value})}
                  onBlur={e => { const n = normalizeDateValue(e.target.value); if (n !== e.target.value) setRenewForm(prev => ({...prev, expiration_date: n})) }}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
            </div>
            <div>
              <label htmlFor="renew-cert-num" className="block text-sm font-medium text-foreground mb-1">Certificate Number</label>
              <input id="renew-cert-num" type="text" value={renewForm.certificate_number} onChange={e => setRenewForm({...renewForm, certificate_number: e.target.value})}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
            <div>
              <label htmlFor="renew-notes" className="block text-sm font-medium text-foreground mb-1">Notes</label>
              <input id="renew-notes" type="text" value={renewForm.notes} onChange={e => setRenewForm({...renewForm, notes: e.target.value})}
                placeholder="Optional renewal notes"
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
            <div className="flex gap-2 pt-2">
              <button type="button" onClick={handleRenew} disabled={saving || !renewForm.issue_date}
                className="flex-1 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2">
                {saving && <Loader2 className="w-4 h-4 animate-spin" />}{!saving && 'Renew Certification'}
              </button>
              <button type="button" onClick={() => setShowRenew(false)} className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm">Back</button>
            </div>
          </div>
        ) : (
          /* Standard Edit/Assign Form */
          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <label htmlFor="pilot" className="block text-sm font-medium text-foreground mb-1">Pilot</label>
              <select id="pilot" value={form.pilot_id} onChange={e => setForm({...form, pilot_id: e.target.value})} required
                disabled={isEditing}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm disabled:opacity-60">
                <option value="">Select pilot...</option>
                {sortPilotsActiveFirst(pilots).map(p => <option key={p.id} value={p.id}>{p.full_name}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="certification" className="block text-sm font-medium text-foreground mb-1">Certification</label>
              <select id="certification" value={form.certification_type_id} onChange={e => setForm({...form, certification_type_id: e.target.value})} required
                disabled={isEditing}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm disabled:opacity-60">
                <option value="">Select cert type...</option>
                {sortByName(certTypes.filter(c => c.is_active || c.id === Number(form.certification_type_id)), 'name').map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="status" className="block text-sm font-medium text-foreground mb-1">Status</label>
              <select id="status" value={form.status} onChange={e => setForm({...form, status: e.target.value})}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
                {Object.keys(CERT_STATUS_COLORS).map(s => <option key={s} value={s}>{s.replaceAll('_', ' ')}</option>)}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="issue-date" className="block text-sm font-medium text-foreground mb-1">Issue Date</label>
                <input id="issue-date" type="date" value={form.issue_date} onChange={e => setForm({...form, issue_date: e.target.value})}
                  onBlur={e => { const n = normalizeDateValue(e.target.value); if (n !== e.target.value) setForm(prev => ({...prev, issue_date: n})) }}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
              <div>
                <label htmlFor="expiration-date" className="block text-sm font-medium text-foreground mb-1">Expiration Date</label>
                <input id="expiration-date" type="date" value={form.expiration_date} onChange={e => setForm({...form, expiration_date: e.target.value})}
                  onBlur={e => { const n = normalizeDateValue(e.target.value); if (n !== e.target.value) setForm(prev => ({...prev, expiration_date: n})) }}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
            </div>
            <div>
              <label htmlFor="certificate-number" className="block text-sm font-medium text-foreground mb-1">Certificate Number</label>
              <input id="certificate-number" type="text" value={form.certificate_number} onChange={e => setForm({...form, certificate_number: e.target.value})}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
            {certType?.category === 'nist' && (
              <div>
                <label htmlFor="nist-level" className="block text-sm font-medium text-foreground mb-1">NIST Level</label>
                <input id="nist-level" type="number" min="0" value={form.nist_level} onChange={e => setForm({...form, nist_level: e.target.value})}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
            )}
            <div>
              <label htmlFor="cert-notes" className="block text-sm font-medium text-foreground mb-1">Notes</label>
              <textarea id="cert-notes" value={form.notes} onChange={e => setForm({...form, notes: e.target.value})}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm h-16 resize-none" />
            </div>
            <div className="flex gap-2 pt-2">
              <button type="submit" disabled={saving} className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2">{saving && <Loader2 className="w-4 h-4 animate-spin" />}{!saving && (isEditing ? 'Update' : 'Assign')}</button>
              {isEditing && hasExpiration && (
                <button type="button" onClick={() => setShowRenew(true)} className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:opacity-90">Renew</button>
              )}
              {isEditing && onDelete && (
                <button type="button" onClick={() => onDelete(existingCert.id)}
                  className="px-4 py-2 bg-destructive/10 text-destructive rounded-lg text-sm font-medium hover:bg-destructive/20">Remove</button>
              )}
              <button type="button" onClick={onClose} className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm">Cancel</button>
            </div>
          </form>
        )}

        {/* Document Upload */}
        {isEditing && existingCert?.id && !showRenew && (
          <div className="mt-4">
            <DocumentUpload entityType="certification" entityId={existingCert.id} folderId={certFolderId}
              canUpload={canRecord('files.upload', ownsPilot(user, existingCert.pilot_id))} />
          </div>
        )}

        {/* Renewal History */}
        {isEditing && history.length > 0 && !showRenew && (
          <div className="mt-4 border-t border-border pt-3">
            <h3 className="text-sm font-medium text-muted-foreground mb-2">Renewal History</h3>
            <div className="space-y-1">
              {history.map(h => (
                <div key={h.id} className="flex items-center gap-3 text-xs text-muted-foreground bg-secondary/50 rounded-lg px-3 py-2">
                  <span className="font-mono">{h.issue_date || '—'}</span>
                  <span>to</span>
                  <span className="font-mono">{h.expiration_date || '—'}</span>
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${CERT_STATUS_COLORS[h.status] || 'bg-muted text-muted-foreground'}`}>{h.status}</span>
                </div>
              ))}
            </div>
          </div>
        )}
    </Modal>
  )
}

/** The read-only view of an existing certification: its documents. Changing the
 *  certification itself needs certifications.manage. */
function CertDocumentsModal({ cert, folderId, onClose }) {
  const { user, canRecord } = useAuth()
  return (
    <Modal open onClose={onClose} title="Certification Documents">
      <DocumentUpload entityType="certification" entityId={cert.id} folderId={folderId}
        canUpload={canRecord('files.upload', ownsPilot(user, cert.pilot_id))} />
    </Modal>
  )
}

// The edit form's view of a matrix cell's record.
function editableCert(row, ct, cert) {
  return {
    id: cert.id,
    pilot_id: row.pilot_id,
    certification_type_id: ct.id,
    status: cert.status,
    issue_date: cert.issue_date || '',
    expiration_date: cert.expiration_date || '',
    certificate_number: cert.certificate_number || '',
    nist_level: cert.nist_level,
    notes: cert.notes || '',
  }
}

const TAB_ON = 'border-primary text-primary'
const TAB_OFF = 'border-transparent text-muted-foreground hover:text-foreground'

function TabButton({ active, onClick, children }) {
  return (
    <button onClick={onClick} className={`shrink-0 text-sm font-medium pb-2 border-b-2 transition-colors whitespace-nowrap ${active ? TAB_ON : TAB_OFF}`}>
      {children}
    </button>
  )
}

function parseStatusLabels(value) {
  if (!value) return {}
  try { return JSON.parse(value) } catch { return {} }
}

/** Loads the page data; reload() refreshes it after a change. */
function useCertificationsData() {
  const [data, setData] = useState({ certTypes: [], matrix: [], pilots: [], labels: {} })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const reload = () => {
    Promise.all([
      api.get('/certification-types'),
      api.get('/certifications/matrix'),
      api.get('/pilots/options'),
      api.get('/settings/cert_status_labels').catch(() => ({ value: '' })),
    ]).then(([certTypes, mx, pilots, labels]) => {
      setData({ certTypes, matrix: mx.matrix || [], pilots, labels: parseStatusLabels(labels.value) })
    }).catch(err => setError(err.message)).finally(() => setLoading(false))
  }
  useEffect(() => { reload() }, [])
  return { ...data, loading, error, reload }
}

// Documents auto-file to the Certifications folder. Auto-filing is optional:
// with no folder list, documents simply stay unfiled.
function useCertFolderId(canSeeFiles) {
  const [folderId, setFolderId] = useState(null)
  useEffect(() => {
    getSection(canSeeFiles, '/folders', []).then(folders => {
      const f = (Array.isArray(folders) ? folders : folders.folders || []).find(f => f.name === 'Certifications')
      if (f) setFolderId(f.id)
    })
  }, [canSeeFiles])
  return folderId
}

export default function CertificationsPage() {
  const [tab, setTab] = useState('matrix')
  const [view, setView] = useCertView()
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [modal, setModal] = useState(null)
  const [editCert, setEditCert] = useState(null)
  // Prefill for the assign modal when opened from an empty matrix cell.
  const [assignDefaults, setAssignDefaults] = useState(null)
  const { certTypes, matrix, pilots, labels, loading, error, reload } = useCertificationsData()
  const { can } = useAuth()
  const canManage = can('certifications.manage')
  const canSeeFiles = can('files.view')
  const toast = useToast()
  const [confirmProps, requestConfirm] = useConfirm()
  const certFolderId = useCertFolderId(canSeeFiles)
  const bulk = useBulkRenew(reload)

  const closeModal = () => { setModal(null); setEditCert(null) }
  // Bulk renewal lives in the matrix, so leaving it (view or tab) drops the selection.
  const changeView = (next) => {
    if (next !== 'matrix') bulk.clear()
    setView(next)
  }
  const changeTab = (next) => {
    if (next !== 'matrix') bulk.clear()
    setTab(next)
  }
  // Runs a change, then the follow-up and a reload; a failure shows a toast.
  const run = async (change, after) => {
    try {
      await change()
      after?.()
      reload()
    } catch (err) { toast.error(err.message) }
  }

  // The matrix API fills an empty pilot and type pair with a placeholder whose id is null.
  const openCertCell = (row, ct, cert) => {
    if (cert?.id) {
      setEditCert(editableCert(row, ct, cert))
      setModal('editCert')
    } else {
      setEditCert(null)
      setAssignDefaults({ pilot_id: row.pilot_id, certification_type_id: ct.id })
      setModal('assign')
    }
  }

  const handleSaveCertType = (data) => run(
    () => (data.id ? api.patch(`/certification-types/${data.id}`, data) : api.post('/certification-types', data)),
    () => setModal(null),
  )

  const handleDeleteCertType = (id) => requestConfirm({
    title: 'Delete Certification Type',
    message: 'Are you sure you want to delete this certification type?',
    onConfirm: () => run(() => api.delete(`/certification-types/${id}`)),
  })

  // Hide a cert type from the matrix (and matrix API) without deleting its
  // records; unhide restores it.
  const handleToggleCertTypeHidden = (ct) => run(() => api.patch(`/certification-types/${ct.id}`, { is_active: !ct.is_active }))

  const handleReorderCertType = (ctId, direction) => {
    const items = reorderedTypes(certTypes, ctId, direction)
    if (items) run(() => api.patch('/certification-types/reorder', { items }))
  }

  const handleDeleteCert = (certId) => requestConfirm({
    title: 'Remove Certification',
    message: 'Remove this certification and its renewal history from the pilot? Attached documents are kept. This cannot be undone.',
    onConfirm: () => run(() => api.delete(`/pilot-certifications/${certId}`), closeModal),
  })

  const handleAssignCert = (data, certId) => run(
    () => (certId ? api.patch(`/pilot-certifications/${certId}`, data) : api.post('/pilot-certifications', data)),
    closeModal,
  )

  const handleRenewCert = (certId, renewData) => run(
    () => api.post(`/pilot-certifications/${certId}/renew`, renewData),
    () => { toast.success('Certification renewed successfully'); closeModal() },
  )

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>

  const ctx = {
    labels, canManage, selected: bulk.selected, onToggle: bulk.toggle,
    canOpen: (cert) => canOpenCert(cert, { canManage, canSeeFiles }),
    onOpen: openCertCell, onReorder: handleReorderCertType,
  }
  const editing = modal === 'editCert' && editCert

  return (
    <div className="space-y-4">
      {error && <div className="bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg p-4 mb-4">{error}</div>}
      {/* Tabs */}
      <div className="flex items-center gap-4 border-b border-border pb-2 overflow-x-auto">
        <TabButton active={tab === 'matrix'} onClick={() => changeTab('matrix')}>Certifications</TabButton>
        <TabButton active={tab === 'types'} onClick={() => changeTab('types')}>Cert Types</TabButton>
        <div className="flex-1" />
        {can('reports.export') && (
          <button
            onClick={() => api.download('/export/certifications/csv')}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90"
          >
            <Download className="w-4 h-4" /> Export CSV
          </button>
        )}
        {canManage && tab === 'types' && (
          <button onClick={() => setModal('addType')} className="flex items-center gap-2 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90">
            <Plus className="w-4 h-4" /> Add Type
          </button>
        )}
        {canManage && tab === 'matrix' && (
          <button onClick={() => { setAssignDefaults(null); setModal('assign') }} className="flex items-center gap-2 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90">
            <Plus className="w-4 h-4" /> Assign Cert
          </button>
        )}
      </div>

      {tab === 'matrix' && (
        <CertViews matrix={matrix} certTypes={certTypes} filters={filters} onFiltersChange={setFilters}
          view={view} onViewChange={changeView} bulk={bulk} ctx={ctx} />
      )}

      {tab === 'types' && (
        <CertTypesGrid certTypes={certTypes} canManage={canManage} onToggleHidden={handleToggleCertTypeHidden}
          onEdit={setModal} onDelete={handleDeleteCertType} />
      )}

      {/* Modals */}
      {modal === 'addType' && <CertTypeModal onSave={handleSaveCertType} onClose={() => setModal(null)} />}
      {modal === 'assign' && <AssignCertModal pilots={pilots} certTypes={certTypes} defaults={assignDefaults} onSave={handleAssignCert} onClose={() => { closeModal(); setAssignDefaults(null) }} certFolderId={certFolderId} />}
      {editing && canManage && <AssignCertModal pilots={pilots} certTypes={certTypes} existingCert={editCert} onSave={handleAssignCert} onRenew={handleRenewCert} onDelete={handleDeleteCert} onClose={closeModal} certFolderId={certFolderId} />}
      {editing && !canManage && <CertDocumentsModal cert={editCert} folderId={certFolderId} onClose={closeModal} />}
      {modal?.name && <CertTypeModal certType={modal} onSave={handleSaveCertType} onClose={() => setModal(null)} />}
      {bulk.open && <BulkRenewModal bulk={bulk} />}
      <ConfirmDialog {...confirmProps} />
    </div>
  )
}
