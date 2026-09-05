import { useState, useEffect, useCallback } from 'react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { useConfirm } from '@/hooks/useConfirm'
import { LogIn, LogOut, Trash2, PackageCheck } from 'lucide-react'

const TYPES = [
  { value: 'vehicle', label: 'Vehicle', endpoint: '/vehicles' },
  { value: 'battery', label: 'Battery', endpoint: '/batteries' },
  { value: 'controller', label: 'Controller', endpoint: '/controllers' },
  { value: 'dock', label: 'Dock', endpoint: '/docks' },
  { value: 'sensor', label: 'Sensor', endpoint: '/sensors' },
  { value: 'attachment', label: 'Attachment', endpoint: '/attachments' },
  { value: 'other', label: 'Other', endpoint: '/other-equipment' },
]

function itemLabel(type, it) {
  if (type === 'vehicle') {
    const base = `${it.manufacturer || ''} ${it.model || ''}`.trim()
    return it.nickname ? `${base} (${it.nickname})` : base || `vehicle #${it.id}`
  }
  if (type === 'battery' || type === 'controller') return it.nickname || it.serial_number || `${type} #${it.id}`
  return it.name || it.serial_number || `${type} #${it.id}`
}

const fmtDate = (s) => (s ? new Date(s).toLocaleDateString() : '—')

export default function CheckoutsPage() {
  const { user, isSupervisor } = useAuth()
  const toast = useToast()
  const [confirmProps, requestConfirm] = useConfirm()
  const [rows, setRows] = useState([])
  const [pilots, setPilots] = useState([])
  const [loading, setLoading] = useState(true)
  const [showReturned, setShowReturned] = useState(false)

  // Check Out modal
  const [coOpen, setCoOpen] = useState(false)
  const [coType, setCoType] = useState('vehicle')
  const [coItems, setCoItems] = useState([])
  const [coForm, setCoForm] = useState({ entity_id: '', checked_out_by_id: '', condition_out: 'good', expected_return: '', notes_out: '' })
  const [saving, setSaving] = useState(false)

  // Check In modal
  const [ciOpen, setCiOpen] = useState(false)
  const [ciTarget, setCiTarget] = useState(null)
  const [ciForm, setCiForm] = useState({ checked_in_by_id: '', condition_in: 'good', notes_in: '' })

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [co, pil] = await Promise.all([
        api.get('/equipment-checkouts').catch(() => []),
        api.get('/pilots').catch(() => []),
      ])
      setRows(Array.isArray(co) ? co : [])
      const plist = Array.isArray(pil) ? pil : (pil.pilots || [])
      setPilots(plist.filter(p => p.status === 'active'))
    } finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const active = rows.filter(r => !r.checked_in_at)
  const history = showReturned ? rows : rows.filter(r => !r.checked_in_at)

  const openCheckout = async () => {
    setCoType('vehicle')
    setCoForm({ entity_id: '', checked_out_by_id: user?.pilot_id ? String(user.pilot_id) : '', condition_out: 'good', expected_return: '', notes_out: '' })
    setCoOpen(true)
    loadItems('vehicle')
  }

  const loadItems = async (type) => {
    const t = TYPES.find(x => x.value === type)
    const data = await api.get(t.endpoint).catch(() => [])
    setCoItems(Array.isArray(data) ? data : (data.vehicles || data.items || []))
  }

  const onTypeChange = (type) => { setCoType(type); setCoForm(f => ({ ...f, entity_id: '' })); loadItems(type) }

  const submitCheckout = async (e) => {
    e.preventDefault()
    const item = coItems.find(i => String(i.id) === String(coForm.entity_id))
    if (!item || !coForm.checked_out_by_id) { toast.error('Pick an item and a pilot'); return }
    setSaving(true)
    try {
      await api.post('/equipment-checkouts', {
        entity_type: coType,
        entity_id: Number(coForm.entity_id),
        entity_name: itemLabel(coType, item),
        checked_out_by_id: Number(coForm.checked_out_by_id),
        condition_out: coForm.condition_out || undefined,
        expected_return: coForm.expected_return || undefined,
        notes_out: coForm.notes_out || undefined,
      })
      setCoOpen(false)
      load()
    } catch (err) {
      toast.error(err.message || 'Checkout failed')
    } finally { setSaving(false) }
  }

  const openCheckin = (row) => {
    setCiTarget(row)
    setCiForm({ checked_in_by_id: row.checked_out_by_id ? String(row.checked_out_by_id) : (user?.pilot_id ? String(user.pilot_id) : ''), condition_in: 'good', notes_in: '' })
    setCiOpen(true)
  }

  const submitCheckin = async (e) => {
    e.preventDefault()
    if (!ciForm.checked_in_by_id) { toast.error('Pick who returned it'); return }
    setSaving(true)
    try {
      await api.post(`/equipment-checkouts/${ciTarget.id}/checkin`, {
        checked_in_by_id: Number(ciForm.checked_in_by_id),
        condition_in: ciForm.condition_in || undefined,
        notes_in: ciForm.notes_in || undefined,
      })
      setCiOpen(false)
      load()
    } catch (err) { toast.error(err.message) } finally { setSaving(false) }
  }

  const handleDelete = (row) => {
    const label = row.entity_name || `${row.entity_type} #${row.entity_id}`
    requestConfirm({
      title: 'Delete checkout record',
      message: `Permanently delete this checkout record for ${label}?`,
      onConfirm: async () => {
        try { await api.delete(`/equipment-checkouts/${row.id}`); load() }
        catch (err) { toast.error(err.message) }
      },
    })
  }

  const pilotOptions = pilots.map(p => ({ id: p.id, name: `${p.first_name} ${p.last_name}` }))

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-semibold text-foreground flex items-center gap-2"><PackageCheck className="w-5 h-5 text-primary" /> Equipment Checkouts</h1>
        <Button onClick={openCheckout}><LogIn className="w-4 h-4 mr-1" /> Check Out</Button>
      </div>

      <section className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-border text-sm font-semibold text-foreground">Currently Out ({active.length})</div>
        {loading ? (
          <div className="p-4 text-sm text-muted-foreground">Loading…</div>
        ) : active.length === 0 ? (
          <div className="p-4 text-sm text-muted-foreground text-center">Nothing checked out.</div>
        ) : (
          <table className="w-full text-sm">
            <thead><tr className="text-left text-muted-foreground border-b border-border">
              <th className="px-4 py-2 font-medium">Equipment</th><th className="px-4 py-2 font-medium">Type</th>
              <th className="px-4 py-2 font-medium">Held by</th><th className="px-4 py-2 font-medium">Out</th>
              <th className="px-4 py-2 font-medium">Expected back</th><th className="px-4 py-2"></th>
            </tr></thead>
            <tbody className="divide-y divide-border">
              {active.map(r => (
                <tr key={r.id}>
                  <td className="px-4 py-2 text-foreground">{r.entity_name || `${r.entity_type} #${r.entity_id}`}</td>
                  <td className="px-4 py-2 text-muted-foreground capitalize">{r.entity_type}</td>
                  <td className="px-4 py-2 text-foreground">{r.checked_out_by_name || '—'}</td>
                  <td className="px-4 py-2 text-muted-foreground">{fmtDate(r.checked_out_at)}</td>
                  <td className="px-4 py-2 text-muted-foreground">{fmtDate(r.expected_return)}</td>
                  <td className="px-4 py-2 text-right">
                    <Button variant="secondary" size="sm" onClick={() => openCheckin(r)}><LogOut className="w-3.5 h-3.5 mr-1" /> Check In</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <span className="text-sm font-semibold text-foreground">History</span>
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
            <input type="checkbox" checked={showReturned} onChange={() => setShowReturned(v => !v)} /> Show returned
          </label>
        </div>
        {history.length === 0 ? (
          <div className="p-4 text-sm text-muted-foreground text-center">No records.</div>
        ) : (
          <table className="w-full text-sm">
            <thead><tr className="text-left text-muted-foreground border-b border-border">
              <th className="px-4 py-2 font-medium">Equipment</th><th className="px-4 py-2 font-medium">Held by</th>
              <th className="px-4 py-2 font-medium">Out</th><th className="px-4 py-2 font-medium">Returned</th>
              <th className="px-4 py-2 font-medium">By</th>{isSupervisor && <th className="px-4 py-2"></th>}
            </tr></thead>
            <tbody className="divide-y divide-border">
              {history.map(r => (
                <tr key={r.id}>
                  <td className="px-4 py-2 text-foreground">{r.entity_name || `${r.entity_type} #${r.entity_id}`}</td>
                  <td className="px-4 py-2 text-foreground">{r.checked_out_by_name || '—'}</td>
                  <td className="px-4 py-2 text-muted-foreground">{fmtDate(r.checked_out_at)}</td>
                  <td className="px-4 py-2 text-muted-foreground">{r.checked_in_at ? fmtDate(r.checked_in_at) : <span className="text-amber-500">Out</span>}</td>
                  <td className="px-4 py-2 text-muted-foreground">{r.checked_in_by_name || '—'}</td>
                  {isSupervisor && <td className="px-4 py-2 text-right"><button onClick={() => handleDelete(r)} className="text-muted-foreground hover:text-destructive"><Trash2 className="w-4 h-4" /></button></td>}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <Modal open={coOpen} onClose={() => setCoOpen(false)} title="Check Out Equipment">
        <form onSubmit={submitCheckout} className="space-y-3">
          <div>
            <label htmlFor="checkout-type" className="text-sm font-medium text-foreground">Type</label>
            <select id="checkout-type" className="flex h-10 w-full rounded-lg border border-border bg-secondary px-3 text-sm text-foreground" value={coType} onChange={e => onTypeChange(e.target.value)}>
              {TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="checkout-item" className="text-sm font-medium text-foreground">Item</label>
            <select id="checkout-item" className="flex h-10 w-full rounded-lg border border-border bg-secondary px-3 text-sm text-foreground" value={coForm.entity_id} onChange={e => setCoForm({ ...coForm, entity_id: e.target.value })} required>
              <option value="">Select…</option>
              {coItems.map(it => <option key={it.id} value={it.id}>{itemLabel(coType, it)}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="checkout-pilot" className="text-sm font-medium text-foreground">Pilot</label>
            <select id="checkout-pilot" className="flex h-10 w-full rounded-lg border border-border bg-secondary px-3 text-sm text-foreground" value={coForm.checked_out_by_id} onChange={e => setCoForm({ ...coForm, checked_out_by_id: e.target.value })} required>
              <option value="">Select…</option>
              {pilotOptions.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <Input label="Expected return (optional)" type="date" value={coForm.expected_return} onChange={e => setCoForm({ ...coForm, expected_return: e.target.value })} />
          <Input label="Notes (optional)" value={coForm.notes_out} onChange={e => setCoForm({ ...coForm, notes_out: e.target.value })} />
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="secondary" onClick={() => setCoOpen(false)}>Cancel</Button>
            <Button type="submit" disabled={saving}>Check Out</Button>
          </div>
        </form>
      </Modal>

      <Modal open={ciOpen} onClose={() => setCiOpen(false)} title="Check In Equipment">
        <form onSubmit={submitCheckin} className="space-y-3">
          <p className="text-sm text-muted-foreground">{ciTarget?.entity_name || `${ciTarget?.entity_type} #${ciTarget?.entity_id}`}</p>
          <div>
            <label htmlFor="checkin-returned-by" className="text-sm font-medium text-foreground">Returned by</label>
            <select id="checkin-returned-by" className="flex h-10 w-full rounded-lg border border-border bg-secondary px-3 text-sm text-foreground" value={ciForm.checked_in_by_id} onChange={e => setCiForm({ ...ciForm, checked_in_by_id: e.target.value })} required>
              <option value="">Select…</option>
              {pilotOptions.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <Input label="Notes (optional)" value={ciForm.notes_in} onChange={e => setCiForm({ ...ciForm, notes_in: e.target.value })} />
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="secondary" onClick={() => setCiOpen(false)}>Cancel</Button>
            <Button type="submit" disabled={saving}>Check In</Button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog {...confirmProps} />
    </div>
  )
}
