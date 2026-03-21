import { useState, useEffect } from 'react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { Save, TestTube, Loader2, Upload, FileSpreadsheet, RefreshCw, UserPlus, Key, Trash2, Shield, ShieldCheck, Eye } from 'lucide-react'

export default function SettingsPage() {
  const [settings, setSettings] = useState({})
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [importResult, setImportResult] = useState(null)
  const [importing, setImporting] = useState(false)
  const { isAdmin, user: currentUser } = useAuth()

  // User management state
  const [users, setUsers] = useState([])
  const [showAddUser, setShowAddUser] = useState(false)
  const [newUser, setNewUser] = useState({ username: '', password: '', display_name: '', role: 'manager' })
  const [addingUser, setAddingUser] = useState(false)

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
    }).catch(console.error)
    if (isAdmin) {
      api.get('/auth/users').then(setUsers).catch(console.error)
    }
  }, [isAdmin])

  const handleAddUser = async (e) => {
    e.preventDefault()
    setAddingUser(true)
    try {
      const created = await api.post('/auth/users', newUser)
      setUsers([...users, created])
      setNewUser({ username: '', password: '', display_name: '', role: 'manager' })
      setShowAddUser(false)
    } catch (err) { alert(err.message) }
    finally { setAddingUser(false) }
  }

  const handleDeleteUser = async (id) => {
    if (!confirm('Delete this user?')) return
    try {
      await api.delete(`/auth/users/${id}`)
      setUsers(users.filter(u => u.id !== id))
    } catch (err) { alert(err.message) }
  }

  const handleToggleActive = async (u) => {
    try {
      const updated = await api.patch(`/auth/users/${u.id}`, { is_active: !u.is_active })
      setUsers(users.map(x => x.id === u.id ? updated : x))
    } catch (err) { alert(err.message) }
  }

  const handleChangeRole = async (u, role) => {
    try {
      const updated = await api.patch(`/auth/users/${u.id}`, { role })
      setUsers(users.map(x => x.id === u.id ? updated : x))
    } catch (err) { alert(err.message) }
  }

  const handleResetPassword = async (userId) => {
    if (resetPw.length < 6) { alert('Password must be at least 6 characters'); return }
    try {
      await api.post(`/auth/users/${userId}/reset-password`, { new_password: resetPw })
      setResetUserId(null)
      setResetPw('')
      alert('Password reset successfully')
    } catch (err) { alert(err.message) }
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
      const items = Object.entries(settings).map(([key, value]) => ({ key, value }))
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
      const items = Object.entries(settings).map(([key, value]) => ({ key, value }))
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

  const handleSyncNow = async () => {
    setSyncing(true)
    setTestResult(null)
    try {
      const result = await api.post('/sync/now', {})
      const msg = `Synced: ${result.flights_new || 0} new flights, ${result.vehicles_synced || 0} vehicles, ${result.batteries_synced || 0} batteries`
      setTestResult({ ok: true, message: msg })
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
      const token = localStorage.getItem('token')
      const res = await fetch('/api/export/excel/import', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData,
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Import failed')
      }
      const result = await res.json()
      setImportResult(result)
    } catch (err) {
      setImportResult({ error: err.message })
    } finally {
      setImporting(false)
      e.target.value = '' // Reset file input
    }
  }

  const field = (label, key, type = 'text', description = '') => (
    <div>
      <label className="block text-sm font-medium text-foreground mb-1">{label}</label>
      {description && <p className="text-xs text-muted-foreground mb-1.5">{description}</p>}
      <input
        type={type}
        value={settings[key] || ''}
        onChange={(e) => setSettings({ ...settings, [key]: e.target.value })}
        className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        disabled={!isAdmin}
      />
    </div>
  )

  return (
    <div className="space-y-6 max-w-2xl">
      {/* Organization */}
      <div className="bg-card border border-border rounded-xl p-6">
        <h3 className="text-lg font-semibold text-foreground mb-4">Organization</h3>
        <div className="space-y-3">
          {field('Organization Name', 'org_name', 'text', 'Displayed on reports and exports')}
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
            onClick={handleSyncNow}
            disabled={syncing || !isAdmin}
            className="flex items-center gap-2 px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90 disabled:opacity-50"
          >
            {syncing ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            Sync Now
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
            <p><span className="font-medium text-foreground">Manager:</span> Add/edit flights, logs, certs, validate imports — cannot change settings, API keys, or manage users</p>
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
                    <option value="manager">Manager</option>
                    <option value="viewer">Viewer</option>
                    <option value="admin">Admin</option>
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
