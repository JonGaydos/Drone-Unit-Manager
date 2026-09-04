# Checkouts Page + UX Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A dedicated all-equipment Checkouts page (replacing the checkout UI on Vehicle Detail), plus six small UX-polish fixes.

**Architecture:** Frontend-only. The `equipment-checkouts` API already supports everything; the page consumes it. No backend changes.

**Tech Stack:** React 19 + Vite. Verify with `npm run build` + `eslint` (no test framework).

**Branch:** `feat/checkouts-and-polish` off `main`.

**Conventions (verified):** api client paths omit `/api` (base already includes it). Equipment list endpoints: `/vehicles`, `/batteries`, `/controllers`, `/docks`, `/sensors`, `/attachments`. Display label: vehicles → `nickname ? "{mfr} {model} ({nickname})" : "{mfr} {model}"`; batteries/controllers → `nickname || serial_number`; docks/sensors/attachments → `name || serial_number`. `useToast()` returns the toast object (`const toast = useToast()`). `useConfirm()` → `[confirmProps, requestConfirm]`, callback-style: `requestConfirm({title,message,confirmLabel,confirmVariant,onConfirm})`, render `<ConfirmDialog {...confirmProps}/>`. Shared `Modal({open,onClose,title,children})`, `Button({variant,size})`, `Input({label,...})`.

---

### Task 0: Branch
- [ ] **Step 1**
```bash
git -C "D:/Claude Projects/Drone-Unit-Manager" checkout main && git -C "D:/Claude Projects/Drone-Unit-Manager" pull --ff-only && git -C "D:/Claude Projects/Drone-Unit-Manager" checkout -b feat/checkouts-and-polish
```

---

### Task 1: CheckoutsPage

**Files:** Create `frontend/src/pages/CheckoutsPage.jsx`

- [ ] **Step 1: Create the page**
```jsx
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
    requestConfirm({
      title: 'Delete checkout record',
      message: `Permanently delete this checkout record for ${row.entity_name || `${row.entity_type} #${row.entity_id}`}?`,
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
            <label className="text-sm font-medium text-foreground">Type</label>
            <select className="flex h-10 w-full rounded-lg border border-border bg-secondary px-3 text-sm text-foreground" value={coType} onChange={e => onTypeChange(e.target.value)}>
              {TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
          <div>
            <label className="text-sm font-medium text-foreground">Item</label>
            <select className="flex h-10 w-full rounded-lg border border-border bg-secondary px-3 text-sm text-foreground" value={coForm.entity_id} onChange={e => setCoForm({ ...coForm, entity_id: e.target.value })} required>
              <option value="">Select…</option>
              {coItems.map(it => <option key={it.id} value={it.id}>{itemLabel(coType, it)}</option>)}
            </select>
          </div>
          <div>
            <label className="text-sm font-medium text-foreground">Pilot</label>
            <select className="flex h-10 w-full rounded-lg border border-border bg-secondary px-3 text-sm text-foreground" value={coForm.checked_out_by_id} onChange={e => setCoForm({ ...coForm, checked_out_by_id: e.target.value })} required>
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
            <label className="text-sm font-medium text-foreground">Returned by</label>
            <select className="flex h-10 w-full rounded-lg border border-border bg-secondary px-3 text-sm text-foreground" value={ciForm.checked_in_by_id} onChange={e => setCiForm({ ...ciForm, checked_in_by_id: e.target.value })} required>
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
```

- [ ] **Step 2: Build + lint**
```bash
cd "D:/Claude Projects/Drone-Unit-Manager/frontend" && npm run build && npx eslint src/pages/CheckoutsPage.jsx
```
Expected: build OK; remove any genuinely unused var eslint flags.

- [ ] **Step 3: Commit**
```bash
git -C "D:/Claude Projects/Drone-Unit-Manager" add frontend/src/pages/CheckoutsPage.jsx && git -C "D:/Claude Projects/Drone-Unit-Manager" commit -m "feat(checkouts): dedicated all-equipment Checkouts page"
```

---

### Task 2: Route, sidebar, NotFound page

**Files:** Create `frontend/src/pages/NotFoundPage.jsx`; Modify `frontend/src/App.jsx`, `frontend/src/components/layout/Sidebar.jsx`

- [ ] **Step 1: NotFoundPage**
```jsx
import { Link } from 'react-router-dom'

export default function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <p className="text-5xl font-bold text-foreground">404</p>
      <p className="mt-2 text-muted-foreground">That page doesn't exist.</p>
      <Link to="/" className="mt-4 text-primary hover:underline">Back to dashboard</Link>
    </div>
  )
}
```

- [ ] **Step 2: App.jsx — lazy imports + route + catch-all**

Add near the other lazy imports (by `ReportsPage`, line ~60):
```jsx
const CheckoutsPage = lazy(() => import('@/pages/CheckoutsPage'))
const NotFoundPage = lazy(() => import('@/pages/NotFoundPage'))
```
Add inside the protected `<Route element={<ProtectedRoute><Layout/></ProtectedRoute>}>` block (near `/manual`):
```jsx
          <Route path="/checkouts" element={<CheckoutsPage />} />
```
Replace the catch-all (line 173) `<Route path="*" element={<Navigate to="/" replace />} />` with:
```jsx
        <Route path="*" element={<NotFoundPage />} />
```
(Keep the `Navigate` import — still used by the auth guards.)

- [ ] **Step 3: Sidebar entry**

In `Sidebar.jsx`, add `PackageCheck` to the `lucide-react` import, and add to `navItems` (in the `'Fleet & Crew'` group):
```jsx
  { to: '/checkouts', icon: PackageCheck, label: 'Checkouts', group: 'Fleet & Crew' },
```

- [ ] **Step 4: Build + lint + commit**
```bash
cd "D:/Claude Projects/Drone-Unit-Manager/frontend" && npm run build && npx eslint src/App.jsx src/components/layout/Sidebar.jsx src/pages/NotFoundPage.jsx
git -C "D:/Claude Projects/Drone-Unit-Manager" add frontend/src/App.jsx frontend/src/components/layout/Sidebar.jsx frontend/src/pages/NotFoundPage.jsx && git -C "D:/Claude Projects/Drone-Unit-Manager" commit -m "feat(checkouts): route + sidebar entry + NotFound page"
```

---

### Task 3: Remove checkout section from VehicleDetailPage

**Files:** Modify `frontend/src/pages/VehicleDetailPage.jsx`

- [ ] **Step 1: Delete the checkout state (lines 37-43)** — remove these seven `useState` lines:
```jsx
  const [checkouts, setCheckouts] = useState([])
  const [activeCheckout, setActiveCheckout] = useState(null)
  const [pilots, setPilots] = useState([])
  const [showCheckoutForm, setShowCheckoutForm] = useState(false)
  const [checkoutForm, setCheckoutForm] = useState({ pilot_id: '', condition_out: 'good', notes_out: '' })
  const [checkinForm, setCheckinForm] = useState({ condition_in: 'good', notes_in: '' })
  const [showCheckinForm, setShowCheckinForm] = useState(false)
```

- [ ] **Step 2: Delete `loadCheckouts` (lines 72-77)** entirely.

- [ ] **Step 3: Fix the main load Promise.all.** Remove the two array entries (lines 90-91):
```jsx
      api.get(`/equipment-checkouts?entity_type=vehicle&entity_id=${id}`).catch(() => []),
      api.get('/pilots').catch(() => []),
```
Change the destructure (line 93) from `([v, s, fData, bat, ctrl, sens, att, maint, regs, chk, pil, comp])` to `([v, s, fData, bat, ctrl, sens, att, maint, regs, comp])` and remove the setter lines (103-105):
```jsx
      setCheckouts(chk)
      setActiveCheckout(chk.find(c => !c.checked_in_at) || null)
      setPilots(Array.isArray(pil) ? pil : (pil.pilots || []))
```
(Verify the remaining destructured names still line up with the remaining Promise.all entries after removing the two — `comp` must remain the last.)

- [ ] **Step 4: Delete the entire "Equipment Checkout Status" JSX block (lines 677-904)** — the single `<div>` from the `{/* Equipment Checkout Status */}` comment through its closing `</div>` immediately before `{/* Components */}`.

- [ ] **Step 5: Remove now-unused imports** — drop `LogIn`, `LogOut`, `User` from the `lucide-react` import (they were used only in the deleted block). Keep all others.

- [ ] **Step 6: Build + lint** (eslint will catch any missed reference — fix until clean):
```bash
cd "D:/Claude Projects/Drone-Unit-Manager/frontend" && npm run build && npx eslint src/pages/VehicleDetailPage.jsx
```
Expected: build OK, no `no-undef`/`no-unused-vars` from the removal.

- [ ] **Step 7: Commit**
```bash
git -C "D:/Claude Projects/Drone-Unit-Manager" add frontend/src/pages/VehicleDetailPage.jsx && git -C "D:/Claude Projects/Drone-Unit-Manager" commit -m "refactor(fleet): remove checkout UI from Vehicle Detail (moved to Checkouts page)"
```

---

### Task 4: DataTable loading skeleton

**Files:** Modify `frontend/src/components/ui/DataTable.jsx`

- [ ] **Step 1: Add a `loading` prop + skeleton rows.** Add `loading = false,` to the props destructure (after `data = [],`). Replace the body conditional (lines 91-114) so that when `loading` is true it renders ~5 skeleton rows:
```jsx
          <tbody className="divide-y divide-border">
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={`sk-${i}`}>
                  {columns.map((col) => (
                    <td key={col.key} className="px-4 py-3"><div className="skeleton h-4 w-3/4" /></td>
                  ))}
                </tr>
              ))
            ) : data.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-4 py-8 text-center text-muted-foreground">No data available</td>
              </tr>
            ) : (
              data.map((row, idx) => (
                <tr key={idx} className="hover:bg-accent/30 transition-colors">
                  {columns.map((col) => (
                    <td key={col.key} className="px-4 py-3 text-foreground">
                      {col.render ? col.render(row[col.key], row) : row[col.key]}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
```
(Match the existing `<tr>`/`<td>` classes exactly — copy them from the current file; the `data.map` branch above must reproduce the current markup verbatim.)

- [ ] **Step 2: Build + lint + commit**
```bash
cd "D:/Claude Projects/Drone-Unit-Manager/frontend" && npm run build && npx eslint src/components/ui/DataTable.jsx
git -C "D:/Claude Projects/Drone-Unit-Manager" add frontend/src/components/ui/DataTable.jsx && git -C "D:/Claude Projects/Drone-Unit-Manager" commit -m "feat(ui): DataTable loading skeleton rows"
```
(Backward-compatible: `loading` defaults false, existing callers unaffected.)

---

### Task 5: Sticky Settings save bar

**Files:** Modify `frontend/src/pages/SettingsPage.jsx`

- [ ] **Step 1: Make the Save bar sticky when dirty.** Replace the Save block (lines 901-913) so the wrapper sticks to the bottom and reflects dirty state:
```jsx
      {/* Save */}
      {isAdmin && (
        <div className={`sticky bottom-4 z-10 flex items-center gap-3 ${hasUnsavedChanges ? 'bg-card border border-border rounded-lg p-3 shadow-lg' : ''}`}>
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 px-6 py-2.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Save Settings
          </button>
          {hasUnsavedChanges && <span className="text-xs text-amber-500">Unsaved changes</span>}
        </div>
      )}
```
(Note: `hasUnsavedChanges` only tracks the general `field()` inputs, so the "Unsaved changes" hint reflects those, not the per-section saves — acceptable.)

- [ ] **Step 2: Build + lint + commit**
```bash
cd "D:/Claude Projects/Drone-Unit-Manager/frontend" && npm run build && npx eslint src/pages/SettingsPage.jsx
git -C "D:/Claude Projects/Drone-Unit-Manager" add frontend/src/pages/SettingsPage.jsx && git -C "D:/Claude Projects/Drone-Unit-Manager" commit -m "feat(settings): sticky save bar with unsaved-changes hint"
```

---

### Task 6: Richer Integrations sync status

**Files:** Modify `frontend/src/pages/IntegrationsPage.jsx`

- [ ] **Step 1: Surface interval + provider alongside last-sync.** Replace the syncStatus display (lines 235-239) with:
```jsx
            {syncStatus?.last_sync && (
              <span className="text-[10px] text-muted-foreground">
                Last sync: {new Date(syncStatus.last_sync).toLocaleString()}
                {syncStatus.provider ? ` · ${syncStatus.provider}` : ''}
                {syncStatus.sync_interval ? ` · every ${syncStatus.sync_interval} min` : ''}
              </span>
            )}
```
- [ ] **Step 2: Show the last sync result inline.** `handleSync` already receives a result it toasts; also store it. Add state near the other `useState`s in the provider card: `const [lastResult, setLastResult] = useState(null)`. In `handleSync`, after the POST resolves to `res`, add `setLastResult(res)`. Below the last-sync line, render:
```jsx
            {lastResult && (
              <span className="text-[10px] text-muted-foreground">
                Last run: {[lastResult.created != null ? `${lastResult.created} new` : null, lastResult.updated != null ? `${lastResult.updated} updated` : null, lastResult.errors ? `${lastResult.errors} errors` : null].filter(Boolean).join(', ') || 'done'}
              </span>
            )}
```
(Adjust the field names to whatever `/sync/now` actually returns — inspect `handleSync`'s `res` shape; if it returns a `message`, show that instead. Persistent last-error is NOT available from `/sync/status` and is out of scope.)

- [ ] **Step 3: Build + lint + commit**
```bash
cd "D:/Claude Projects/Drone-Unit-Manager/frontend" && npm run build && npx eslint src/pages/IntegrationsPage.jsx
git -C "D:/Claude Projects/Drone-Unit-Manager" add frontend/src/pages/IntegrationsPage.jsx && git -C "D:/Claude Projects/Drone-Unit-Manager" commit -m "feat(integrations): richer sync status (provider, interval, last result)"
```

---

### Task 7: Reports remember-last-config

**Files:** Modify `frontend/src/pages/ReportsPage.jsx`

- [ ] **Step 1: Persist config on generate.** In `handleGenerate` (after building `config`, before the POST) add:
```jsx
      try {
        localStorage.setItem('dum_report_config', JSON.stringify({ reportType, dateFrom, dateTo, selectedPilots, selectedVehicles }))
      } catch { /* ignore quota */ }
```
- [ ] **Step 2: Hydrate on mount.** In the load `useEffect` (lines 39-53), after the existing fetches, add:
```jsx
    try {
      const saved = JSON.parse(localStorage.getItem('dum_report_config') || 'null')
      if (saved) {
        if (saved.reportType) setReportType(saved.reportType)
        if (saved.dateFrom) setDateFrom(saved.dateFrom)
        if (saved.dateTo) setDateTo(saved.dateTo)
        if (Array.isArray(saved.selectedPilots)) setSelectedPilots(saved.selectedPilots)
        if (Array.isArray(saved.selectedVehicles)) setSelectedVehicles(saved.selectedVehicles)
      }
    } catch { /* ignore */ }
```
- [ ] **Step 3: Build + lint + commit**
```bash
cd "D:/Claude Projects/Drone-Unit-Manager/frontend" && npm run build && npx eslint src/pages/ReportsPage.jsx
git -C "D:/Claude Projects/Drone-Unit-Manager" add frontend/src/pages/ReportsPage.jsx && git -C "D:/Claude Projects/Drone-Unit-Manager" commit -m "feat(reports): remember last report config in localStorage"
```

---

### Task 8: Fix broken currency-rule delete confirm

**Files:** Modify `frontend/src/pages/SettingsPage.jsx` (`handleDeleteRule`, lines 263-278)

The current handler `await`s `requestConfirm` (which returns nothing) and passes `confirmText`/`danger` (wrong keys), so the delete never runs. Rewrite it to the callback contract.

- [ ] **Step 1: Rewrite `handleDeleteRule`** to:
```jsx
  const handleDeleteRule = (ruleId) => {
    requestConfirm({
      title: 'Delete currency rule',
      message: 'Delete this currency rule? This cannot be undone.',
      confirmLabel: 'Delete',
      confirmVariant: 'danger',
      onConfirm: async () => {
        try {
          await api.delete(`/currency/rules/${ruleId}`)
          setCurrencyRules(prev => prev.filter(r => r.id !== ruleId))
          toast.success('Rule deleted')
        } catch (err) { toast.error(err.message) }
      },
    })
  }
```
(Confirm the delete endpoint path + the rules state setter name against the current file before finalizing; match them exactly.)

- [ ] **Step 2: Build + lint + commit**
```bash
cd "D:/Claude Projects/Drone-Unit-Manager/frontend" && npm run build && npx eslint src/pages/SettingsPage.jsx
git -C "D:/Claude Projects/Drone-Unit-Manager" add frontend/src/pages/SettingsPage.jsx && git -C "D:/Claude Projects/Drone-Unit-Manager" commit -m "fix(settings): repair currency-rule delete confirm (useConfirm contract)"
```

---

### Task 9: Final verification + live retest

- [ ] **Step 1: Whole frontend build + eslint sweep**
```bash
cd "D:/Claude Projects/Drone-Unit-Manager/frontend" && npm run build && npx eslint src
```
Expected: clean build; only the repo's pre-existing eslint baseline (no NEW errors from these changes).

- [ ] **Step 2: Live retest (after deploy):**
  - Sidebar shows **Checkouts** (Fleet & Crew). Page lists current checkouts; **Check Out** each type (vehicle/battery/controller/dock/sensor/attachment) works; a second checkout of the same item shows the 409 message; **Check In** returns it; "Show returned" reveals history; supervisor can delete a record.
  - **Vehicle Detail** page no longer shows any checkout UI and still renders fully (registrations, components, etc.).
  - Visiting a bad URL shows the **404** page.
  - A dirty Settings form shows the **sticky save bar**.
  - Integrations shows provider/interval + a sync result line after "Sync now".
  - A table shows **skeleton rows** while loading (wire a consumer to pass `loading`, or verify the prop renders).
  - **Currency rule delete** now actually deletes (confirm dialog → row removed).
  - **Reports** pre-fills the last config on reload.

- [ ] **Step 3: Finish** — `superpowers:finishing-a-development-branch` (merge to main / push when Jonathan approves).

---

## Self-review (against the spec)
- Dedicated all-equipment Checkouts page (active + check-out modal + history + supervisor delete) → Task 1. ✓
- Route + sidebar + removal from Vehicle Detail → Tasks 2, 3. ✓
- NotFound, sticky save bar, integrations status, DataTable skeleton, Reports remember, confirm fix → Tasks 2,5,6,4,7,8. ✓
- Backend untouched. ✓
- Corrections folded in: sync-status is frontend-only (no counts/error from backend); the "standardized confirms" item became the real fix of the broken currency-rule delete; the non-existent "sidebar/cert-label removes" dropped. ✓
- DataTable skeleton task warns to reproduce existing row markup verbatim (no placeholder). ✓
- Task 8 notes to confirm the delete endpoint + setter name before finalizing (no invented symbol). ✓
