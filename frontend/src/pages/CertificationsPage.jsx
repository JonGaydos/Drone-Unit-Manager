import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { useConfirm } from '@/hooks/useConfirm'
import { normalizeDateValue } from '@/lib/utils'
import { CERT_STATUS_COLORS } from '@/lib/constants'
import { sortByName, sortPilotsActiveFirst } from '@/lib/formatters'
import { Plus, Edit, Trash2, ShieldCheck, Search, Filter, Download, ChevronLeft, ChevronRight, Loader2 } from 'lucide-react'
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
    else data.renewal_period_months = parseInt(data.renewal_period_months)
    setSaving(true)
    try { await onSave(data) } finally { setSaving(false) }
  }
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-xl p-6 w-full max-w-md shadow-xl" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-foreground mb-4">{certType ? 'Edit Certification Type' : 'Add Certification Type'}</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Name</label>
            <input type="text" value={form.name} onChange={e => setForm({...form, name: e.target.value})} required
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Category</label>
            <select value={form.category} onChange={e => setForm({...form, category: e.target.value})}
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
              <label className="block text-sm font-medium text-foreground mb-1">Renewal Period (months)</label>
              <input type="number" value={form.renewal_period_months || ''} onChange={e => setForm({...form, renewal_period_months: e.target.value})}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" placeholder="e.g. 24" />
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Description</label>
            <textarea value={form.description || ''} onChange={e => setForm({...form, description: e.target.value})}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm h-16 resize-none" />
          </div>
          <div className="flex gap-2 pt-2">
            <button type="submit" disabled={saving} className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : (certType ? 'Update' : 'Add')}
            </button>
            <button type="button" onClick={onClose} className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm">Cancel</button>
          </div>
        </form>
      </div>
    </div>
  )
}

function AssignCertModal({ pilots, certTypes, existingCert, onSave, onClose, certFolderId }) {
  const [form, setForm] = useState(existingCert ? {
    pilot_id: String(existingCert.pilot_id || ''),
    certification_type_id: String(existingCert.certification_type_id || ''),
    status: existingCert.status || 'not_started',
    issue_date: existingCert.issue_date || '',
    expiration_date: existingCert.expiration_date || '',
    certificate_number: existingCert.certificate_number || '',
    nist_level: existingCert.nist_level != null ? String(existingCert.nist_level) : '',
    notes: existingCert.notes || '',
  } : {
    pilot_id: '', certification_type_id: '', status: 'not_started', issue_date: '', expiration_date: '', certificate_number: '', nist_level: '', notes: ''
  })
  const isEditing = !!existingCert
  const [saving, setSaving] = useState(false)
  const handleSubmit = async (e) => {
    e.preventDefault()
    const data = { ...form }
    data.pilot_id = parseInt(data.pilot_id)
    data.certification_type_id = parseInt(data.certification_type_id)
    if (data.nist_level) data.nist_level = parseInt(data.nist_level)
    else data.nist_level = null
    Object.keys(data).forEach(k => { if (data[k] === '') delete data[k] })
    setSaving(true)
    try { await onSave(data, isEditing ? existingCert.id : null) } finally { setSaving(false) }
  }
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-xl p-6 w-full max-w-md shadow-xl" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-foreground mb-4">{isEditing ? 'Edit Certification' : 'Assign Certification'}</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Pilot</label>
            <select value={form.pilot_id} onChange={e => setForm({...form, pilot_id: e.target.value})} required
              disabled={isEditing}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm disabled:opacity-60">
              <option value="">Select pilot...</option>
              {sortPilotsActiveFirst(pilots).map(p => <option key={p.id} value={p.id}>{p.full_name}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Certification</label>
            <select value={form.certification_type_id} onChange={e => setForm({...form, certification_type_id: e.target.value})} required
              disabled={isEditing}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm disabled:opacity-60">
              <option value="">Select cert type...</option>
              {sortByName(certTypes, 'name').map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Status</label>
            <select value={form.status} onChange={e => setForm({...form, status: e.target.value})}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
              {Object.keys(CERT_STATUS_COLORS).map(s => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Issue Date</label>
              <input type="date" value={form.issue_date} onChange={e => setForm({...form, issue_date: e.target.value})}
                onBlur={e => { const n = normalizeDateValue(e.target.value); if (n !== e.target.value) setForm(prev => ({...prev, issue_date: n})) }}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Expiration Date</label>
              <input type="date" value={form.expiration_date} onChange={e => setForm({...form, expiration_date: e.target.value})}
                onBlur={e => { const n = normalizeDateValue(e.target.value); if (n !== e.target.value) setForm(prev => ({...prev, expiration_date: n})) }}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Certificate Number</label>
            <input type="text" value={form.certificate_number} onChange={e => setForm({...form, certificate_number: e.target.value})}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
          </div>
          <div className="flex gap-2 pt-2">
            <button type="submit" disabled={saving} className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2">{saving ? <Loader2 className="w-4 h-4 animate-spin" /> : (isEditing ? 'Update' : 'Assign')}</button>
            <button type="button" onClick={onClose} className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm">Cancel</button>
          </div>
        </form>
        {isEditing && existingCert?.id && (
          <div className="mt-4">
            <DocumentUpload entityType="certification" entityId={existingCert.id} folderId={certFolderId} />
          </div>
        )}
      </div>
    </div>
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
  const { isAdmin, isPilot, isSupervisor } = useAuth()
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
        try { setCertStatusLabels(JSON.parse(labels.value)) } catch {}
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
          <button onClick={() => setModal('assign')} className="flex items-center gap-2 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90">
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
                  <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>
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
                        <td key={ct.id} className="px-3 py-2 text-center cursor-pointer hover:bg-accent/40 transition-colors"
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
                              setModal('assign')
                            }
                          }}>
                          <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${CERT_STATUS_COLORS[status] || CERT_STATUS_COLORS.not_started}`}>
                            {certStatusLabels[status] || status.replace(/_/g, ' ')}
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
            <div key={ct.id} className="bg-card border border-border rounded-xl p-4">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <ShieldCheck className="w-5 h-5 text-primary" />
                  <h3 className="font-semibold text-foreground">{ct.name}</h3>
                </div>
                {isSupervisor && (
                  <div className="flex gap-1">
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
      {modal === 'assign' && <AssignCertModal pilots={pilots} certTypes={certTypes} onSave={handleAssignCert} onClose={() => { setModal(null); setEditCert(null) }} certFolderId={certFolderId} />}
      {modal === 'editCert' && editCert && <AssignCertModal pilots={pilots} certTypes={certTypes} existingCert={editCert} onSave={handleAssignCert} onClose={() => { setModal(null); setEditCert(null) }} certFolderId={certFolderId} />}
      {modal && typeof modal === 'object' && modal.name && <CertTypeModal certType={modal} onSave={handleSaveCertType} onClose={() => setModal(null)} />}
      <ConfirmDialog {...confirmProps} />
    </div>
  )
}
