import React, { useState, useEffect, useCallback } from 'react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { Modal } from '@/components/ui/Modal'
import { useConfirm } from '@/hooks/useConfirm'
import { sortPilotsActiveFirst } from '@/lib/formatters'
import { DEFAULT_ORG_LOCATION } from '@/lib/location'
import { TIMEZONES } from '@/lib/utils'
import { Save, Loader2, Upload, Download, UserPlus, Key, Trash2, Shield, Image as ImageIcon, ChevronUp, ChevronDown, ExternalLink, X, Edit2, MapPin, Search, GripVertical } from 'lucide-react'

const IntegrationsContent = React.lazy(() => import('@/pages/IntegrationsPage'))
const ApiTokensSection = React.lazy(() => import('@/components/ApiTokensSection'))

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState('general')
  const [settings, setSettings] = useState({})
  const [saving, setSaving] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [includeTelemetry, setIncludeTelemetry] = useState(false)

  // Automated backup state
  const [backupStatus, setBackupStatus] = useState(null)
  const [backupForm, setBackupForm] = useState({ enabled: true, retention: 7, hour: 3 })
  const [savingBackup, setSavingBackup] = useState(false)
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
  const [showSidebarGroups, setShowSidebarGroups] = useState(true)
  const [draggedIdx, setDraggedIdx] = useState(null)

  // Currency rules state
  const [currencyRules, setCurrencyRules] = useState([])
  const [editingRule, setEditingRule] = useState(null)
  const [savingRule, setSavingRule] = useState(false)
  const [ruleForm, setRuleForm] = useState({
    name: '', description: '', vehicle_model: '',
    required_hours: 5, period_days: 90,
    required_flights: '', is_active: true,
  })

  // Certification status labels state
  const [certLabels, setCertLabels] = useState({})
  const [savingCertLabels, setSavingCertLabels] = useState(false)

  // Weather thresholds state
  const [weatherThresholds, setWeatherThresholds] = useState({})
  const [savingWeatherThresholds, setSavingWeatherThresholds] = useState(false)

  // Mission purposes state
  const [purposeRows, setPurposeRows] = useState([])
  const [newPurpose, setNewPurpose] = useState('')
  const [savingPurposes, setSavingPurposes] = useState(false)

  // Drone location places state
  const [dronePlaces, setDronePlaces] = useState(['North', 'Central', 'South'])

  // Default location (org) state
  const [addressQuery, setAddressQuery] = useState('')
  const [geoResult, setGeoResult] = useState(null)
  const [geoLoading, setGeoLoading] = useState(false)
  const [savingLocation, setSavingLocation] = useState(false)

  const handleGeocodeSearch = async () => {
    const q = addressQuery.trim()
    if (q.length < 2) { toast.error('Enter an address to search'); return }
    setGeoLoading(true)
    try {
      const result = await api.get('/geocode?q=' + encodeURIComponent(q))
      setGeoResult(result)
    } catch (err) {
      setGeoResult(null)
      toast.error(err.message?.includes('No match') ? 'No match for that address' : 'Lookup failed')
    } finally {
      setGeoLoading(false)
    }
  }

  const handleSaveLocation = async () => {
    if (!geoResult) return
    setSavingLocation(true)
    try {
      await api.put('/settings/bulk', [
        { key: 'org_default_lat', value: String(geoResult.lat) },
        { key: 'org_default_lon', value: String(geoResult.lon) },
        { key: 'org_location_name', value: geoResult.display_name },
      ])
      setSettings(prev => ({
        ...prev,
        org_default_lat: String(geoResult.lat),
        org_default_lon: String(geoResult.lon),
        org_location_name: geoResult.display_name,
      }))
      setGeoResult(null)
      setAddressQuery('')
      toast.success('Default location saved')
    } catch (err) {
      toast.error(err.message)
    } finally {
      setSavingLocation(false)
    }
  }

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

  // The flight_purposes table is the source of truth: it is what the Flights
  // and Flight-detail dropdowns read. Editing here used to write a separate
  // mission_purposes setting instead, so removing an option changed nothing on
  // the flight pages.
  const loadPurposes = useCallback(() => {
    api.get('/flights/purposes/usage')
      .then(rows => { if (Array.isArray(rows)) setPurposeRows(rows) })
      .catch(() => {})
  }, [])

  const loadBackupStatus = () => {
    if (!isAdmin) return
    api.get('/backup/status').then(status => {
      setBackupStatus(status)
      setBackupForm({
        enabled: status.enabled !== false,
        retention: status.retention ?? 7,
        hour: status.hour ?? 3,
      })
    }).catch(() => {})
  }

  useEffect(() => { loadBackupStatus() }, [isAdmin]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleSaveBackupSettings = async () => {
    setSavingBackup(true)
    try {
      await api.put('/settings/bulk', [
        { key: 'backup_enabled', value: backupForm.enabled ? 'true' : 'false' },
        { key: 'backup_retention', value: String(backupForm.retention) },
        { key: 'backup_hour', value: String(backupForm.hour) },
      ])
      toast.success('Backup settings saved')
      loadBackupStatus()
    } catch (err) {
      toast.error(err.message)
    } finally {
      setSavingBackup(false)
    }
  }

  const addPurpose = async () => {
    const name = newPurpose.trim()
    if (!name) return
    setSavingPurposes(true)
    try {
      await api.post('/flights/purposes', { name })
      setNewPurpose('')
      loadPurposes()
      toast.success(`Added "${name}"`)
    } catch (err) {
      // The API rejects names differing only in case, which is how "CPTED" and
      // "CPTEd" both ended up in the list; surface that reason rather than
      // failing silently.
      toast.error(err.message)
    } finally {
      setSavingPurposes(false)
    }
  }

  const handlePurposeKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      addPurpose()
    }
  }

  const requestPurposeDelete = (purpose) => {
    const flights = purpose.flight_count || 0
    const missions = purpose.mission_count || 0
    const parts = []
    if (flights) parts.push(`${flights} flight${flights === 1 ? '' : 's'} will have their purpose cleared and will show as "—"`)
    if (missions) parts.push(`${missions} mission log${missions === 1 ? '' : 's'} will keep "${purpose.name}" as their written reason`)

    requestConfirm({
      title: `Delete "${purpose.name}"?`,
      message: parts.length
        ? `${parts.join('. ')}. This cannot be undone.`
        : `Nothing currently uses "${purpose.name}", so no records will change.`,
      confirmLabel: 'Delete purpose',
      confirmVariant: 'destructive',
      onConfirm: async () => {
        try {
          const res = await api.delete(`/flights/purposes/${purpose.id}`)
          loadPurposes()
          toast.success(
            res?.flights_cleared
              ? `Deleted "${purpose.name}" and cleared it from ${res.flights_cleared} flight(s)`
              : `Deleted "${purpose.name}"`
          )
        } catch (err) {
          toast.error(err.message)
        }
      },
    })
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
      // Load sidebar group-display toggle (defaults to true if unset)
      if (map.sidebar_show_groups !== undefined) {
        setShowSidebarGroups(map.sidebar_show_groups !== 'false')
      }
      // Load cert status labels
      if (map.cert_status_labels) {
        try { setCertLabels(JSON.parse(map.cert_status_labels)) } catch { /* invalid JSON */ }
      }
      // Load weather thresholds
      if (map.weather_thresholds) {
        try { setWeatherThresholds(JSON.parse(map.weather_thresholds)) } catch { /* invalid JSON */ }
      }
      loadPurposes()
      // Load drone location places
      if (map.drone_location_places) {
        try { const j = JSON.parse(map.drone_location_places); if (Array.isArray(j)) setDronePlaces(j) } catch { /* keep default */ }
      }
    }).catch(console.error)
    if (isAdmin) {
      api.get('/auth/users').then(setUsers).catch(console.error)
      api.get('/pilots').then(setPilots).catch(console.error)
      api.get('/currency/rules').then(setCurrencyRules).catch(console.error)
    }
  }, [isAdmin])

  const openNewRule = () => {
    setRuleForm({ name: '', description: '', vehicle_model: '', required_hours: 5, period_days: 90, required_flights: '', is_active: true })
    setEditingRule({})
  }

  const openEditRule = (rule) => {
    setRuleForm({
      name: rule.name || '',
      description: rule.description || '',
      vehicle_model: rule.vehicle_model || '',
      required_hours: rule.required_hours,
      period_days: rule.period_days,
      required_flights: rule.required_flights ?? '',
      is_active: rule.is_active,
    })
    setEditingRule(rule)
  }

  const handleSaveRule = async () => {
    if (!ruleForm.name?.trim()) { toast.error('Name is required'); return }
    const hrs = Number.parseFloat(ruleForm.required_hours)
    const days = Number.parseInt(ruleForm.period_days, 10)
    if (!hrs || hrs <= 0) { toast.error('Required hours must be > 0'); return }
    if (!days || days <= 0) { toast.error('Period days must be > 0'); return }
    setSavingRule(true)
    try {
      const payload = {
        name: ruleForm.name.trim(),
        description: ruleForm.description?.trim() || null,
        vehicle_model: ruleForm.vehicle_model?.trim() || null,
        required_hours: hrs,
        period_days: days,
        required_flights: ruleForm.required_flights === '' || ruleForm.required_flights == null ? null : Number.parseInt(ruleForm.required_flights, 10),
        is_active: ruleForm.is_active,
      }
      if (editingRule?.id) {
        await api.patch(`/currency/rules/${editingRule.id}`, payload)
      } else {
        await api.post('/currency/rules', payload)
      }
      setCurrencyRules(await api.get('/currency/rules'))
      setEditingRule(null)
      toast.success(editingRule?.id ? 'Rule updated' : 'Rule created')
    } catch (err) {
      toast.error(err.message)
    } finally {
      setSavingRule(false)
    }
  }

  const handleDeleteRule = (rule) => {
    requestConfirm({
      title: 'Delete currency rule?',
      message: `Delete "${rule.name}"? Pilot currency status calculations will stop using this rule.`,
      confirmLabel: 'Delete',
      confirmVariant: 'danger',
      onConfirm: async () => {
        try {
          await api.delete(`/currency/rules/${rule.id}`)
          setCurrencyRules(prev => prev.filter(r => r.id !== rule.id))
          toast.success('Rule deleted')
        } catch (err) {
          toast.error(err.message)
        }
      },
    })
  }

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
      toast.success('Settings saved!')
    } catch (err) {
      toast.error(err.message)
    } finally {
      setSaving(false)
    }
  }

  // Use refs for settings inputs to avoid re-renders on keystroke/paste
  const inputRefs = React.useRef({})

  const PASSWORD_KEYS = new Set(['skydio_api_token'])
  const REDACTED_MARKER = '********'

  const gatherInputs = () => {
    const gathered = { ...settings }
    for (const [key, ref] of Object.entries(inputRefs.current)) {
      if (!ref) continue
      // Skip password fields where user didn't type anything new
      if (PASSWORD_KEYS.has(key) && ref.value === '') continue
      gathered[key] = ref.value
    }
    // Never echo the redaction marker back to the server: drop any key whose
    // current value is still the marker (e.g. a secret GET /settings redacted
    // and the General tab renders no input to override).
    for (const key of Object.keys(gathered)) {
      if (gathered[key] === REDACTED_MARKER) delete gathered[key]
    }
    return gathered
  }

  const field = (label, key, type = 'text', description = '') => {
    const isPassword = type === 'password'
    const hasMaskedValue = isPassword && settings[key]?.includes('********')
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
    ...(isAdmin ? [{ id: 'api-tokens', label: 'API Tokens' }] : []),
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

      {/* API Tokens Tab */}
      {activeTab === 'api-tokens' && isAdmin && (
        <React.Suspense fallback={<div className="flex items-center justify-center h-32"><div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>}>
          <ApiTokensSection />
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

          <div>
            <label htmlFor="setting-display_timezone" className="block text-sm font-medium text-foreground mb-1">Time Zone</label>
            <p className="text-xs text-muted-foreground mb-1.5">All flight times display in this zone. Stored data stays in UTC.</p>
            <select
              id="setting-display_timezone"
              ref={el => { inputRefs.current['display_timezone'] = el }}
              key={`display_timezone-${settings.display_timezone === undefined ? 'loading' : 'loaded'}`}
              defaultValue={settings.display_timezone || 'America/Chicago'}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              disabled={!isAdmin}
              onInput={() => setHasUnsavedChanges(true)}
            >
              {TIMEZONES.map(tz => <option key={tz} value={tz}>{tz}</option>)}
            </select>
          </div>

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
          <p className="text-sm text-muted-foreground mb-3">
            These are the options offered on flights and missions. Changes apply immediately.
          </p>
          <div className="flex flex-wrap gap-2 mb-3">
            {purposeRows.map((p) => (
              <div key={p.id} className="flex items-center gap-1.5 px-3 py-1 bg-secondary border border-border rounded-full text-sm text-foreground">
                <span>{p.name}</span>
                {(p.flight_count > 0 || p.mission_count > 0) && (
                  <span className="text-xs text-muted-foreground">
                    ({p.flight_count + p.mission_count} in use)
                  </span>
                )}
                <button
                  aria-label={`Delete purpose ${p.name}`}
                  onClick={() => requestPurposeDelete(p)}
                  className="text-muted-foreground hover:text-destructive ml-1"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
            {purposeRows.length === 0 && <p className="text-sm text-muted-foreground">No purposes configured.</p>}
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
              onClick={addPurpose}
              disabled={savingPurposes}
              className="px-3 py-2 bg-secondary border border-border rounded-lg text-sm text-foreground hover:bg-accent/30 disabled:opacity-50"
            >
              Add
            </button>
          </div>
        </div>
      )}

      {/* Drone Locations - Admin Only */}
      {isAdmin && (
        <div className="bg-card border border-border rounded-xl p-6">
          <h2 className="text-lg font-semibold text-foreground mb-1">Drone Locations</h2>
          <p className="text-xs text-muted-foreground mb-3">Named places shown in the dashboard location dropdown (pilots are always available too).</p>
          <div className="space-y-2 mb-3">
            {dronePlaces.map((pl, i) => (
              <div key={i} className="flex gap-2">
                <input
                  className="flex-1 px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm"
                  value={pl}
                  onChange={(e) => setDronePlaces(dronePlaces.map((x, xi) => xi === i ? e.target.value : x))}
                />
                <button type="button" className="px-3 py-2 text-sm text-red-400 hover:bg-red-500/10 rounded-lg"
                  onClick={() => setDronePlaces(dronePlaces.filter((_, xi) => xi !== i))}>Remove</button>
              </div>
            ))}
          </div>
          <div className="flex gap-2">
            <button type="button" className="px-3 py-2 text-sm bg-secondary border border-border rounded-lg text-foreground"
              onClick={() => setDronePlaces([...dronePlaces, ''])}>Add place</button>
            <button type="button" className="px-3 py-2 text-sm bg-primary text-primary-foreground rounded-lg"
              onClick={async () => {
                const cleaned = dronePlaces.map(s => s.trim()).filter(Boolean)
                try {
                  await api.put('/settings/bulk', [{ key: 'drone_location_places', value: JSON.stringify(cleaned) }])
                  setDronePlaces(cleaned)
                  toast.success('Locations saved')
                } catch (err) { toast.error(err.message) }
              }}>Save locations</button>
          </div>
        </div>
      )}

      {/* Default Location - Admin Only */}
      {isAdmin && (
        <div className="bg-card border border-border rounded-xl p-6">
          <h3 className="text-lg font-semibold text-foreground mb-1 flex items-center gap-2">
            <MapPin className="w-5 h-5" /> Default Location
          </h3>
          <p className="text-sm text-muted-foreground mb-3">
            Organization default used by Weather, Airspace, and the dashboard weather tile. Search an address to set it.
          </p>
          <div className="mb-3 p-3 bg-muted/30 rounded-lg text-sm">
            {settings.org_default_lat && settings.org_default_lon ? (
              <>
                <p className="text-foreground">{settings.org_location_name || 'Saved location'}</p>
                <p className="text-xs text-muted-foreground">{settings.org_default_lat}, {settings.org_default_lon}</p>
              </>
            ) : (
              <p className="text-muted-foreground">Defaults to the White House ({DEFAULT_ORG_LOCATION.lat}, {DEFAULT_ORG_LOCATION.lon}).</p>
            )}
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              value={addressQuery}
              onChange={e => setAddressQuery(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); handleGeocodeSearch() } }}
              placeholder="Enter an address or place..."
              className="flex-1 px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <button
              type="button"
              onClick={handleGeocodeSearch}
              disabled={geoLoading}
              className="flex items-center gap-2 px-4 py-2 bg-secondary border border-border rounded-lg text-sm text-foreground hover:bg-accent/30 disabled:opacity-50"
            >
              {geoLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
              Search
            </button>
          </div>
          {geoResult && (
            <div className="mt-3 p-3 bg-muted/20 border border-border rounded-lg space-y-2">
              <p className="text-sm text-foreground">{geoResult.display_name}</p>
              <p className="text-xs text-muted-foreground">{geoResult.lat}, {geoResult.lon}</p>
              <button
                type="button"
                onClick={handleSaveLocation}
                disabled={savingLocation}
                className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50"
              >
                {savingLocation ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                Save as Default Location
              </button>
            </div>
          )}
        </div>
      )}

      {/* Backup Export - Admin Only */}
      {isAdmin && (
        <div className="bg-card border border-border rounded-xl p-6">
          <h3 className="text-lg font-semibold text-foreground mb-1">Backup & Restore</h3>
          <p className="text-sm text-muted-foreground mb-4">
            Download a complete backup of your database, settings, and uploaded files as a ZIP archive. To restore, use the Setup page on a fresh install.
          </p>
          <label className="flex items-center gap-2 mb-4 cursor-pointer">
            <input type="checkbox" checked={includeTelemetry} onChange={e => setIncludeTelemetry(e.target.checked)} className="rounded border-border" />
            <span className="text-sm text-foreground">Include telemetry data</span>
            <span className="text-xs text-muted-foreground">(flight GPS/altitude/speed — can be very large)</span>
          </label>
          <button
            onClick={async () => {
              setExporting(true)
              try {
                // No timeout: build_backup_archive assembles the entire zip,
                // every table plus every uploaded file, before the first byte
                // is sent, so the 30s default aborted any sizeable backup.
                // The restore path in SetupPage does the same for the same reason.
                await api.download(`/backup/export?include_telemetry=${includeTelemetry}`, { timeout: 0 })
                toast.success('Backup exported successfully')
              } catch (err) { toast.error(err.message) }
              finally { setExporting(false) }
            }}
            disabled={exporting}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50"
          >
            {exporting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
            {exporting ? 'Exporting...' : 'Export Backup'}
          </button>
        </div>
      )}

      {/* Automated Backups - Admin Only */}
      {isAdmin && (
        <div className="bg-card border border-border rounded-xl p-6">
          <h3 className="text-lg font-semibold text-foreground mb-1">Automated Backups</h3>
          <p className="text-sm text-muted-foreground mb-4">
            Keeps the last N full backups (DB + uploads) under /app/data/backups.
            Schedule changes (enable/time) take effect after the next app restart.
          </p>

          <label className="flex items-center gap-2 mb-4 cursor-pointer">
            <input
              type="checkbox"
              checked={backupForm.enabled}
              onChange={e => setBackupForm(f => ({ ...f, enabled: e.target.checked }))}
              className="rounded border-border"
            />
            <span className="text-sm text-foreground">Enable daily automated backups</span>
          </label>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
            <div>
              <label htmlFor="backup-retention" className="block text-sm font-medium text-foreground mb-1">Retention (backups to keep)</label>
              <input
                id="backup-retention"
                type="number"
                min="1"
                value={backupForm.retention}
                onChange={e => setBackupForm(f => ({ ...f, retention: e.target.value }))}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
            <div>
              <label htmlFor="backup-hour" className="block text-sm font-medium text-foreground mb-1">Run at hour (24h)</label>
              <select
                id="backup-hour"
                value={backupForm.hour}
                onChange={e => setBackupForm(f => ({ ...f, hour: Number.parseInt(e.target.value, 10) }))}
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                {Array.from({ length: 24 }, (_, h) => (
                  <option key={h} value={h}>{String(h).padStart(2, '0')}:00</option>
                ))}
              </select>
            </div>
          </div>

          <button
            onClick={handleSaveBackupSettings}
            disabled={savingBackup}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50"
          >
            {savingBackup ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Save Backup Settings
          </button>

          {backupStatus && (
            <div className="mt-4 p-3 bg-muted/20 border border-border rounded-lg text-sm space-y-1">
              <p className="text-foreground">
                Stored backups: <span className="font-medium">{backupStatus.count}</span>
              </p>
              <p className="text-muted-foreground">
                Last backup: {backupStatus.last_backup_at
                  ? new Date(backupStatus.last_backup_at).toLocaleString()
                  : 'never'}
              </p>
              {backupStatus.last_backup_result && (
                <p className="text-muted-foreground">
                  Result: {backupStatus.last_backup_result.ok
                    ? `OK (${backupStatus.last_backup_result.file}, ${backupStatus.last_backup_result.bytes} bytes)`
                    : `Failed — ${backupStatus.last_backup_result.error || 'unknown error'}`}
                </p>
              )}
            </div>
          )}
        </div>
      )}

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

      {/* API Documentation */}
      <div className="bg-card border border-border rounded-xl p-6">
        <h3 className="text-lg font-semibold text-foreground mb-2">API Documentation</h3>
        <p className="text-sm text-muted-foreground mb-3">Browse the interactive API documentation powered by Swagger UI.</p>
        <a href="/docs" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 text-primary hover:underline text-sm">
          <ExternalLink className="w-4 h-4" /> Open API Documentation (Swagger UI)
        </a>
      </div>

      {/* Currency Rules - Admin Only */}
      {isAdmin && (
        <div className="bg-card border border-border rounded-xl p-6">
          <div className="flex items-center justify-between mb-1">
            <h3 className="text-lg font-semibold text-foreground">Currency Rules</h3>
            <button
              onClick={openNewRule}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-medium hover:opacity-90"
            >
              <UserPlus className="w-3.5 h-3.5" /> New Rule
            </button>
          </div>
          <p className="text-sm text-muted-foreground mb-4">
            Define how many flight hours (and optionally how many flights) pilots must log within a rolling period to stay current. Each rule appears on the pilot detail page's Currency Status section. Leave Vehicle Model blank to apply across all aircraft, or set it (e.g. "X10") to scope the rule to one type.
          </p>
          {currencyRules.length === 0 ? (
            <p className="text-sm text-muted-foreground italic px-3 py-4 bg-muted/30 rounded-lg text-center">
              No rules defined yet. Without rules, every pilot shows as "current" by default. Click <strong>New Rule</strong> to add your first one (e.g. "5 hours per 90 days").
            </p>
          ) : (
            <div className="space-y-2">
              {currencyRules.map(r => (
                <div key={r.id} className="flex items-center gap-3 px-3 py-2 bg-muted/30 rounded-lg">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground">
                      {r.name}
                      {!r.is_active && <span className="ml-2 text-xs text-muted-foreground">(inactive)</span>}
                    </p>
                    <p className="text-xs text-muted-foreground truncate">
                      {r.required_hours}h
                      {r.required_flights ? ` and ${r.required_flights} flights` : ''}
                      {' '}per {r.period_days} days
                      {r.vehicle_model && ` · ${r.vehicle_model} only`}
                      {r.description && ` · ${r.description}`}
                    </p>
                  </div>
                  <button
                    onClick={() => openEditRule(r)}
                    className="p-1.5 text-muted-foreground hover:text-foreground rounded hover:bg-accent/30"
                    title="Edit rule"
                  >
                    <Edit2 className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleDeleteRule(r)}
                    className="p-1.5 text-red-400 hover:text-red-300 rounded hover:bg-red-500/10"
                    title="Delete rule"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Sidebar Configuration - Admin Only */}
      {isAdmin && sidebarItems.length > 0 && (
        <div className="bg-card border border-border rounded-xl p-6">
          <h3 className="text-lg font-semibold text-foreground mb-1">Sidebar Configuration</h3>
          <p className="text-sm text-muted-foreground mb-4">Toggle visibility and reorder sidebar navigation items.</p>
          <label className="flex items-center gap-3 px-3 py-2 mb-3 bg-muted/30 rounded-lg cursor-pointer">
            <input
              type="checkbox"
              checked={showSidebarGroups}
              onChange={() => setShowSidebarGroups(v => !v)}
              className="w-4 h-4 rounded border-border text-primary focus:ring-ring"
            />
            <span className="text-sm text-foreground flex-1">Show group headers (Overview, Flight Ops, etc.)</span>
            <span className="text-xs text-muted-foreground">{showSidebarGroups ? 'On' : 'Off'}</span>
          </label>
          <div className="space-y-1">
            {sidebarItems.map((item, idx) => (
              <div
                key={item.to}
                draggable
                onDragStart={() => setDraggedIdx(idx)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => {
                  if (draggedIdx === null || draggedIdx === idx) { setDraggedIdx(null); return }
                  const items = [...sidebarItems]
                  const [moved] = items.splice(draggedIdx, 1)
                  items.splice(idx, 0, moved)
                  items.forEach((it, i) => { it.order = i })
                  setSidebarItems(items)
                  setDraggedIdx(null)
                }}
                onDragEnd={() => setDraggedIdx(null)}
                className={`flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-muted/30 ${draggedIdx === idx ? 'opacity-50' : ''}`}
              >
                <GripVertical className="w-4 h-4 text-muted-foreground cursor-grab shrink-0" />
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
                await api.put('/settings/bulk', [
                  { key: 'sidebar_config', value: JSON.stringify(config) },
                  { key: 'sidebar_show_groups', value: showSidebarGroups ? 'true' : 'false' },
                ])
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

      {/* Currency Rule Modal */}
      {editingRule && (
        <Modal open onClose={() => setEditingRule(null)} title={editingRule.id ? 'Edit Currency Rule' : 'New Currency Rule'} className="max-w-md">
            <div className="space-y-3">
              <div>
                <label htmlFor="rule-name" className="block text-sm font-medium text-foreground mb-1">Name</label>
                <input
                  id="rule-name" type="text" value={ruleForm.name}
                  onChange={e => setRuleForm({ ...ruleForm, name: e.target.value })}
                  placeholder="e.g. Quarterly currency"
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>
              <div>
                <label htmlFor="rule-desc" className="block text-sm font-medium text-foreground mb-1">Description (optional)</label>
                <input
                  id="rule-desc" type="text" value={ruleForm.description}
                  onChange={e => setRuleForm({ ...ruleForm, description: e.target.value })}
                  placeholder="Short note shown next to the rule"
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>
              <div>
                <label htmlFor="rule-vmodel" className="block text-sm font-medium text-foreground mb-1">Vehicle model (optional)</label>
                <input
                  id="rule-vmodel" type="text" value={ruleForm.vehicle_model}
                  onChange={e => setRuleForm({ ...ruleForm, vehicle_model: e.target.value })}
                  placeholder="Leave blank for all aircraft"
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="rule-hours" className="block text-sm font-medium text-foreground mb-1">Required hours</label>
                  <input
                    id="rule-hours" type="number" step="0.5" min="0" value={ruleForm.required_hours}
                    onChange={e => setRuleForm({ ...ruleForm, required_hours: e.target.value })}
                    className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                </div>
                <div>
                  <label htmlFor="rule-days" className="block text-sm font-medium text-foreground mb-1">Period (days)</label>
                  <input
                    id="rule-days" type="number" min="1" value={ruleForm.period_days}
                    onChange={e => setRuleForm({ ...ruleForm, period_days: e.target.value })}
                    className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                </div>
              </div>
              <div>
                <label htmlFor="rule-flights" className="block text-sm font-medium text-foreground mb-1">Minimum flights (optional)</label>
                <input
                  id="rule-flights" type="number" min="0" value={ruleForm.required_flights}
                  onChange={e => setRuleForm({ ...ruleForm, required_flights: e.target.value })}
                  placeholder="Leave blank if only hours matter"
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox" checked={ruleForm.is_active}
                  onChange={() => setRuleForm({ ...ruleForm, is_active: !ruleForm.is_active })}
                  className="w-4 h-4 rounded border-border text-primary focus:ring-ring"
                />
                <span className="text-sm text-foreground">Active (include in pilot currency calculations)</span>
              </label>
              <div className="flex gap-2 pt-2">
                <button
                  onClick={handleSaveRule} disabled={savingRule}
                  className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {savingRule ? <Loader2 className="w-4 h-4 animate-spin" /> : (editingRule.id ? 'Save' : 'Create')}
                </button>
                <button
                  onClick={() => setEditingRule(null)}
                  className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90"
                >
                  Cancel
                </button>
              </div>
            </div>
        </Modal>
      )}

      {/* Edit User Modal */}
      {editUser && (
        <Modal open onClose={() => setEditUser(null)} title={`Edit User: ${editUser.username}`} className="max-w-md">
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
        </Modal>
      )}

      <ConfirmDialog {...confirmProps} />
    </div>
  )
}
