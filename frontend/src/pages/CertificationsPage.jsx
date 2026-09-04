import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { Modal } from '@/components/ui/Modal'
import { useConfirm } from '@/hooks/useConfirm'
import { normalizeDateValue } from '@/lib/utils'
import { CERT_STATUS_COLORS } from '@/lib/constants'
import { sortByName, sortPilotsActiveFirst } from '@/lib/formatters'
import { Plus, Edit, Trash2, ShieldCheck, Search, Filter, Download, ChevronLeft, ChevronRight, Loader2, Eye, EyeOff } from 'lucide-react'
import DocumentUpload from '@/components/DocumentUpload'

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
                className="rounded border-border" />
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
      const d = new Date(renewForm.issue_date)
      d.setMonth(d.getMonth() + certType.renewal_period_months)
      setRenewForm(prev => ({ ...prev, expiration_date: d.toISOString().split('T')[0] }))
    }
  }, [renewForm.issue_date, showRenew])

  const handleSubmit = async (e) => {
    e.preventDefault()
    const data = { ...form }
    data.pilot_id = Number.parseInt(data.pilot_id, 10)
    data.certification_type_id = Number.parseInt(data.certification_type_id, 10)
    if (data.nist_level) data.nist_level = Number.parseInt(data.nist_level, 10)
    else data.nist_level = null
    Object.keys(data).forEach(k => { if (data[k] === '') delete data[k] })
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
            <DocumentUpload entityType="certification" entityId={existingCert.id} folderId={certFolderId} />
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

export default function CertificationsPage() {
  const [tab, setTab] = useState('matrix')
  const [certTypes, setCertTypes] = useState([])
  const [matrix, setMatrix] = useState([])
  const [pilots, setPilots] = useState([])
  const [modal, setModal] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const { isSupervisor } = useAuth()
  const toast = useToast()
  const [confirmProps, requestConfirm] = useConfirm()

  // Auto-file documents to Certifications folder
  const [certFolderId, setCertFolderId] = useState(null)
  useEffect(() => {
    api.get('/folders').then(folders => {
      const f = (Array.isArray(folders) ? folders : folders.folders || []).find(f => f.name === 'Certifications')
      if (f) setCertFolderId(f.id)
    }).catch(() => {})
  }, [])

  // Custom cert status labels
  const [certStatusLabels, setCertStatusLabels] = useState({})

  // Filter state
  const [statusFilter, setStatusFilter] = useState('all')
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [pilotSearch, setPilotSearch] = useState('')
  const [hideEmpty, setHideEmpty] = useState(false)

  const load = () => {
    Promise.all([
      api.get('/certification-types'),
      api.get('/certifications/matrix'),
      api.get('/pilots'),
      api.get('/settings/cert_status_labels').catch(() => ({ value: '' })),
    ]).then(([ct, mx, p, labels]) => {
      setCertTypes(ct); setMatrix(mx.matrix || []); setPilots(p)
      if (labels.value) {
        try { setCertStatusLabels(JSON.parse(labels.value)) } catch { /* invalid JSON */ }
      }
    }).catch(err => setError(err.message)).finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

  // Filtered cert type columns based on category filter
  const filteredCertTypes = useMemo(() => {
    const active = certTypes.filter(c => c.is_active)
    if (categoryFilter === 'all') return active
    return active.filter(c => c.category === categoryFilter)
  }, [certTypes, categoryFilter])

  // Filtered matrix rows based on status, pilot search, and hide-empty
  const filteredMatrix = useMemo(() => {
    let rows = matrix

    // Filter by pilot name search
    if (pilotSearch.trim()) {
      const q = pilotSearch.toLowerCase().trim()
      rows = rows.filter(row => row.pilot_name?.toLowerCase().includes(q))
    }

    // Filter by status: show only pilots who have at least one cert matching the status
    if (statusFilter !== 'all') {
      rows = rows.filter(row => {
        const certs = row.certs || {}
        return Object.values(certs).some(c => c?.status === statusFilter)
      })
    }

    // Hide empty: hide pilots who have no certifications assigned at all
    if (hideEmpty) {
      rows = rows.filter(row => {
        const certs = row.certs || {}
        return Object.keys(certs).length > 0
      })
    }

    return rows
  }, [matrix, statusFilter, pilotSearch, hideEmpty])

  const handleSaveCertType = async (data) => {
    try {
      if (data.id) await api.patch(`/certification-types/${data.id}`, data)
      else await api.post('/certification-types', data)
      setModal(null); load()
    } catch (err) { toast.error(err.message) }
  }

  const handleDeleteCertType = (id) => {
    requestConfirm({
      title: 'Delete Certification Type',
      message: 'Are you sure you want to delete this certification type?',
      onConfirm: async () => {
        try { await api.delete(`/certification-types/${id}`); load() } catch (err) { toast.error(err.message) }
      }
    })
  }

  // Hide a cert type from the matrix (and matrix API) without deleting its
  // records; unhide restores it.
  const handleToggleCertTypeHidden = async (ct) => {
    try {
      await api.patch(`/certification-types/${ct.id}`, { is_active: !ct.is_active })
      load()
    } catch (err) { toast.error(err.message) }
  }

  const handleReorderCertType = async (ctId, direction) => {
    // Work with the active cert types in their current sorted order
    const active = [...certTypes].filter(c => c.is_active)
    const idx = active.findIndex(c => c.id === ctId)
    if (idx < 0) return
    const targetIdx = direction === 'left' ? idx - 1 : idx + 1
    if (targetIdx < 0 || targetIdx >= active.length) return
    // Swap
    const reordered = [...active]
    const temp = reordered[idx]
    reordered[idx] = reordered[targetIdx]
    reordered[targetIdx] = temp
    // Assign new sort_order values
    const items = reordered.map((ct, i) => ({ id: ct.id, sort_order: i }))
    try {
      await api.patch('/certification-types/reorder', { items })
      load()
    } catch (err) { toast.error(err.message) }
  }

  const [editCert, setEditCert] = useState(null)
  // Prefill for the assign modal when opened from an empty matrix cell.
  const [assignDefaults, setAssignDefaults] = useState(null)

  const handleDeleteCert = (certId) => {
    requestConfirm({
      title: 'Remove Certification',
      message: 'Remove this certification from the pilot? This cannot be undone.',
      onConfirm: async () => {
        try {
          await api.delete(`/pilot-certifications/${certId}`)
          setModal(null); setEditCert(null); load()
        } catch (err) { toast.error(err.message) }
      }
    })
  }

  const handleAssignCert = async (data, certId) => {
    try {
      if (certId) {
        await api.patch(`/pilot-certifications/${certId}`, data)
      } else {
        await api.post('/pilot-certifications', data)
      }
      setModal(null); setEditCert(null); load()
    } catch (err) { toast.error(err.message) }
  }

  const handleRenewCert = async (certId, renewData) => {
    try {
      await api.post(`/pilot-certifications/${certId}/renew`, renewData)
      toast.success('Certification renewed successfully')
      setModal(null); setEditCert(null); load()
    } catch (err) { toast.error(err.message) }
  }

  // Bulk renewal (e.g. a training day): multi-select certs in the matrix and
  // renew them all with one issue date.
  const [selectedCerts, setSelectedCerts] = useState(() => new Set())
  const [bulkRenewOpen, setBulkRenewOpen] = useState(false)
  const [bulkIssueDate, setBulkIssueDate] = useState('')
  const [bulkNotes, setBulkNotes] = useState('')
  const [bulkRenewing, setBulkRenewing] = useState(false)

  const toggleCertSelection = (certId) => {
    setSelectedCerts(prev => {
      const next = new Set(prev)
      if (next.has(certId)) next.delete(certId)
      else next.add(certId)
      return next
    })
  }

  const handleBulkRenew = async () => {
    if (!bulkIssueDate) { toast.error('Issue date is required'); return }
    setBulkRenewing(true)
    try {
      const res = await api.post('/pilot-certifications/bulk-renew', {
        pilot_certification_ids: [...selectedCerts],
        issue_date: bulkIssueDate,
        notes: bulkNotes || null,
      })
      toast.success(`Renewed ${res.renewed} certification(s)`)
      setBulkRenewOpen(false); setSelectedCerts(new Set()); setBulkIssueDate(''); setBulkNotes(''); load()
    } catch (err) {
      toast.error(err.message)
    } finally {
      setBulkRenewing(false)
    }
  }

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>

  return (
    <div className="space-y-4">
      {error && <div className="bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg p-4 mb-4">{error}</div>}
      {/* Tabs */}
      <div className="flex items-center gap-4 border-b border-border pb-2 overflow-x-auto">
        <button onClick={() => setTab('matrix')} className={`text-sm font-medium pb-2 border-b-2 transition-colors whitespace-nowrap ${tab === 'matrix' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'}`}>
          Certification Matrix
        </button>
        <button onClick={() => setTab('types')} className={`text-sm font-medium pb-2 border-b-2 transition-colors whitespace-nowrap ${tab === 'types' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'}`}>
          Cert Types
        </button>
        <div className="flex-1" />
        <button
          onClick={() => api.download('/export/certifications/csv')}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90"
        >
          <Download className="w-4 h-4" /> Export CSV
        </button>
        {isSupervisor && tab === 'types' && (
          <button onClick={() => setModal('addType')} className="flex items-center gap-2 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90">
            <Plus className="w-4 h-4" /> Add Type
          </button>
        )}
        {isSupervisor && tab === 'matrix' && (
          <button onClick={() => { setAssignDefaults(null); setModal('assign') }} className="flex items-center gap-2 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90">
            <Plus className="w-4 h-4" /> Assign Cert
          </button>
        )}
      </div>

      {/* Matrix View */}
      {tab === 'matrix' && (
        <>
          {/* Filter Bar */}
          <div className="bg-card border border-border rounded-xl p-4">
            <div className="flex flex-col sm:flex-row flex-wrap items-start sm:items-center gap-2 sm:gap-3">
              <div className="flex items-center gap-2">
                <Filter className="w-4 h-4 text-muted-foreground" />
                <span className="text-sm font-medium text-muted-foreground">Filters:</span>
              </div>

              {/* Pilot Search */}
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-muted-foreground absolute left-2.5 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Search pilots..."
                  value={pilotSearch}
                  onChange={e => setPilotSearch(e.target.value)}
                  className="pl-8 pr-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm w-44 focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>

              {/* Status Filter */}
              <select
                value={statusFilter}
                onChange={e => setStatusFilter(e.target.value)}
                className="px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm"
              >
                <option value="all">All Statuses</option>
                {Object.keys(CERT_STATUS_COLORS).map(s => (
                  <option key={s} value={s}>{s.replaceAll('_', ' ')}</option>
                ))}
              </select>

              {/* Category Filter */}
              <select
                value={categoryFilter}
                onChange={e => setCategoryFilter(e.target.value)}
                className="px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm"
              >
                <option value="all">All Categories</option>
                <option value="faa">FAA</option>
                <option value="nist">NIST</option>
                <option value="equipment">Equipment</option>
                <option value="insurance">Insurance</option>
                <option value="training">Training</option>
                <option value="custom">Custom</option>
              </select>

              {/* Hide Empty */}
              <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                <input
                  type="checkbox"
                  checked={hideEmpty}
                  onChange={e => setHideEmpty(e.target.checked)}
                  className="rounded border-border"
                />
                Hide empty
              </label>

              {/* Result count */}
              <span className="text-xs text-muted-foreground ml-auto">
                {filteredMatrix.length} of {matrix.length} pilots | {filteredCertTypes.length} cert columns
              </span>
            </div>
          </div>

          {/* Bulk renewal action bar */}
          {isSupervisor && selectedCerts.size > 0 && (
            <div className="flex items-center gap-3 bg-primary/10 border border-primary/30 rounded-lg px-4 py-2">
              <span className="text-sm font-medium text-foreground">{selectedCerts.size} selected</span>
              <button
                onClick={() => { setBulkIssueDate(new Date().toISOString().split('T')[0]); setBulkRenewOpen(true) }}
                className="px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90"
              >
                Renew selected
              </button>
              <button onClick={() => setSelectedCerts(new Set())} className="text-sm text-muted-foreground hover:text-foreground">
                Clear
              </button>
            </div>
          )}

          {/* Matrix Table */}
          <div className="bg-card border border-border rounded-xl overflow-auto max-h-[calc(100vh-16rem)]">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/30 sticky top-0 z-20">
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground sticky left-0 bg-card z-30 min-w-[150px]">Pilot</th>
                  {filteredCertTypes.map((ct, idx) => (
                    <th key={ct.id} className="text-center px-3 py-3 font-medium text-muted-foreground min-w-[100px] bg-card">
                      <div className="flex items-center justify-center gap-0.5">
                        {isSupervisor && (
                          <button
                            onClick={() => handleReorderCertType(ct.id, 'left')}
                            disabled={idx === 0}
                            className="p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-20 disabled:cursor-not-allowed"
                            title="Move left"
                          >
                            <ChevronLeft className="w-3 h-3" />
                          </button>
                        )}
                        <span className="text-xs">{ct.name}</span>
                        {isSupervisor && (
                          <button
                            onClick={() => handleReorderCertType(ct.id, 'right')}
                            disabled={idx === filteredCertTypes.length - 1}
                            className="p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-20 disabled:cursor-not-allowed"
                            title="Move right"
                          >
                            <ChevronRight className="w-3 h-3" />
                          </button>
                        )}
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredMatrix.map(row => (
                  <tr key={row.pilot_id} className="border-b border-border/50 hover:bg-accent/30">
                    <td className="px-4 py-2 text-foreground font-medium sticky left-0 bg-card z-10">
                      <Link to={`/pilots/${row.pilot_id}`} className="text-primary hover:underline">
                        {row.pilot_name}
                      </Link>
                    </td>
                    {filteredCertTypes.map(ct => {
                      const cert = row.certs?.[ct.id]
                      const status = cert?.status || 'not_started'
                      return (
                        <td key={ct.id} className="relative px-3 py-2 text-center cursor-pointer hover:bg-accent/40 transition-colors"
                          tabIndex={0} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.currentTarget.click() } }}
                          onClick={() => {
                            if (cert) {
                              setEditCert({
                                id: cert.id,
                                pilot_id: row.pilot_id,
                                certification_type_id: ct.id,
                                status: cert.status,
                                issue_date: cert.issue_date || '',
                                expiration_date: cert.expiration_date || '',
                                certificate_number: cert.certificate_number || '',
                                nist_level: cert.nist_level,
                                notes: cert.notes || '',
                              })
                              setModal('editCert')
                            } else {
                              setEditCert(null)
                              setAssignDefaults({ pilot_id: row.pilot_id, certification_type_id: ct.id })
                              setModal('assign')
                            }
                          }}>
                          {isSupervisor && cert && ct.has_expiration && (
                            <input
                              type="checkbox"
                              checked={selectedCerts.has(cert.id)}
                              onClick={e => e.stopPropagation()}
                              onKeyDown={e => e.stopPropagation()}
                              onChange={() => toggleCertSelection(cert.id)}
                              className="absolute top-1 left-1 rounded border-border"
                              title="Select for bulk renewal"
                              aria-label="Select certification for bulk renewal"
                            />
                          )}
                          <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${CERT_STATUS_COLORS[status] || CERT_STATUS_COLORS.not_started}`}>
                            {certStatusLabels[status] || status.replaceAll('_', ' ')}
                          </span>
                          {cert?.expiration_date && (
                            <div className="text-xs text-muted-foreground mt-0.5">{cert.expiration_date}</div>
                          )}
                        </td>
                      )
                    })}
                  </tr>
                ))}
                {filteredMatrix.length === 0 && (
                  <tr><td colSpan={filteredCertTypes.length + 1} className="px-4 py-12 text-center text-muted-foreground">
                    {matrix.length === 0 ? 'No pilots or certifications configured yet' : 'No pilots match the current filters'}
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* Cert Types View */}
      {tab === 'types' && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {certTypes.map(ct => (
            <div key={ct.id} className={`bg-card border border-border rounded-xl p-4 ${ct.is_active ? '' : 'opacity-60'}`}>
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <ShieldCheck className="w-5 h-5 text-primary" />
                  <h3 className="font-semibold text-foreground">{ct.name}</h3>
                  {!ct.is_active && (
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-zinc-500/15 text-zinc-400">Hidden</span>
                  )}
                </div>
                {isSupervisor && (
                  <div className="flex gap-1">
                    <button onClick={() => handleToggleCertTypeHidden(ct)} className="p-1 text-muted-foreground hover:text-foreground"
                      aria-label={ct.is_active ? 'Hide' : 'Unhide'} title={ct.is_active ? 'Hide from the matrix (keeps records)' : 'Show on the matrix again'}>
                      {ct.is_active ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
                    </button>
                    <button onClick={() => setModal(ct)} className="p-1 text-muted-foreground hover:text-foreground" aria-label="Edit"><Edit className="w-3.5 h-3.5" /></button>
                    <button onClick={() => handleDeleteCertType(ct.id)} className="p-1 text-muted-foreground hover:text-destructive" aria-label="Delete"><Trash2 className="w-3.5 h-3.5" /></button>
                  </div>
                )}
              </div>
              <div className="mt-2 space-y-1 text-xs text-muted-foreground">
                <p>Category: <span className="text-foreground">{ct.category}</span></p>
                <p>Expires: <span className="text-foreground">{ct.has_expiration ? `Yes (${ct.renewal_period_months || '?'}mo)` : 'No'}</span></p>
                {ct.description && <p className="mt-1">{ct.description}</p>}
              </div>
            </div>
          ))}
          {certTypes.length === 0 && (
            <div className="col-span-full text-center py-12 text-muted-foreground">No certification types configured yet</div>
          )}
        </div>
      )}

      {/* Modals */}
      {modal === 'addType' && <CertTypeModal onSave={handleSaveCertType} onClose={() => setModal(null)} />}
      {modal === 'assign' && <AssignCertModal pilots={pilots} certTypes={certTypes} defaults={assignDefaults} onSave={handleAssignCert} onClose={() => { setModal(null); setEditCert(null); setAssignDefaults(null) }} certFolderId={certFolderId} />}
      {modal === 'editCert' && editCert && <AssignCertModal pilots={pilots} certTypes={certTypes} existingCert={editCert} onSave={handleAssignCert} onRenew={handleRenewCert} onDelete={isSupervisor ? handleDeleteCert : null} onClose={() => { setModal(null); setEditCert(null) }} certFolderId={certFolderId} />}
      {modal && typeof modal === 'object' && modal.name && <CertTypeModal certType={modal} onSave={handleSaveCertType} onClose={() => setModal(null)} />}
      {bulkRenewOpen && (
        <Modal
          open
          onClose={() => setBulkRenewOpen(false)}
          title={`Renew ${selectedCerts.size} Certification${selectedCerts.size === 1 ? '' : 's'}`}
          className="max-w-md"
        >
            <p className="text-sm text-muted-foreground mb-4">
              Each selected certification is archived and replaced with a new record. Expiration is auto-calculated per certification type. Already-renewed certs are skipped.
            </p>
            <div className="space-y-3">
              <div>
                <label htmlFor="bulk-issue-date" className="block text-sm font-medium text-foreground mb-1">Issue date</label>
                <input id="bulk-issue-date" type="date" value={bulkIssueDate} onChange={e => setBulkIssueDate(e.target.value)}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
              <div>
                <label htmlFor="bulk-notes" className="block text-sm font-medium text-foreground mb-1">Notes (optional)</label>
                <input id="bulk-notes" type="text" value={bulkNotes} onChange={e => setBulkNotes(e.target.value)}
                  placeholder="e.g. Recurrent training day" className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
              </div>
            </div>
            <div className="flex gap-2 mt-4">
              <button onClick={handleBulkRenew} disabled={!bulkIssueDate || bulkRenewing}
                className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2">
                {bulkRenewing ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Renew All'}
              </button>
              <button onClick={() => setBulkRenewOpen(false)} className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm">Cancel</button>
            </div>
        </Modal>
      )}
      <ConfirmDialog {...confirmProps} />
    </div>
  )
}
