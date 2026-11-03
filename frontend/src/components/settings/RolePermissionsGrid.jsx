/**
 * Admin editor for what each role can do (Settings > Users, below User
 * Management). Wide screens get a table with one column per role; narrow
 * screens get one card per feature with a role selector.
 */
import { useState, useEffect, useCallback } from 'react'
import { api } from '@/api/client'
import { useToast } from '@/contexts/ToastContext'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { useConfirm } from '@/hooks/useConfirm'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { Loader2, ShieldCheck } from 'lucide-react'
import {
  ROLES, EDITABLE_ROLES, ROLE_LABELS, VALUE_LABELS, OPTIONS,
  groupByFeature, setCell, cellState, diffChanges,
} from '@/lib/permissionGrid'

const WIDE_QUERY = '(min-width: 768px)'
const BUTTON = 'px-3 py-1.5 rounded-lg text-sm font-medium disabled:opacity-50'
const SECONDARY_BUTTON = `${BUTTON} bg-secondary text-secondary-foreground hover:opacity-90`
const PRIMARY_BUTTON = `${BUTTON} bg-primary text-primary-foreground hover:opacity-90`

const cellId = (role, key) => `perm-${role}-${key}`

/** One setting for one role: a select plus its short reason when locked. */
function PermissionCell({ def, role, values, registry, onChange }) {
  const { disabled, reason } = cellState(def, role, values, registry)
  const id = cellId(role, def.key)
  const reasonId = `${id}-reason`
  const showReason = role !== 'admin'

  return (
    <div className="flex flex-col gap-1">
      <select
        id={id}
        aria-label={`${ROLE_LABELS[role]}, ${def.feature}, ${def.action}`}
        aria-describedby={reason ? reasonId : undefined}
        value={values[role][def.key]}
        disabled={disabled}
        onChange={e => onChange(role, def.key, e.target.value)}
        className="w-full min-h-10 px-2 py-1.5 bg-secondary border border-border rounded-lg text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {OPTIONS[def.kind].map(option => (
          <option key={option} value={option}>{VALUE_LABELS[option]}</option>
        ))}
      </select>
      {reason && (
        <span id={reasonId} className={showReason ? 'text-xs text-muted-foreground' : 'sr-only'}>
          {reason}
        </span>
      )}
    </div>
  )
}

function PermissionTable({ groups, values, registry, onChange }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-border bg-card">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-muted-foreground">
            <th scope="col" className="px-3 py-2 font-medium">Setting</th>
            {ROLES.map(role => (
              <th key={role} scope="col" className="px-3 py-2 font-medium min-w-24">
                {ROLE_LABELS[role]}{role === 'admin' && <span className="block text-xs font-normal">Locked on</span>}
              </th>
            ))}
          </tr>
        </thead>
        {groups.map(group => (
          <tbody key={group.feature}>
            <tr className="bg-muted/40">
              <th scope="rowgroup" colSpan={ROLES.length + 1} className="px-3 py-2 text-left font-semibold text-foreground">
                {group.feature}
              </th>
            </tr>
            {group.rows.map(def => (
              <tr key={def.key} className="border-t border-border align-top">
                <th scope="row" className="px-3 py-2 text-left font-normal text-foreground">{def.action}</th>
                {ROLES.map(role => (
                  <td key={role} className="px-3 py-2">
                    <PermissionCell def={def} role={role} values={values} registry={registry} onChange={onChange} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        ))}
      </table>
    </div>
  )
}

function RoleSelector({ role, onChange }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor="permission-role" className="text-sm font-medium text-foreground">Role</label>
      <select
        id="permission-role"
        value={role}
        onChange={e => onChange(e.target.value)}
        className="w-full min-h-10 px-3 py-2 bg-secondary border border-border rounded-lg text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
      >
        {ROLES.map(r => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
      </select>
    </div>
  )
}

function PermissionCards({ groups, values, registry, onChange }) {
  const [role, setRole] = useState(EDITABLE_ROLES[0])

  return (
    <div className="space-y-4">
      <RoleSelector role={role} onChange={setRole} />
      {groups.map(group => (
        <div key={group.feature} role="group" aria-label={group.feature} className="bg-card border border-border rounded-xl p-4">
          <h4 className="text-sm font-semibold text-foreground mb-3">{group.feature}</h4>
          <div className="space-y-3">
            {group.rows.map(def => (
              <div key={def.key} className="grid grid-cols-2 gap-3 items-start">
                <label htmlFor={cellId(role, def.key)} className="text-sm text-foreground pt-2">{def.action}</label>
                <PermissionCell def={def} role={role} values={values} registry={registry} onChange={onChange} />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function SaveBar({ count, saving, onSave, onDiscard }) {
  return (
    <div className="sticky bottom-0 z-10 flex items-center justify-between gap-3 bg-card border border-border rounded-xl px-4 py-3 shadow-lg">
      <span className="text-sm text-foreground">{count} unsaved {count === 1 ? 'change' : 'changes'}</span>
      <div className="flex gap-2">
        <button type="button" onClick={onDiscard} disabled={saving} className={SECONDARY_BUTTON}>Discard</button>
        <button type="button" onClick={onSave} disabled={saving} className={`${PRIMARY_BUTTON} flex items-center gap-2`}>
          {saving && <Loader2 className="w-4 h-4 animate-spin" />} Save changes
        </button>
      </div>
    </div>
  )
}

function usePermissionGrid() {
  const toast = useToast()
  const [grid, setGrid] = useState(null)
  const [draft, setDraft] = useState(null)
  const [loadError, setLoadError] = useState('')
  const [saveError, setSaveError] = useState('')
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setLoadError('')
    try {
      const data = await api.get('/permissions')
      setGrid(data)
      setDraft(data.values)
    } catch (err) {
      setLoadError(err.message || 'Could not load permissions')
    }
  }, [])

  useEffect(() => { load() }, [load])

  const refresh = (data) => {
    setGrid(data)
    setDraft(data.values)
  }

  const run = async (request, success) => {
    setSaving(true)
    setSaveError('')
    try {
      refresh(await request())
      toast.success(success)
    } catch (err) {
      setSaveError(err.message || 'Could not save permissions')
    } finally {
      setSaving(false)
    }
  }

  const edit = (role, key, value) => setDraft(current => setCell(current, grid.registry, role, key, value))
  const changes = grid ? diffChanges(grid.values, draft, grid.registry) : []

  return {
    grid, draft, loadError, saveError, saving, changes, load, edit,
    discard: () => { setDraft(grid.values); setSaveError('') },
    save: () => run(() => api.put('/permissions', { changes }), 'Permissions saved'),
    reset: () => run(() => api.post('/permissions/reset', {}), 'Permissions reset to defaults'),
  }
}

function GridBody({ state }) {
  const wide = useMediaQuery(WIDE_QUERY)
  const { grid, draft, edit } = state
  const Layout = wide ? PermissionTable : PermissionCards
  return <Layout groups={groupByFeature(grid.registry)} values={draft} registry={grid.registry} onChange={edit} />
}

function LoadState({ error, onRetry }) {
  if (!error) {
    return <div className="flex items-center justify-center h-24"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /></div>
  }
  return (
    <div role="alert" className="flex items-center justify-between gap-3 text-sm text-destructive">
      <span>{error}</span>
      <button type="button" onClick={onRetry} className={SECONDARY_BUTTON}>Retry</button>
    </div>
  )
}

export default function RolePermissionsGrid() {
  const state = usePermissionGrid()
  const [confirmProps, requestConfirm] = useConfirm()
  const { grid, changes, saving, saveError } = state

  const askReset = () => requestConfirm({
    title: 'Reset permissions',
    message: changes.length > 0
      ? 'Return every role to the default permissions? Your unsaved changes will be lost.'
      : 'Return every role to the default permissions?',
    confirmLabel: 'Reset to defaults',
    onConfirm: state.reset,
  })

  return (
    <section aria-labelledby="role-permissions-title" className="space-y-4">
      <div className="bg-card border border-border rounded-xl p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 id="role-permissions-title" className="text-lg font-semibold text-foreground flex items-center gap-2">
            <ShieldCheck className="w-5 h-5" /> Role Permissions
          </h3>
          {grid && <button type="button" onClick={askReset} disabled={saving} className={SECONDARY_BUTTON}>Reset to defaults</button>}
        </div>
        <p className="mt-2 text-sm text-muted-foreground">
          Choose what supervisors, pilots and viewers can do. Changes apply from each person's next request.
          Viewers can never change unit data, and turning a feature's View off also turns off the settings that depend on it.
        </p>
        {!grid && <div className="mt-4"><LoadState error={state.loadError} onRetry={state.load} /></div>}
      </div>
      {grid && <GridBody state={state} />}
      {saveError && <p role="alert" className="text-sm text-destructive">{saveError}</p>}
      {changes.length > 0 && (
        <SaveBar count={changes.length} saving={saving} onSave={state.save} onDiscard={state.discard} />
      )}
      <ConfirmDialog {...confirmProps} />
    </section>
  )
}
