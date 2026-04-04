import React, { useState, useEffect } from 'react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { useConfirm } from '@/hooks/useConfirm'
import { sortPilotsActiveFirst } from '@/lib/formatters'
import { Save, Loader2, Upload, UserPlus, Key, Trash2, Shield, Image as ImageIcon, ChevronUp, ChevronDown, ExternalLink, X, Edit2 } from 'lucide-react'

const IntegrationsContent = React.lazy(() => import('@/pages/IntegrationsPage'))

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState('general')
  const [settings, setSettings] = useState({})
  const [saving, setSaving] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const { isAdmin, user: currentUser } = useAuth()
  const toast = useToast()
  const [confirmProps, requestConfirm] = useConfirm()

  // User management state
  const [users, setUsers] = useState([])
  const [pilots, setPilots] = useState([])
  const [showAddUser, setShowAddUser] = useState(false)
  const [newUser, setNewUser] = useState({ username: '', password: '', display_name: '', role: 'pilot', pilot_id: '' })
  const [addingUser, setAddingUser] = useState(false)

  // Logo state
  const [logoUrl, setLogoUrl] = useState(null)
  const [uploadingLogo, setUploadingLogo] = useState(false)

  // Sidebar config state
  const [sidebarItems, setSidebarItems] = useState([])
  const [savingSidebar, setSavingSidebar] = useState(false)

  // Certification status labels state
  const [certLabels, setCertLabels] = useState({})
  const [savingCertLabels, setSavingCertLabels] = useState(false)

  // Weather thresholds state
  const [weatherThresholds, setWeatherThresholds] = useState({})
  const [savingWeatherThresholds, setSavingWeatherThresholds] = useState(false)

  // Mission purposes state
  const [missionPurposes, setMissionPurposes] = useState([])
  const [newPurpose, setNewPurpose] = useState('')
  const [savingPurposes, setSavingPurposes] = useState(false)

  // Unsaved changes state
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false)

  useEffect(() => {
    if (!hasUnsavedChanges) return
    const handler = (e) => {
      e.preventDefault()
      e.returnValue = ''
    }
    globalThis.addEventListener('beforeunload', handler)
    return () => globalThis.removeEventListener('beforeunload', handler)
  }, [hasUnsavedChanges])

  // Change password state
  const [pwForm, setPwForm] = useState({ current_password: '', new_password: '', confirm_password: '' })
  const [pwMsg, setPwMsg] = useState(null)
  const [changingPw, setChangingPw] = useState(false)

  // Edit user state
  const [editUser, setEditUser] = useState(null)
  const [editUserForm, setEditUserForm] = useState({ display_name: '', role: '', pilot_id: '' })
  const [savingEditUser, setSavingEditUser] = useState(false)

  const openEditUser = (u) => {
    setEditUser(u)
    setEditUserForm({
      display_name: u.display_name || '',
      role: u.role || 'viewer',
      pilot_id: u.pilot_id ? String(u.pilot_id) : '',
    })
  }

  const handleSaveEditUser = async () => {
    if (!editUser) return
    setSavingEditUser(true)
    try {
      const payload = { display_name: editUserForm.display_name, role: editUserForm.role }
      payload.pilot_id = editUserForm.pilot_id ? Number.parseInt(editUserForm.pilot_id, 10) : 0
      const updated = await api.patch(`/auth/users/${editUser.id}`, payload)
      setUsers(users.map(x => x.id === editUser.id ? updated : x))
      setEditUser(null)
      toast.success('User updated')
    } catch (err) { toast.error(err.message) }
    finally { setSavingEditUser(false) }
  }

  // Reset password state
  const [resetUserId, setResetUserId] = useState(null)
  const [resetPw, setResetPw] = useState('')

  const DEFAULT_SIDEBAR_ITEMS = [
    { to: '/', label: 'Dashboard' },
    { to: '/weather', label: 'Weather' },
    { to: '/airspace', label: 'Airspace' },
    { to: '/analytics', label: 'Analytics' },
    { to: '/flight-plans', label: 'Flight Plans' },
    { to: '/checklists', label: 'Checklists' },
    { to: '/flights', label: 'Flights' },
    { to: '/missions', label: 'Mission Log' },
    { to: '/training', label: 'Training Log' },
    { to: '/pilots', label: 'Pilots' },
    { to: '/fleet', label: 'Fleet' },
    { to: '/certifications', label: 'Certifications' },
    { to: '/maintenance', label: 'Maintenance' },
    { to: '/media', label: 'Photo Gallery' },
    { to: '/documents', label: 'Documents' },
    { to: '/reports', label: 'Reports' },
    { to: '/compliance', label: 'Compliance' },
    { to: '/alerts', label: 'Alerts' },
    { to: '/incidents', label: 'Activity Reports' },
    { to: '/settings', label: 'Settings' },
    { to: '/audit-log', label: 'Audit Log' },
  ]

  const loadDefaultPurposes = () => {
    api.get('/flights/purposes/list').then(purposes => {
      if (Array.isArray(purposes) && purposes.length > 0) {
        setMissionPurposes(purposes.map(p => p.name))
      }
    }).catch(() => {})
  }

  const handlePurposeKeyDown = (e) => {
    if (e.key === 'Enter' && newPurpose.trim()) {
      setMissionPurposes(prev => [...prev, newPurpose.trim()])
      setNewPurpose('')
    }
  }

  useEffect(() => {
    api.get('/settings').then(data => {
      const map = {}
      data.forEach(s => { map[s.key] = s.value })
      setSettings(map)
      if (map.org_logo) setLogoUrl(map.org_logo + '?t=' + Date.now())
      // Load sidebar config
      if (map.sidebar_config) {
        try {
          const parsed = JSON.parse(map.sidebar_config)
          // Merge with defaults to pick up any new items
          const configMap = {}
          parsed.forEach(c => { configMap[c.to] = c })
          const merged = DEFAULT_SIDEBAR_ITEMS.map((item, i) => {
            const existing = configMap[item.to]
            return {
              to: item.to,
              label: item.label,
              visible: existing ? existing.visible !== false : true,
              order: existing ? existing.order : i,
            }
          })
          merged.sort((a, b) => a.order - b.order)
          setSidebarItems(merged)
        } catch {
          setSidebarItems(DEFAULT_SIDEBAR_ITEMS.map((item, i) => ({ ...item, visible: true, order: i })))
        }
      } else {
        setSidebarItems(DEFAULT_SIDEBAR_ITEMS.map((item, i) => ({ ...item, visible: true, order: i })))
      }
      // Load cert status labels
      if (map.cert_status_labels) {
        try { setCertLabels(JSON.parse(map.cert_status_labels)) } catch { /* invalid JSON */ }
      }
      // Load weather thresholds
      if (map.weather_thresholds) {
        try { setWeatherThresholds(JSON.parse(map.weather_thresholds)) } catch { /* invalid JSON */ }
      }
      // Load mission purposes from settings, or fall back to API defaults
      if (map.mission_purposes) {
        try { setMissionPurposes(JSON.parse(map.mission_purposes)) } catch { /* invalid JSON */ }
      } else {
        loadDefaultPurposes()
      }
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
        payload.pilot_id = Number.parseInt(payload.pilot_id, 10)
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

  const handleDeleteUser = (id) => {
    requestConfirm({
      title: 'Delete User',
      message: 'Delete this user?',
      onConfirm: async () => {
        try {
          await api.delete(`/auth/users/${id}`)
          setUsers(users.filter(u => u.id !== id))
        } catch (err) { toast.error(err.message) }
      }
    })
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
      setHasUnsavedChanges(false)
      setTestResult({ ok: true, message: 'Settings saved!' })
    } catch (err) {
      setTestResult({ ok: false, message: err.message })
    } finally {
      setSaving(false)
      setTimeout(() => setTestResult(null), 5000)
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
    const hasMaskedValue = isPassword && settings[key]?.includes('...')
    const fieldId = `setting-${key}`
    return (
      <div>
        <label htmlFor={fieldId} className="block text-sm font-medium text-foreground mb-1">{label}</label>
        {description && <p className="text-xs text-muted-foreground mb-1.5">{description}</p>}
        <input
          id={fieldId}
          type={type}
          ref={el => { inputRefs.current[key] = el }}
          key={`${key}-${settings[key] === undefined ? 'loading' : 'loaded'}`}
          defaultValue={isPassword ? '' : (settings[key] || '')}
          placeholder={hasMaskedValue ? 'Token saved (enter new to replace)' : ''}
          className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          disabled={!isAdmin}
          onInput={() => setHasUnsavedChanges(true)}
        />
      </div>
    )
  }

  const TABS = [
    { id: 'general', label: 'General' },
    ...(isAdmin ? [{ id: 'users', label: 'Users' }] : []),
    ...(isAdmin ? [{ id: 'integrations', label: 'Integrations' }] : []),
  ]

  return (
    <div className="space-y-6">
      {/* Tab Navigation */}
      <div className="flex gap-1 border-b border-border">
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px ${
              activeTab === tab.id
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Integrations Tab */}
      {activeTab === 'integrations' && isAdmin && (
        <React.Suspense fallback={<div className="flex items-center justify-center h-32"><div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>}>
          <IntegrationsContent />
        </React.Suspense>
      )}

      {/* Users Tab */}
      {activeTab === 'users' && isAdmin && (
        <div className="max-w-2xl space-y-6">
          {/* Change Password */}
          <div className="bg-card border border-border rounded-xl p-6">
            <form onSubmit={handleChangePassword}>
              <h3 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
                <Key className="w-5 h-5" /> Change Password
              </h3>
              <div className="space-y-3">
                <div>
                  <label htmlFor="current-password" className="block text-sm font-medium text-foreground mb-1">Current Password</label>
                  <input id="current-password" type="password" value={pwForm.current_password} onChange={e => setPwForm({...pwForm, current_password: e.target.value})} required
                    className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                </div>
                <div>
                  <label htmlFor="new-password" className="block text-sm font-medium text-foreground mb-1">New Password</label>
                  <input id="new-password" type="password" value={pwForm.new_password} onChange={e => setPwForm({...pwForm, new_password: e.target.value})} required minLength={12}
                    className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                </div>
                <div>
                  <label htmlFor="confirm-new-password" className="block text-sm font-medium text-foreground mb-1">Confirm New Password</label>
                  <input id="confirm-new-password" type="password" value={pwForm.confirm_password} onChange={e => setPwForm({...pwForm, confirm_password: e.target.value})} required minLength={6}
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
              </div>
            </form>
          </div>

          {/* User Management */}
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
              <p><span className="font-medium text-foreground">Admin:</span> Full access — settings, API keys, user management, audit logs</p>
              <p><span className="font-medium text-foreground">Supervisor:</span> Manage pilots, vehicles, certifications, approve flights</p>
              <p><span className="font-medium text-foreground">Pilot:</span> Create flights, missions, training logs, maintenance, upload photos/docs</p>
              <p><span className="font-medium text-foreground">Viewer:</span> Read-only access to all data and reports</p>
            </div>

            {/* Add user form */}
            {showAddUser && (
              <form onSubmit={handleAddUser} className="mb-4 p-4 bg-muted/20 rounded-lg border border-border space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label htmlFor="username" className="block text-sm font-medium text-foreground mb-1">Username</label>
                    <input id="username" type="text" value={newUser.username} onChange={e => setNewUser({...newUser, username: e.target.value})} required
                      className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                  </div>
                  <div>
                    <label htmlFor="display-name" className="block text-sm font-medium text-foreground mb-1">Display Name</label>
                    <input id="display-name" type="text" value={newUser.display_name} onChange={e => setNewUser({...newUser, display_name: e.target.value})} required
                      className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                  </div>
                  <div>
                    <label htmlFor="password" className="block text-sm font-medium text-foreground mb-1">Password</label>
                    <input id="password" type="password" value={newUser.password} onChange={e => setNewUser({...newUser, password: e.target.value})} required minLength={6}
                      className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                    <p className="text-xs text-muted-foreground mt-2">Username and password are case-sensitive.</p>
                  </div>
                  <div>
                    <label htmlFor="role" className="block text-sm font-medium text-foreground mb-1">Role</label>
                    <select id="role" value={newUser.role} onChange={e => setNewUser({...newUser, role: e.target.value})}
                      className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
                      <option value="admin">Admin</option>
                      <option value="supervisor">Supervisor</option>
                      <option value="pilot">Pilot</option>
                      <option value="viewer">Viewer</option>
                    </select>
                  </div>
                  <div className="sm:col-span-2">
                    <label htmlFor="link-to-pilot" className="block text-sm font-medium text-foreground mb-1">Link to Pilot</label>
                    <select id="link-to-pilot" value={newUser.pilot_id} onChange={e => setNewUser({...newUser, pilot_id: e.target.value})}
                      className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
                      <option value="">-- No pilot linked --</option>
                      {sortPilotsActiveFirst(pilots).map(p => (
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
                          <option value="supervisor">Supervisor</option>
                          <option value="pilot">Pilot</option>
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
                              <button onClick={() => openEditUser(u)} title="Edit user"
                                className="p-1.5 text-muted-foreground hover:text-foreground rounded hover:bg-accent/30">
                                <Edit2 className="w-3.5 h-3.5" />
                              </button>
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
        </div>
      )}

      {/* General Tab */}
      {activeTab !== 'integrations' && activeTab !== 'users' && (
      <div className="space-y-6 max-w-2xl">
      {/* Organization */}
      <div className="bg-card border border-border rounded-xl p-6">
        <h3 className="text-lg font-semibold text-foreground mb-4">Organization</h3>
        <div className="space-y-4">
          {field('Organization Name', 'org_name', 'text', 'Displayed on reports and exports')}

          {/* Logo Upload */}
          <div>
            <p className="block text-sm font-medium text-foreground mb-1">Organization Logo</p>
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

      {/* Certification Status Labels - Admin Only */}
      {isAdmin && (
        <div className="bg-card border border-border rounded-xl p-6">
          <h3 className="text-lg font-semibold text-foreground mb-1">Certification Status Labels</h3>
          <p className="text-sm text-muted-foreground mb-3">Customize the display names for certification statuses.</p>
          <div className="space-y-2">
            {['not_issued', 'pending', 'complete', 'active', 'expired', 'not_eligible'].map(status => (
              <div key={status} className="flex items-center gap-3">
                <span className="text-sm text-muted-foreground w-28 shrink-0">{status.replaceAll('_', ' ')}</span>
                <input
                  type="text"
                  defaultValue={certLabels[status] || ''}
                  placeholder={status.replaceAll('_', ' ')}
                  onBlur={e => setCertLabels(prev => ({ ...prev, [status]: e.target.value }))}
                  className="flex-1 px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>
            ))}
          </div>
          <button
            onClick={async () => {
              setSavingCertLabels(true)
              try {
                await api.put('/settings/bulk', [{ key: 'cert_status_labels', value: JSON.stringify(certLabels) }])
                toast.success('Certification labels saved')
              } catch (err) { toast.error(err.message) }
              finally { setSavingCertLabels(false) }
            }}
            disabled={savingCertLabels}
            className="mt-4 flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50"
          >
            {savingCertLabels ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Save Labels
          </button>
        </div>
      )}

      {/* Weather Thresholds - Admin Only */}
      {isAdmin && (
        <div className="bg-card border border-border rounded-xl p-6">
          <h3 className="text-lg font-semibold text-foreground mb-1">Weather Thresholds</h3>
          <p className="text-sm text-muted-foreground mb-3">Customize weather advisory thresholds for GO / CAUTION / NO-GO.</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {[
              { key: 'wind_sustained_go', label: 'Wind Sustained GO (mph)', default: 15 },
              { key: 'wind_sustained_caution', label: 'Wind Sustained CAUTION (mph)', default: 25 },
              { key: 'wind_gusts_go', label: 'Wind Gusts GO (mph)', default: 20 },
              { key: 'wind_gusts_caution', label: 'Wind Gusts CAUTION (mph)', default: 30 },
              { key: 'visibility_go', label: 'Visibility GO (miles)', default: 3 },
              { key: 'visibility_caution', label: 'Visibility CAUTION (miles)', default: 1 },
              { key: 'ceiling_go', label: 'Ceiling GO (ft AGL)', default: 500 },
              { key: 'ceiling_caution', label: 'Ceiling CAUTION (ft AGL)', default: 200 },
              { key: 'temp_low_go', label: 'Temp Low GO (F)', default: 32 },
              { key: 'temp_low_caution', label: 'Temp Low CAUTION (F)', default: 20 },
              { key: 'temp_high_go', label: 'Temp High GO (F)', default: 100 },
              { key: 'precip_caution', label: 'Precip CAUTION (in)', default: 0.01 },
            ].map(t => (
              <div key={t.key}>
                <label htmlFor={`weather-${t.key}`} className="block text-xs text-muted-foreground mb-1">{t.label}</label>
                <input
                  id={`weather-${t.key}`}
                  key={`weather-${t.key}-${weatherThresholds[t.key] ?? t.default}`}
                  type="number"
                  step="any"
                  defaultValue={weatherThresholds[t.key] ?? t.default}
                  onBlur={e => {
                    const val = Number.parseFloat(e.target.value)
                    if (!Number.isNaN(val)) setWeatherThresholds(prev => ({ ...prev, [t.key]: val }))
                  }}
                  className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>
            ))}
          </div>
          <div className="mt-4 flex items-center gap-3">
            <button
              onClick={async () => {
                setSavingWeatherThresholds(true)
                try {
                  await api.put('/settings/bulk', [{ key: 'weather_thresholds', value: JSON.stringify(weatherThresholds) }])
                  toast.success('Weather thresholds saved')
                } catch (err) { toast.error(err.message) }
                finally { setSavingWeatherThresholds(false) }
              }}
              disabled={savingWeatherThresholds}
              className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50"
            >
              {savingWeatherThresholds ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              Save Thresholds
            </button>
            <button
              onClick={async () => {
                const defaults = {
                  wind_sustained_go: 15, wind_sustained_caution: 25,
                  wind_gusts_go: 20, wind_gusts_caution: 30,
                  visibility_go: 3, visibility_caution: 1,
                  ceiling_go: 500, ceiling_caution: 200,
                  temp_low_go: 32, temp_low_caution: 20,
                  temp_high_go: 100, precip_caution: 0.01,
                }
                setWeatherThresholds(defaults)
                try {
                  await api.put('/settings/bulk', [{ key: 'weather_thresholds', value: JSON.stringify(defaults) }])
                  toast.success('Weather thresholds reset to defaults')
                } catch (err) { toast.error(err.message) }
              }}
              className="flex items-center gap-2 px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm font-medium hover:opacity-90"
            >
              Reset to Defaults
            </button>
          </div>
        </div>
      )}

      {/* Mission/Flight Purposes - Admin Only */}
      {isAdmin && (
        <div className="bg-card border border-border rounded-xl p-6">
          <h3 className="text-lg font-semibold text-foreground mb-1">Mission / Flight Purposes</h3>
          <p className="text-sm text-muted-foreground mb-3">Add or remove purpose options for missions and flights.</p>
          <div className="flex flex-wrap gap-2 mb-3">
            {missionPurposes.map((p) => (
              <div key={p} className="flex items-center gap-1 px-3 py-1 bg-secondary border border-border rounded-full text-sm text-foreground">
                <span>{p}</span>
                <button onClick={() => setMissionPurposes(prev => prev.filter(item => item !== p))} className="text-muted-foreground hover:text-destructive ml-1">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
            {missionPurposes.length === 0 && <p className="text-sm text-muted-foreground">No custom purposes configured. Default list will be used.</p>}
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              value={newPurpose}
              onChange={e => setNewPurpose(e.target.value)}
              onKeyDown={handlePurposeKeyDown}
              placeholder="Add a purpose..."
              className="flex-1 px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <button
              onClick={() => {
                if (newPurpose.trim()) {
                  setMissionPurposes(prev => [...prev, newPurpose.trim()])
                  setNewPurpose('')
                }
              }}
              className="px-3 py-2 bg-secondary border border-border rounded-lg text-sm text-foreground hover:bg-accent/30"
            >
              Add
            </button>
          </div>
          <button
            onClick={async () => {
              setSavingPurposes(true)
              try {
                await api.put('/settings/bulk', [{ key: 'mission_purposes', value: JSON.stringify(missionPurposes) }])
                toast.success('Mission purposes saved')
              } catch (err) { toast.error(err.message) }
              finally { setSavingPurposes(false) }
            }}
            disabled={savingPurposes}
            className="mt-4 flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50"
          >
            {savingPurposes ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Save Purposes
          </button>
        </div>
      )}

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
        </div>
      )}

      {/* API Documentation */}
      <div className="bg-card border border-border rounded-xl p-6">
        <h3 className="text-lg font-semibold text-foreground mb-2">API Documentation</h3>
        <p className="text-sm text-muted-foreground mb-3">Browse the interactive API documentation powered by Swagger UI.</p>
        <a href="/docs" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 text-primary hover:underline text-sm">
          <ExternalLink className="w-4 h-4" /> Open API Documentation (Swagger UI)
        </a>
      </div>

      {/* Sidebar Configuration - Admin Only */}
      {isAdmin && sidebarItems.length > 0 && (
        <div className="bg-card border border-border rounded-xl p-6">
          <h3 className="text-lg font-semibold text-foreground mb-1">Sidebar Configuration</h3>
          <p className="text-sm text-muted-foreground mb-4">Toggle visibility and reorder sidebar navigation items.</p>
          <div className="space-y-1">
            {sidebarItems.map((item, idx) => (
              <div key={item.to} className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-muted/30">
                <div className="flex flex-col gap-0.5">
                  <button
                    onClick={() => {
                      if (idx === 0) return
                      const items = [...sidebarItems]
                      ;[items[idx - 1], items[idx]] = [items[idx], items[idx - 1]]
                      items.forEach((it, i) => { it.order = i })
                      setSidebarItems(items)
                    }}
                    disabled={idx === 0}
                    className="p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-30"
                  >
                    <ChevronUp className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => {
                      if (idx === sidebarItems.length - 1) return
                      const items = [...sidebarItems]
                      ;[items[idx], items[idx + 1]] = [items[idx + 1], items[idx]]
                      items.forEach((it, i) => { it.order = i })
                      setSidebarItems(items)
                    }}
                    disabled={idx === sidebarItems.length - 1}
                    className="p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-30"
                  >
                    <ChevronDown className="w-3.5 h-3.5" />
                  </button>
                </div>
                <label className="flex items-center gap-3 flex-1 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={item.visible}
                    onChange={() => {
                      const items = [...sidebarItems]
                      items[idx] = { ...items[idx], visible: !items[idx].visible }
                      setSidebarItems(items)
                    }}
                    className="w-4 h-4 rounded border-border text-primary focus:ring-ring"
                  />
                  <span className={`text-sm ${item.visible ? 'text-foreground' : 'text-muted-foreground line-through'}`}>
                    {item.label}
                  </span>
                  <span className="text-xs text-muted-foreground ml-auto">{item.to}</span>
                </label>
              </div>
            ))}
          </div>
          <button
            onClick={async () => {
              setSavingSidebar(true)
              try {
                const config = sidebarItems.map((item, i) => ({ to: item.to, label: item.label, visible: item.visible, order: i }))
                await api.put('/settings/bulk', [{ key: 'sidebar_config', value: JSON.stringify(config) }])
                toast.success('Sidebar configuration saved')
              } catch (err) {
                toast.error(err.message)
              } finally {
                setSavingSidebar(false)
              }
            }}
            disabled={savingSidebar}
            className="mt-4 flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50"
          >
            {savingSidebar ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Save Sidebar Config
          </button>
        </div>
      )}

      </div>
      )}

      {/* Edit User Modal */}
      {editUser && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <button className="absolute inset-0 bg-transparent cursor-default" onClick={() => setEditUser(null)} aria-label="Close dialog" />
          <div className="relative bg-card border border-border rounded-xl p-6 w-full max-w-md shadow-xl">
            <h2 className="text-lg font-semibold text-foreground mb-4">Edit User: {editUser.username}</h2>
            <div className="space-y-3">
              <div>
                <label htmlFor="display-name-1" className="block text-sm font-medium text-foreground mb-1">Display Name</label>
                <input id="display-name-1" type="text" value={editUserForm.display_name} onChange={e => setEditUserForm({...editUserForm, display_name: e.target.value})}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
              </div>
              <div>
                <label htmlFor="role-1" className="block text-sm font-medium text-foreground mb-1">Role</label>
                <select id="role-1" value={editUserForm.role} onChange={e => setEditUserForm({...editUserForm, role: e.target.value})}
                  disabled={editUser.id === currentUser?.id}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm disabled:opacity-50">
                  <option value="admin">Admin</option>
                  <option value="supervisor">Supervisor</option>
                  <option value="pilot">Pilot</option>
                  <option value="viewer">Viewer</option>
                </select>
              </div>
              <div>
                <label htmlFor="link-to-pilot-1" className="block text-sm font-medium text-foreground mb-1">Link to Pilot</label>
                <select id="link-to-pilot-1" value={editUserForm.pilot_id} onChange={e => setEditUserForm({...editUserForm, pilot_id: e.target.value})}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
                  <option value="">-- No pilot linked --</option>
                  {sortPilotsActiveFirst(pilots).map(p => (
                    <option key={p.id} value={p.id}>{p.full_name}{p.badge_number ? ` (Badge: ${p.badge_number})` : ''}</option>
                  ))}
                </select>
              </div>
              <div className="flex gap-2 pt-2">
                <button onClick={handleSaveEditUser} disabled={savingEditUser}
                  className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2">
                  {savingEditUser ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Save'}
                </button>
                <button onClick={() => setEditUser(null)}
                  className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90">
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog {...confirmProps} />
    </div>
  )
}
