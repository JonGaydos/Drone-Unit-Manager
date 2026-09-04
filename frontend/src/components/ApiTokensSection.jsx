/**
 * Admin management of long-lived API tokens (Settings > API Tokens).
 * Tokens are shown once at creation; afterwards only the prefix is visible.
 */
import { useState, useEffect, useCallback } from 'react'
import { api } from '@/api/client'
import { useToast } from '@/contexts/ToastContext'
import { Modal } from '@/components/ui/Modal'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { useConfirm } from '@/hooks/useConfirm'
import { Plus, Copy, KeyRound, Loader2 } from 'lucide-react'

const SCOPE_LABELS = {
  fleet: 'Fleet',
  flights: 'Flights',
  pilots: 'Pilots & Certifications',
  maintenance: 'Maintenance',
  operations: 'Operations',
  documents: 'Documents & Media',
  reports: 'Reports & Dashboard',
}

const fmt = (s) => (s ? new Date(s).toLocaleString() : 'Never')

// Own component so typing re-renders only the modal, not the whole section
// (a section re-render would recreate Modal props and steal focus).
function CreateTokenModal({ onCreated, onClose }) {
  const toast = useToast()
  const [form, setForm] = useState({ name: '', read_only: true, allAreas: true, scopes: [] })
  const [saving, setSaving] = useState(false)
  const [newToken, setNewToken] = useState(null)

  const toggleScope = (key) => {
    setForm(f => ({
      ...f,
      scopes: f.scopes.includes(key) ? f.scopes.filter(s => s !== key) : [...f.scopes, key],
    }))
  }

  const handleCreate = async (e) => {
    e.preventDefault()
    if (!form.allAreas && form.scopes.length === 0) {
      toast.error('Select at least one area, or choose all areas')
      return
    }
    setSaving(true)
    try {
      const res = await api.post('/api-tokens', {
        name: form.name,
        read_only: form.read_only,
        scopes: form.allAreas ? null : form.scopes,
      })
      setNewToken(res.token)
      onCreated()
    } catch (err) {
      toast.error(err.message)
    } finally {
      setSaving(false)
    }
  }

  const copyToken = async () => {
    try {
      await navigator.clipboard.writeText(newToken)
      toast.success('Token copied to clipboard')
    } catch {
      toast.error('Copy failed; select and copy it manually')
    }
  }

  return (
    <Modal open onClose={onClose} title={newToken ? 'Token Created' : 'Create API Token'} className="max-w-md">
      {newToken ? (
        <div className="space-y-3">
          <div className="bg-warning-bg text-warning rounded-lg p-3 text-sm">
            Copy this token now. It is shown only once and cannot be recovered later.
          </div>
          <div className="flex gap-2">
            <input readOnly value={newToken} onFocus={e => e.target.select()}
              className="flex-1 px-3 py-2 bg-secondary border border-border rounded-lg text-foreground font-mono text-xs" />
            <button onClick={copyToken} className="px-3 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90" aria-label="Copy token">
              <Copy className="w-4 h-4" />
            </button>
          </div>
          <button onClick={onClose} className="w-full py-2 bg-secondary text-secondary-foreground rounded-lg text-sm">Done</button>
        </div>
      ) : (
        <form onSubmit={handleCreate} className="space-y-3">
          <div>
            <label htmlFor="token-name" className="block text-sm font-medium text-foreground mb-1">Name</label>
            <input id="token-name" type="text" required value={form.name}
              onChange={e => { const v = e.target.value; setForm(f => ({ ...f, name: v })) }}
              placeholder="e.g. Home Assistant"
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
          </div>
          <div>
            <label htmlFor="token-access" className="block text-sm font-medium text-foreground mb-1">Access</label>
            <select id="token-access" value={form.read_only ? 'read' : 'write'}
              onChange={e => { const v = e.target.value; setForm(f => ({ ...f, read_only: v === 'read' })) }}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
              <option value="read">Read only</option>
              <option value="write">Read & write</option>
            </select>
          </div>
          <div>
            <span className="block text-sm font-medium text-foreground mb-1">Areas</span>
            <label className="flex items-center gap-2 text-sm text-foreground mb-1">
              <input type="checkbox" checked={form.allAreas}
                onChange={e => { const v = e.target.checked; setForm(f => ({ ...f, allAreas: v })) }} className="rounded border-border" />
              All areas
            </label>
            {!form.allAreas && (
              <div className="grid grid-cols-2 gap-1 pl-1">
                {Object.entries(SCOPE_LABELS).map(([key, label]) => (
                  <label key={key} className="flex items-center gap-2 text-sm text-foreground">
                    <input type="checkbox" checked={form.scopes.includes(key)}
                      onChange={() => toggleScope(key)} className="rounded border-border" />
                    {label}
                  </label>
                ))}
              </div>
            )}
          </div>
          <div className="flex gap-2 pt-2">
            <button type="submit" disabled={saving}
              className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2">
              {saving && <Loader2 className="w-4 h-4 animate-spin" />}{!saving && 'Create Token'}
            </button>
            <button type="button" onClick={onClose} className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm">Cancel</button>
          </div>
        </form>
      )}
    </Modal>
  )
}

export default function ApiTokensSection() {
  const toast = useToast()
  const [confirmProps, requestConfirm] = useConfirm()
  const [tokens, setTokens] = useState([])
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)

  const load = useCallback(() => {
    api.get('/api-tokens')
      .then(t => setTokens(Array.isArray(t) ? t : []))
      .catch(err => toast.error(err.message))
      .finally(() => setLoading(false))
  }, [toast])

  useEffect(() => { load() }, [load])

  const handleRevoke = (t) => {
    requestConfirm({
      title: 'Revoke API Token',
      message: `Revoke "${t.name}"? Anything using it will immediately lose access. This cannot be undone.`,
      onConfirm: async () => {
        try { await api.delete(`/api-tokens/${t.id}`); load() } catch (err) { toast.error(err.message) }
      }
    })
  }

  if (loading) return <div className="flex items-center justify-center h-32"><div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>

  return (
    <div className="bg-card border border-border rounded-xl p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <KeyRound className="w-5 h-5 text-primary" />
          <h2 className="font-semibold text-foreground">API Tokens</h2>
        </div>
        <button onClick={() => setCreateOpen(true)} className="flex items-center gap-2 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90">
          <Plus className="w-4 h-4" /> Create Token
        </button>
      </div>
      <p className="text-sm text-muted-foreground">
        Long-lived tokens for external integrations such as Home Assistant. Tokens never expire until revoked,
        act with your role at most, and can be limited to read-only access and specific areas.
        Settings, users, backups, and sync control are never accessible with a token.
      </p>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/30">
              <th className="text-left px-3 py-2 font-medium text-muted-foreground">Name</th>
              <th className="text-left px-3 py-2 font-medium text-muted-foreground">Token</th>
              <th className="text-left px-3 py-2 font-medium text-muted-foreground">Access</th>
              <th className="text-left px-3 py-2 font-medium text-muted-foreground hidden md:table-cell">Areas</th>
              <th className="text-left px-3 py-2 font-medium text-muted-foreground hidden md:table-cell">Last Used</th>
              <th className="text-left px-3 py-2 font-medium text-muted-foreground">Status</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {tokens.map(t => (
              <tr key={t.id} className="border-b border-border/50">
                <td className="px-3 py-2 text-foreground font-medium">{t.name}</td>
                <td className="px-3 py-2 text-muted-foreground font-mono text-xs">{t.token_prefix}...</td>
                <td className="px-3 py-2 text-foreground">{t.read_only ? 'Read only' : 'Read & write'}</td>
                <td className="px-3 py-2 text-muted-foreground hidden md:table-cell">
                  {t.scopes ? t.scopes.map(s => SCOPE_LABELS[s] || s).join(', ') : 'All areas'}
                </td>
                <td className="px-3 py-2 text-muted-foreground hidden md:table-cell">{fmt(t.last_used_at)}</td>
                <td className="px-3 py-2">
                  {t.revoked_at
                    ? <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-danger-bg text-danger">revoked</span>
                    : <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-success-bg text-success">active</span>}
                </td>
                <td className="px-3 py-2 text-right">
                  {!t.revoked_at && (
                    <button onClick={() => handleRevoke(t)} className="text-sm text-muted-foreground hover:text-destructive">Revoke</button>
                  )}
                </td>
              </tr>
            ))}
            {tokens.length === 0 && (
              <tr><td colSpan={7} className="px-3 py-8 text-center text-muted-foreground">No API tokens yet</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {createOpen && (
        <CreateTokenModal onCreated={load} onClose={() => setCreateOpen(false)} />
      )}
      <ConfirmDialog {...confirmProps} />
    </div>
  )
}
