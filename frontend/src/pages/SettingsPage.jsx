import React, { useState, useEffect } from 'react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { sortByName } from '@/lib/formatters'
import { Save, TestTube, Loader2, Upload, FileSpreadsheet, RefreshCw, UserPlus, Key, Trash2, Shield, ShieldCheck, Eye, Image as ImageIcon } from 'lucide-react'

export default function SettingsPage() {
  const [settings, setSettings] = useState({})
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [importResult, setImportResult] = useState(null)
  const [importing, setImporting] = useState(false)
  const { isAdmin, user: currentUser } = useAuth()
  const toast = useToast()

  // User management state
  const [users, setUsers] = useState([])
  const [pilots, setPilots] = useState([])
  const [showAddUser, setShowAddUser] = useState(false)
  const [newUser, setNewUser] = useState({ username: '', password: '', display_name: '', role: 'pilot', pilot_id: '' })
  const [addingUser, setAddingUser] = useState(false)

  // Logo state
  const [logoUrl, setLogoUrl] = useState(null)
  const [uploadingLogo, setUploadingLogo] = useState(false)

  // Change password state
  const [pwForm, setPwForm] = useState({ current_password: '', new_password: '', confirm_password: '' })
  const [pwMsg, setPwMsg] = useState(null)
  const [changingPw, setChangingPw] = useState(false)

  // Reset password state
  const [resetUserId, setResetUserId] = useState(null)
  const [resetPw, setResetPw] = useState('')

  useEffect(() => {
    api.get('/settings').then(data => {
      const map = {}
      data.forEach(s => { map[s.key] = s.value })
      setSettings(map)
      if (map.org_logo) setLogoUrl(map.org_logo + '?t=' + Date.now())
    }).catch(console.error)
    if (isAdmin) {
      api.get('/auth/users').then(setUsers).catch(console.error)
      api.get('/pilots').then(setPilots).catch(console.error)
    }
  }, [isAdmin])

  const handleAddUser = async (e) => {
    e.preventDefault()
    setAddingUser(true)
    try {
      const payload = { ...newUser }
      if (payload.pilot_id) {
        payload.pilot_id = parseInt(payload.pilot_id)
      } else {
        delete payload.pilot_id
      }
      const created = await api.post('/auth/users', payload)
      setUsers([...users, created])
      setNewUser({ username: '', password: '', display_name: '', role: 'pilot', pilot_id: '' })
      setShowAddUser(false)
    } catch (err) { toast.error(err.message) }
    finally { setAddingUser(false) }
  }

  const handleDeleteUser = async (id) => {
    if (!confirm('Delete this user?')) return
    try {
      await api.delete(`/auth/users/${id}`)
      setUsers(users.filter(u => u.id !== id))
    } catch (err) { toast.error(err.message) }
  }

  const handleToggleActive = async (u) => {
    try {
      const updated = await api.patch(`/auth/users/${u.id}`, { is_active: !u.is_active })
      setUsers(users.map(x => x.id === u.id ? updated : x))
    } catch (err) { toast.error(err.message) }
  }

  const handleChangeRole = async (u, role) => {
    try {
      const updated = await api.patch(`/auth/users/${u.id}`, { role })
      setUsers(users.map(x => x.id === u.id ? updated : x))
    } catch (err) { toast.error(err.message) }
  }

  const handleResetPassword = async (userId) => {
    if (resetPw.length < 6) { toast.warning('Password must be at least 6 characters'); return }
    try {
      await api.post(`/auth/users/${userId}/reset-password`, { new_password: resetPw })
      setResetUserId(null)
      setResetPw('')
      toast.success('Password reset successfully')
    } catch (err) { toast.error(err.message) }
  }

  const handleChangePassword = async (e) => {
    e.preventDefault()
    if (pwForm.new_password !== pwForm.confirm_password) {
      setPwMsg({ ok: false, message: 'Passwords do not match' }); return
    }
    setChangingPw(true)
    try {
      const result = await api.post('/auth/change-password', {
        current_password: pwForm.current_password,
        new_password: pwForm.new_password,
      })
      setPwMsg({ ok: true, message: result.message })
      setPwForm({ current_password: '', new_password: '', confirm_password: '' })
    } catch (err) {
      setPwMsg({ ok: false, message: err.message })
    } finally { setChangingPw(false) }
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const current = gatherInputs()
      setSettings(current)
      const items = Object.entries(current).map(([key, value]) => ({ key, value }))
      await api.put('/settings/bulk', items)
      setTestResult({ ok: true, message: 'Settings saved!' })
    } catch (err) {
      setTestResult({ ok: false, message: err.message })
    } finally {
      setSaving(false)
      setTimeout(() => setTestResult(null), 5000)
    }
  }

  const handleTestConnection = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      // Save credentials first
      const current = gatherInputs()
      setSettings(current)
      const items = Object.entries(current).map(([key, value]) => ({ key, value }))
      await api.put('/settings/bulk', items)
      // Then test
      const result = await api.post('/sync/test', {})
      setTestResult({ ok: result.ok, message: result.message })
    } catch (err) {
      setTestResult({ ok: false, message: err.message })
    } finally {
      setTesting(false)
    }
  }

  const handleSyncNow = async (full = false) => {
    setSyncing(true)
    setTestResult(null)
    try {
      const result = await api.post(`/sync/now?full=${full}`, {})
      const parts = [
        `${result.flights_new || 0} new flights`,
        `${result.flights_skipped || 0} skipped`,
        `${result.vehicles_synced || 0} vehicles`,
        `${result.batteries_synced || 0} batteries`,
        `${result.controllers_synced || 0} controllers`,
        `${result.users_synced || 0} users`,
      ]
      let msg = `Synced: ${parts.join(', ')}`
      if (result.errors?.length > 0) {
        msg += `\n\nErrors:\n${result.errors.join('\n')}`
      }
      setTestResult({ ok: result.errors?.length === 0, message: msg })
    } catch (err) {
      setTestResult({ ok: false, message: err.message })
    } finally {
      setSyncing(false)
    }
  }

  const handleExcelImport = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    setImporting(true)
    setImportResult(null)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const result = await api.upload('/export/excel/import', formData)
      setImportResult(result)
    } catch (err) {
      setImportResult({ error: err.message })
    } finally {
      setImporting(false)
      e.target.value = '' // Reset file input
    }
  }

  // Use refs for settings inputs to avoid re-renders on keystroke/paste
  const inputRefs = React.useRef({})

  const PASSWORD_KEYS = new Set(['skydio_api_token'])

  const gatherInputs = () => {
    const gathered = { ...settings }
    for (const [key, ref] of Object.entries(inputRefs.current)) {
      if (!ref) continue
      // Skip password fields where user didn't type anything new
      if (PASSWORD_KEYS.has(key) && ref.value === '') continue
      gathered[key] = ref.value
    }
    return gathered
  }

  const field = (label, key, type = 'text', description = '') => {
    const isPassword = type === 'password'
    const hasMaskedValue = isPassword && settings[key] && settings[key].includes('...')
    return (
      <div>
        <label className="block text-sm font-medium text-foreground mb-1">{label}</label>
        {description && <p className="text-xs text-muted-foreground mb-1.5">{description}</p>}
        <input
          type={type}
          ref={el => { inputRefs.current[key] = el }}
          key={`${key}-${settings[key] === undefined ? 'loading' : 'loaded'}`}
          defaultValue={isPassword ? '' : (settings[key] || '')}
          placeholder={hasMaskedValue ? 'Token saved (enter new to replace)' : ''}
          className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          disabled={!isAdmin}
        />
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-2xl">
      {/* Organization */}
      <div className="bg-card border border-border rounded-xl p-6">
        <h3 className="text-lg font-semibold text-foreground mb-4">Organization</h3>
        <div className="space-y-4">
          {field('Organization Name', 'org_name', 'text', 'Displayed on reports and exports')}

          {/* Logo Upload */}
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Organization Logo</label>
            <p className="text-xs text-muted-foreground mb-2">Used on reports and exports</p>
            <div className="flex items-center gap-4">
              {logoUrl ? (
                <img src={logoUrl} alt="Org logo" className="w-16 h-16 object-contain rounded-lg border border-border bg-secondary p-1" />
              ) : (
                <div className="w-16 h-16 rounded-lg border border-border border-dashed bg-secondary/50 flex items-center justify-center">
                  <ImageIcon className="w-6 h-6 text-muted-foreground" />
                </div>
              )}
              {isAdmin && (
                <label className="flex items-center gap-2 px-4 py-2 bg-secondary border border-border rounded-lg text-sm cursor-pointer hover:bg-accent/30 transition-colors">
                  {uploadingLogo ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                  <span className="text-muted-foreground">{uploadingLogo ? 'Uploading...' : 'Upload Logo'}</span>
                  <input type="file" accept="image/*" className="hidden" disabled={uploadingLogo} onChange={async (e) => {
                    const file = e.target.files[0]
                    if (!file) return
                    setUploadingLogo(true)
                    try {
                      const formData = new FormData()
                      formData.append('file', file)
                      const result = await api.upload('/settings/logo', formData)
                      setLogoUrl(result.logo_url + '?t=' + Date.now())
                    } catch (err) { toast.error(err.message) }
                    finally { setUploadingLogo(false) }
                    e.target.value = ''
                  }} />
                </label>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Skydio API */}
      <div className="bg-card border border-border rounded-xl p-6">
        <h3 className="text-lg font-semibold text-foreground mb-1">Skydio Cloud API</h3>
        <p className="text-sm text-muted-foreground mb-4">
          Enter your Skydio Cloud API credentials. Get them from Settings &gt; Integrations in Skydio Cloud.
        </p>
        <div className="space-y-3">
          {field('API Token', 'skydio_api_token', 'password', 'Your Skydio Cloud API token')}
          {field('Token ID', 'skydio_token_id', 'text', 'UUID of the API token')}
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Auto-Sync Interval</label>
            <select
              value={settings.skydio_sync_interval || 'manual'}
              onChange={(e) => setSettings({ ...settings, skydio_sync_interval: e.target.value })}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm"
              disabled={!isAdmin}
            >
              <option value="manual">Manual Only</option>
              <option value="6h">Every 6 Hours</option>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
            </select>
          </div>
        </div>
        <div className="flex gap-2 mt-4">
          <button
            onClick={handleTestConnection}
            disabled={testing || !isAdmin}
            className="flex items-center gap-2 px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90 disabled:opacity-50"
          >
            {testing ? <Loader2 className="w-4 h-4 animate-spin" /> : <TestTube className="w-4 h-4" />}
            Test Connection
          </button>
          <button
            onClick={() => handleSyncNow(false)}
            disabled={syncing || !isAdmin}
            className="flex items-center gap-2 px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90 disabled:opacity-50"
          >
            {syncing ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            Sync Now
          </button>
          <button
            onClick={() => handleSyncNow(true)}
            disabled={syncing || !isAdmin}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm hover:opacity-90 disabled:opacity-50"
            title="Ignore last sync date and fetch ALL historical flights from Skydio"
          >
            {syncing ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            Full Sync
          </button>
        </div>
      </div>

      {/* Excel Import */}
      <div className="bg-card border border-border rounded-xl p-6">
        <h3 className="text-lg font-semibold text-foreground mb-1">Import Data</h3>
        <p className="text-sm text-muted-foreground mb-4">
          Import pilots, flights, and certifications from an Excel spreadsheet (.xlsx).
          The spreadsheet should have sheets named "Skydio" (flights) and "Pilot Info" (certifications).
        </p>
        {isAdmin && (
          <label className="flex items-center gap-3 px-4 py-3 bg-secondary border border-border border-dashed rounded-lg cursor-pointer hover:bg-accent/30 transition-colors">
            {importing ? (
              <Loader2 className="w-5 h-5 text-primary animate-spin" />
            ) : (
              <FileSpreadsheet className="w-5 h-5 text-primary" />
            )}
            <div>
              <p className="text-sm font-medium text-foreground">
                {importing ? 'Importing...' : 'Choose Excel File (.xlsx)'}
              </p>
              <p className="text-xs text-muted-foreground">Pilots, flights, and certifications will be imported</p>
            </div>
            <input
              type="file"
              accept=".xlsx,.xls"
              className="hidden"
              onChange={handleExcelImport}
              disabled={importing}
            />
          </label>
        )}

        {importResult && (
          <div className={`mt-4 p-4 rounded-lg border text-sm ${
            importResult.error
              ? 'bg-destructive/10 border-destructive/30 text-destructive'
              : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
          }`}>
            {importResult.error ? (
              <p>{importResult.error}</p>
            ) : (
              <div className="space-y-1">
                <p className="font-medium">Import Complete</p>
                <p>Pilots: {importResult.pilots_created}</p>
                <p>Vehicles: {importResult.vehicles_created}</p>
                <p>Flights imported: {importResult.flights_imported}</p>
                <p>Flights skipped (duplicates): {importResult.flights_skipped}</p>
                <p>Certification types created: {importResult.certifications_created}</p>
                <p>Cert assignments: {importResult.cert_assignments}</p>
                {importResult.errors?.length > 0 && (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-amber-400">{importResult.errors.length} warnings</summary>
                    <ul className="mt-1 text-xs space-y-0.5">
                      {importResult.errors.slice(0, 20).map((e, i) => <li key={i}>{e}</li>)}
                      {importResult.errors.length > 20 && <li>...and {importResult.errors.length - 20} more</li>}
                    </ul>
                  </details>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Save */}
      {isAdmin && (
        <div className="flex items-center gap-4">
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 px-6 py-2.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Save Settings
          </button>
          {testResult && (
            <span className={`text-sm ${testResult.ok ? 'text-emerald-400' : 'text-destructive'}`}>
              {testResult.message}
            </span>
          )}
        </div>
      )}

      {/* Change Password */}
      <div className="bg-card border border-border rounded-xl p-6">
        <h3 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
          <Key className="w-5 h-5" /> Change Password
        </h3>
        <form onSubmit={handleChangePassword} className="space-y-3 max-w-sm">
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Current Password</label>
            <input type="password" value={pwForm.current_password} onChange={e => setPwForm({...pwForm, current_password: e.target.value})} required
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">New Password</label>
            <input type="password" value={pwForm.new_password} onChange={e => setPwForm({...pwForm, new_password: e.target.value})} required minLength={6}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Confirm New Password</label>
            <input type="password" value={pwForm.confirm_password} onChange={e => setPwForm({...pwForm, confirm_password: e.target.value})} required minLength={6}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
          </div>
          <button type="submit" disabled={changingPw}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50">
            {changingPw ? <Loader2 className="w-4 h-4 animate-spin" /> : <Key className="w-4 h-4" />}
            Change Password
          </button>
          {pwMsg && (
            <p className={`text-sm ${pwMsg.ok ? 'text-emerald-400' : 'text-destructive'}`}>{pwMsg.message}</p>
          )}
        </form>
      </div>

      {/* User Management - Admin Only */}
      {isAdmin && (
        <div className="bg-card border border-border rounded-xl p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
              <Shield className="w-5 h-5" /> User Management
            </h3>
            <button onClick={() => setShowAddUser(!showAddUser)}
              className="flex items-center gap-2 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90">
              <UserPlus className="w-4 h-4" /> Add User
            </button>
          </div>

          {/* Role descriptions */}
          <div className="mb-4 p-3 bg-muted/30 rounded-lg text-xs text-muted-foreground space-y-1">
            <p><span className="font-medium text-foreground">Admin:</span> Full access — settings, API keys, user management, delete records</p>
            <p><span className="font-medium text-foreground">Pilot:</span> Add/edit flights, logs, certs — linked to a pilot profile</p>
            <p><span className="font-medium text-foreground">Viewer:</span> Read-only access to all data and reports</p>
          </div>

          {/* Add user form */}
          {showAddUser && (
            <form onSubmit={handleAddUser} className="mb-4 p-4 bg-muted/20 rounded-lg border border-border space-y-3">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">Username</label>
                  <input type="text" value={newUser.username} onChange={e => setNewUser({...newUser, username: e.target.value})} required
                    className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">Display Name</label>
                  <input type="text" value={newUser.display_name} onChange={e => setNewUser({...newUser, display_name: e.target.value})} required
                    className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">Password</label>
                  <input type="password" value={newUser.password} onChange={e => setNewUser({...newUser, password: e.target.value})} required minLength={6}
                    className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">Role</label>
                  <select value={newUser.role} onChange={e => setNewUser({...newUser, role: e.target.value})}
                    className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
                    <option value="admin">Admin</option>
                    <option value="pilot">Pilot</option>
                    <option value="viewer">Viewer</option>
                  </select>
                </div>
                <div className="sm:col-span-2">
                  <label className="block text-sm font-medium text-foreground mb-1">Link to Pilot</label>
                  <select value={newUser.pilot_id} onChange={e => setNewUser({...newUser, pilot_id: e.target.value})}
                    className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
                    <option value="">-- No pilot linked --</option>
                    {sortByName(pilots).map(p => (
                      <option key={p.id} value={p.id}>{p.full_name}{p.badge_number ? ` (Badge: ${p.badge_number})` : ''}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="flex gap-2">
                <button type="submit" disabled={addingUser}
                  className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50">
                  {addingUser ? 'Creating...' : 'Create User'}
                </button>
                <button type="button" onClick={() => setShowAddUser(false)}
                  className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90">
                  Cancel
                </button>
              </div>
            </form>
          )}

          {/* User list */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left px-3 py-2 font-medium text-muted-foreground">User</th>
                  <th className="text-left px-3 py-2 font-medium text-muted-foreground">Role</th>
                  <th className="text-left px-3 py-2 font-medium text-muted-foreground">Status</th>
                  <th className="text-right px-3 py-2 font-medium text-muted-foreground">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map(u => (
                  <tr key={u.id} className="border-b border-border/50">
                    <td className="px-3 py-2">
                      <div className="font-medium text-foreground">{u.display_name}</div>
                      <div className="text-xs text-muted-foreground">{u.username}</div>
                    </td>
                    <td className="px-3 py-2">
                      <select value={u.role} onChange={e => handleChangeRole(u, e.target.value)}
                        disabled={u.id === currentUser?.id}
                        className="px-2 py-1 bg-secondary border border-border rounded text-xs text-foreground disabled:opacity-50">
                        <option value="admin">Admin</option>
                        <option value="pilot">Pilot</option>
                        <option value="manager">Manager</option>
                        <option value="viewer">Viewer</option>
                      </select>
                    </td>
                    <td className="px-3 py-2">
                      <button onClick={() => handleToggleActive(u)} disabled={u.id === currentUser?.id}
                        className={`px-2 py-0.5 rounded-full text-xs font-medium ${u.is_active ? 'bg-emerald-500/15 text-emerald-400' : 'bg-red-500/15 text-red-400'} disabled:opacity-50`}>
                        {u.is_active ? 'Active' : 'Disabled'}
                      </button>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <div className="flex items-center justify-end gap-1">
                        {resetUserId === u.id ? (
                          <div className="flex items-center gap-1">
                            <input type="password" placeholder="New password" value={resetPw} onChange={e => setResetPw(e.target.value)}
                              className="w-28 px-2 py-1 bg-secondary border border-border rounded text-xs text-foreground" />
                            <button onClick={() => handleResetPassword(u.id)} className="px-2 py-1 bg-primary text-primary-foreground rounded text-xs">Set</button>
                            <button onClick={() => { setResetUserId(null); setResetPw('') }} className="px-2 py-1 bg-secondary text-secondary-foreground rounded text-xs">Cancel</button>
                          </div>
                        ) : (
                          <>
                            <button onClick={() => setResetUserId(u.id)} title="Reset password"
                              className="p-1.5 text-muted-foreground hover:text-foreground rounded hover:bg-accent/30">
                              <Key className="w-3.5 h-3.5" />
                            </button>
                            {u.id !== currentUser?.id && (
                              <button onClick={() => handleDeleteUser(u.id)} title="Delete user"
                                className="p-1.5 text-muted-foreground hover:text-destructive rounded hover:bg-accent/30">
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            )}
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
