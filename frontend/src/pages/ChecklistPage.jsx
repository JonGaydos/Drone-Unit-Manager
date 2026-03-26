import { useState, useEffect } from 'react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { useConfirm } from '@/hooks/useConfirm'
import {
  ClipboardList, Plus, X, Loader2, CheckCircle, XCircle,
  Trash2, Edit2, Eye, ChevronDown, Download,
} from 'lucide-react'
import { sortPilotsActiveFirst, vehicleDisplayName } from '@/lib/formatters'

// ─── Template Modal ──────────────────────────────────────────────

function TemplateModal({ template, vehicles, onSave, onClose }) {
  const [form, setForm] = useState({
    name: template?.name || '',
    description: template?.description || '',
    vehicle_model: template?.vehicle_model || '',
    items: template?.items?.length > 0
      ? template.items.map(i => ({ label: i.label, required: i.required ?? true }))
      : [{ label: '', required: true }],
  })
  const [saving, setSaving] = useState(false)

  const addItem = () => setForm({ ...form, items: [...form.items, { label: '', required: true }] })

  const removeItem = (idx) => {
    const items = form.items.filter((_, i) => i !== idx)
    setForm({ ...form, items: items.length > 0 ? items : [{ label: '', required: true }] })
  }

  const updateItem = (idx, field, value) => {
    const items = [...form.items]
    items[idx] = { ...items[idx], [field]: value }
    setForm({ ...form, items })
  }

  const moveItem = (idx, dir) => {
    const items = [...form.items]
    const newIdx = idx + dir
    if (newIdx < 0 || newIdx >= items.length) return
    ;[items[idx], items[newIdx]] = [items[newIdx], items[idx]]
    setForm({ ...form, items })
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.name.trim()) return
    const validItems = form.items.filter(i => i.label.trim())
    if (validItems.length === 0) return
    setSaving(true)
    try {
      await onSave({
        name: form.name,
        description: form.description || null,
        vehicle_model: form.vehicle_model || null,
        items: validItems,
      })
    } finally {
      setSaving(false)
    }
  }

  // Get unique vehicle models
  const models = [...new Set((vehicles || []).map(v => `${v.manufacturer} ${v.model}`).filter(Boolean))]

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-xl p-6 w-full max-w-2xl shadow-xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-foreground">
            {template ? 'Edit Template' : 'Create Checklist Template'}
          </h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="w-5 h-5" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Name *</label>
            <input
              type="text"
              value={form.name}
              onChange={e => setForm({ ...form, name: e.target.value })}
              placeholder="Pre-Flight Safety Checklist"
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Description</label>
            <textarea
              value={form.description}
              onChange={e => setForm({ ...form, description: e.target.value })}
              rows={2}
              placeholder="Standard pre-flight inspection checklist..."
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm resize-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Vehicle Model</label>
            <select
              value={form.vehicle_model}
              onChange={e => setForm({ ...form, vehicle_model: e.target.value })}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm"
            >
              <option value="">All models</option>
              {models.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>

          {/* Checklist Items Builder */}
          <div>
            <label className="block text-sm font-medium text-foreground mb-2">
              Checklist Items *
            </label>
            <div className="space-y-2">
              {form.items.map((item, idx) => (
                <div key={idx} className="flex items-center gap-2 bg-secondary/50 border border-border rounded-lg p-2">
                  <div className="flex flex-col gap-0.5">
                    <button type="button" onClick={() => moveItem(idx, -1)} className="text-muted-foreground hover:text-foreground" disabled={idx === 0}>
                      <ChevronDown className="w-3 h-3 rotate-180" />
                    </button>
                    <button type="button" onClick={() => moveItem(idx, 1)} className="text-muted-foreground hover:text-foreground" disabled={idx === form.items.length - 1}>
                      <ChevronDown className="w-3 h-3" />
                    </button>
                  </div>
                  <input
                    type="text"
                    value={item.label}
                    onChange={e => updateItem(idx, 'label', e.target.value)}
                    placeholder={`Item ${idx + 1}...`}
                    className="flex-1 px-2 py-1.5 bg-secondary border border-border rounded text-foreground text-sm"
                  />
                  <label className="flex items-center gap-1.5 text-xs text-muted-foreground whitespace-nowrap cursor-pointer">
                    <input
                      type="checkbox"
                      checked={item.required}
                      onChange={e => updateItem(idx, 'required', e.target.checked)}
                      className="rounded border-border"
                    />
                    Required
                  </label>
                  <button type="button" onClick={() => removeItem(idx)} className="text-muted-foreground hover:text-red-400 p-1">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
            <button
              type="button"
              onClick={addItem}
              className="mt-2 flex items-center gap-1 text-sm text-primary hover:text-primary/80"
            >
              <Plus className="w-4 h-4" /> Add Item
            </button>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground border border-border rounded-lg">
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 text-sm bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2"
            >
              {saving && <Loader2 className="w-4 h-4 animate-spin" />}
              {template ? 'Update' : 'Create'} Template
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ─── Complete Checklist Modal ────────────────────────────────────

function CompleteModal({ templates, pilots, vehicles, onSave, onClose }) {
  const [templateId, setTemplateId] = useState('')
  const [selectedTemplate, setSelectedTemplate] = useState(null)
  const [form, setForm] = useState({
    pilot_id: '',
    vehicle_id: '',
    notes: '',
  })
  const [responses, setResponses] = useState([])
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (templateId) {
      const t = templates.find(t => t.id === parseInt(templateId))
      setSelectedTemplate(t)
      setResponses((t?.items || []).map(item => ({
        label: item.label,
        checked: false,
        notes: '',
        required: item.required,
      })))
    } else {
      setSelectedTemplate(null)
      setResponses([])
    }
  }, [templateId, templates])

  const toggleResponse = (idx) => {
    const newResp = [...responses]
    newResp[idx] = { ...newResp[idx], checked: !newResp[idx].checked }
    setResponses(newResp)
  }

  const updateResponseNote = (idx, notes) => {
    const newResp = [...responses]
    newResp[idx] = { ...newResp[idx], notes }
    setResponses(newResp)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!templateId || !form.pilot_id) return
    setSaving(true)
    try {
      await onSave({
        template_id: parseInt(templateId),
        pilot_id: parseInt(form.pilot_id),
        vehicle_id: form.vehicle_id ? parseInt(form.vehicle_id) : null,
        responses: responses.map(r => ({ label: r.label, checked: r.checked, notes: r.notes })),
        notes: form.notes || null,
      })
    } finally {
      setSaving(false)
    }
  }

  const allRequiredChecked = responses.filter(r => r.required).every(r => r.checked)

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-xl p-6 w-full max-w-2xl shadow-xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-foreground">Complete Pre-Flight Checklist</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="w-5 h-5" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Template *</label>
              <select
                value={templateId}
                onChange={e => setTemplateId(e.target.value)}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm"
                required
              >
                <option value="">Select template...</option>
                {templates.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Pilot *</label>
              <select
                value={form.pilot_id}
                onChange={e => setForm({ ...form, pilot_id: e.target.value })}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm"
                required
              >
                <option value="">Select pilot...</option>
                {sortPilotsActiveFirst(pilots).map(p => <option key={p.id} value={p.id}>{p.first_name} {p.last_name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Vehicle</label>
              <select
                value={form.vehicle_id}
                onChange={e => setForm({ ...form, vehicle_id: e.target.value })}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm"
              >
                <option value="">Select vehicle...</option>
                {vehicles.map(v => (
                  <option key={v.id} value={v.id}>
                    {vehicleDisplayName(v)}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {selectedTemplate && (
            <>
              {selectedTemplate.description && (
                <p className="text-sm text-muted-foreground bg-secondary/50 p-3 rounded-lg">{selectedTemplate.description}</p>
              )}

              {/* Checklist Items */}
              <div className="space-y-1">
                {responses.map((resp, idx) => (
                  <div key={idx} className={`border rounded-lg p-3 transition-colors ${resp.checked ? 'bg-emerald-500/5 border-emerald-500/30' : 'bg-secondary/30 border-border'}`}>
                    <div className="flex items-start gap-3">
                      <button
                        type="button"
                        onClick={() => toggleResponse(idx)}
                        className={`mt-0.5 shrink-0 w-5 h-5 rounded border-2 flex items-center justify-center transition-colors ${
                          resp.checked
                            ? 'bg-emerald-500 border-emerald-500 text-white'
                            : 'border-border hover:border-primary'
                        }`}
                      >
                        {resp.checked && <CheckCircle className="w-3.5 h-3.5" />}
                      </button>
                      <div className="flex-1">
                        <span className={`text-sm ${resp.checked ? 'text-foreground' : 'text-foreground'}`}>
                          {resp.label}
                          {resp.required && <span className="text-red-400 ml-1">*</span>}
                        </span>
                        <input
                          type="text"
                          value={resp.notes}
                          onChange={e => updateResponseNote(idx, e.target.value)}
                          placeholder="Notes (optional)"
                          className="w-full mt-1.5 px-2 py-1 bg-secondary border border-border rounded text-xs text-foreground"
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {!allRequiredChecked && (
                <div className="flex items-center gap-2 text-amber-400 text-sm bg-amber-500/10 border border-amber-500/30 rounded-lg p-3">
                  <XCircle className="w-4 h-4 shrink-0" />
                  Some required items are not checked
                </div>
              )}
            </>
          )}

          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Overall Notes</label>
            <textarea
              value={form.notes}
              onChange={e => setForm({ ...form, notes: e.target.value })}
              rows={2}
              placeholder="Any additional notes..."
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm resize-none"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground border border-border rounded-lg">
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving || !templateId || !form.pilot_id}
              className="px-4 py-2 text-sm bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2"
            >
              {saving && <Loader2 className="w-4 h-4 animate-spin" />}
              Submit Checklist
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ─── View Completion Modal ───────────────────────────────────────

function ViewCompletionModal({ completion, onClose }) {
  if (!completion) return null

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-xl p-6 w-full max-w-lg shadow-xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-foreground">Checklist Details</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="space-y-3 text-sm">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <span className="text-muted-foreground">Template:</span>
              <p className="font-medium text-foreground">{completion.template_name}</p>
            </div>
            <div>
              <span className="text-muted-foreground">Date:</span>
              <p className="font-medium text-foreground">
                {completion.completed_at ? new Date(completion.completed_at).toLocaleString() : '-'}
              </p>
            </div>
            <div>
              <span className="text-muted-foreground">Pilot:</span>
              <p className="font-medium text-foreground">{completion.pilot_name || '-'}</p>
            </div>
            <div>
              <span className="text-muted-foreground">Vehicle:</span>
              <p className="font-medium text-foreground">{completion.vehicle_name || '-'}</p>
            </div>
          </div>

          <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${
            completion.all_passed
              ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
              : 'bg-red-500/15 text-red-400 border-red-500/30'
          }`}>
            {completion.all_passed ? <CheckCircle className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
            {completion.all_passed ? 'All Passed' : 'Items Failed'}
          </div>

          <div className="space-y-1.5 mt-3">
            {(completion.responses || []).map((r, i) => (
              <div key={i} className={`flex items-start gap-2 p-2 rounded-lg ${r.checked ? 'bg-emerald-500/5' : 'bg-red-500/5'}`}>
                {r.checked
                  ? <CheckCircle className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
                  : <XCircle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
                }
                <div>
                  <span className="text-foreground">{r.label}</span>
                  {r.notes && <p className="text-xs text-muted-foreground mt-0.5">{r.notes}</p>}
                </div>
              </div>
            ))}
          </div>

          {completion.notes && (
            <div className="mt-3">
              <span className="text-muted-foreground">Notes:</span>
              <p className="text-foreground mt-1">{completion.notes}</p>
            </div>
          )}
        </div>

        <div className="flex justify-end mt-4">
          <button onClick={onClose} className="px-4 py-2 text-sm border border-border rounded-lg text-muted-foreground hover:text-foreground">
            Close
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Main Page ───────────────────────────────────────────────────

export default function ChecklistPage() {
  const [tab, setTab] = useState('templates')
  const [templates, setTemplates] = useState([])
  const [completions, setCompletions] = useState([])
  const [pilots, setPilots] = useState([])
  const [vehicles, setVehicles] = useState([])
  const [loading, setLoading] = useState(true)
  const [showTemplateModal, setShowTemplateModal] = useState(false)
  const [editingTemplate, setEditingTemplate] = useState(null)
  const [showCompleteModal, setShowCompleteModal] = useState(false)
  const [viewCompletion, setViewCompletion] = useState(null)
  const { isSupervisor, isPilot } = useAuth()
  const toast = useToast()
  const [confirmProps, requestConfirm] = useConfirm()

  const load = async () => {
    setLoading(true)
    try {
      const [tpl, comp, p, v] = await Promise.all([
        api.get('/checklists/templates'),
        api.get('/checklists/completions'),
        api.get('/pilots'),
        api.get('/vehicles'),
      ])
      setTemplates(tpl)
      setCompletions(comp)
      setPilots(Array.isArray(p) ? p : p.pilots || p.items || [])
      setVehicles(Array.isArray(v) ? v : v.vehicles || v.items || [])
    } catch (err) {
      toast.error(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleSaveTemplate = async (data) => {
    try {
      if (editingTemplate) {
        await api.patch(`/checklists/templates/${editingTemplate.id}`, data)
        toast.success('Template updated')
      } else {
        await api.post('/checklists/templates', data)
        toast.success('Template created')
      }
      setShowTemplateModal(false)
      setEditingTemplate(null)
      await load()
    } catch (err) {
      toast.error(err.message)
    }
  }

  const handleDeleteTemplate = (id) => {
    requestConfirm({
      title: 'Delete Template',
      message: 'Delete this template?',
      onConfirm: async () => {
        try {
          await api.delete(`/checklists/templates/${id}`)
          toast.success('Template deleted')
          load()
        } catch (err) {
          toast.error(err.message)
        }
      }
    })
  }

  const handleComplete = async (data) => {
    try {
      await api.post('/checklists/complete', data)
      toast.success('Checklist submitted')
      setShowCompleteModal(false)
      setTab('completions')
      await load()
    } catch (err) {
      toast.error(err.message)
    }
  }

  return (
    <div className="p-4 md:p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <ClipboardList className="w-7 h-7 text-primary" />
          <h1 className="text-2xl font-bold text-foreground">Pre-Flight Checklists</h1>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => api.download('/export/checklists/csv')}
            className="flex items-center gap-2 px-3 py-2 text-sm bg-secondary border border-border text-secondary-foreground rounded-lg hover:bg-secondary/80"
          >
            <Download className="w-4 h-4" />
            Export CSV
          </button>
          {isPilot && (
            <button
              onClick={() => setShowCompleteModal(true)}
              className="flex items-center gap-2 px-3 py-2 text-sm bg-primary text-primary-foreground rounded-lg hover:bg-primary/90"
            >
              <CheckCircle className="w-4 h-4" />
              Complete Checklist
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-secondary/50 p-1 rounded-lg w-fit">
        <button
          onClick={() => setTab('templates')}
          className={`px-4 py-2 text-sm rounded-md transition-colors ${
            tab === 'templates' ? 'bg-card text-foreground shadow-sm font-medium' : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          Templates
        </button>
        <button
          onClick={() => setTab('completions')}
          className={`px-4 py-2 text-sm rounded-md transition-colors ${
            tab === 'completions' ? 'bg-card text-foreground shadow-sm font-medium' : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          Completions
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-40">
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
        </div>
      ) : tab === 'templates' ? (
        /* ── Templates Tab ──────────────────────────── */
        <div className="space-y-4">
          {isSupervisor && (
            <div className="flex justify-end">
              <button
                onClick={() => { setEditingTemplate(null); setShowTemplateModal(true) }}
                className="flex items-center gap-2 px-3 py-2 text-sm bg-secondary border border-border rounded-lg text-foreground hover:bg-secondary/80"
              >
                <Plus className="w-4 h-4" /> Create Template
              </button>
            </div>
          )}

          {templates.length === 0 ? (
            <div className="bg-card border border-border rounded-xl p-8 text-center text-muted-foreground">
              <ClipboardList className="w-10 h-10 mx-auto mb-3 opacity-50" />
              <p className="font-medium text-foreground">No Templates Yet</p>
              <p className="text-sm mt-1">Create a checklist template to get started.</p>
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {templates.map(t => (
                <div key={t.id} className="bg-card border border-border rounded-xl p-4 hover:border-primary/30 transition-colors">
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="font-medium text-foreground">{t.name}</h3>
                      {t.vehicle_model && (
                        <span className="text-xs text-muted-foreground">{t.vehicle_model}</span>
                      )}
                    </div>
                    {isSupervisor && (
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => { setEditingTemplate(t); setShowTemplateModal(true) }}
                          className="p-1.5 text-muted-foreground hover:text-foreground"
                          aria-label="Edit"
                        >
                          <Edit2 className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleDeleteTemplate(t.id)}
                          className="p-1.5 text-muted-foreground hover:text-red-400"
                          aria-label="Delete"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    )}
                  </div>
                  {t.description && (
                    <p className="text-xs text-muted-foreground mt-2 line-clamp-2">{t.description}</p>
                  )}
                  <div className="flex items-center gap-2 mt-3 text-xs text-muted-foreground">
                    <span className="bg-secondary px-2 py-0.5 rounded">{(t.items || []).length} items</span>
                    {!t.is_active && (
                      <span className="bg-amber-500/15 text-amber-400 px-2 py-0.5 rounded">Inactive</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        /* ── Completions Tab ────────────────────────── */
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          {completions.length === 0 ? (
            <div className="p-8 text-center text-muted-foreground">
              <CheckCircle className="w-10 h-10 mx-auto mb-3 opacity-50" />
              <p className="font-medium text-foreground">No Completions Yet</p>
              <p className="text-sm mt-1">Complete a checklist to see history here.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-secondary/50">
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">Date</th>
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">Pilot</th>
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">Vehicle</th>
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">Template</th>
                    <th className="px-4 py-3 text-center font-medium text-muted-foreground">Passed</th>
                    <th className="px-4 py-3 text-center font-medium text-muted-foreground">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {completions.map(c => (
                    <tr key={c.id} className="hover:bg-secondary/30 transition-colors">
                      <td className="px-4 py-3 text-foreground">
                        {c.completed_at ? new Date(c.completed_at).toLocaleDateString() : '-'}
                      </td>
                      <td className="px-4 py-3 text-foreground">{c.pilot_name || '-'}</td>
                      <td className="px-4 py-3 text-foreground">{c.vehicle_name || '-'}</td>
                      <td className="px-4 py-3 text-foreground">{c.template_name || '-'}</td>
                      <td className="px-4 py-3 text-center">
                        {c.all_passed ? (
                          <span className="inline-flex items-center gap-1 text-emerald-400">
                            <CheckCircle className="w-4 h-4" />
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-red-400">
                            <XCircle className="w-4 h-4" />
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <button
                          onClick={() => setViewCompletion(c)}
                          className="p-1.5 text-muted-foreground hover:text-primary"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Modals */}
      {showTemplateModal && (
        <TemplateModal
          template={editingTemplate}
          vehicles={vehicles}
          onSave={handleSaveTemplate}
          onClose={() => { setShowTemplateModal(false); setEditingTemplate(null) }}
        />
      )}
      {showCompleteModal && (
        <CompleteModal
          templates={templates}
          pilots={pilots}
          vehicles={vehicles}
          onSave={handleComplete}
          onClose={() => setShowCompleteModal(false)}
        />
      )}
      {viewCompletion && (
        <ViewCompletionModal
          completion={viewCompletion}
          onClose={() => setViewCompletion(null)}
        />
      )}
      <ConfirmDialog {...confirmProps} />
    </div>
  )
}
