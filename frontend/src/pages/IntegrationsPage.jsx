/**
 * Integrations page for managing drone provider APIs, SMTP email,
 * ADS-B settings, and flight log imports.
 */
import { useState, useEffect } from 'react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import {
  Plug, RefreshCw, CheckCircle, XCircle, Upload, Loader2,
  Mail, ChevronDown, ChevronRight,
} from 'lucide-react'
import { QuadcopterIcon } from '@/components/icons/QuadcopterIcon'

/** Provider definitions with their status and required settings keys. */
const PROVIDERS = [
  {
    id: 'skydio',
    name: 'Skydio',
    description: 'Sync flights, vehicles, batteries, and telemetry from Skydio Cloud API.',
    icon: QuadcopterIcon,
    available: true,
    tokenKey: 'skydio_api_token',
    tokenIdKey: 'skydio_token_id',
  },
  {
    id: 'brinc',
    name: 'BRINC',
    description: 'Sync data from BRINC drone fleet management.',
    icon: QuadcopterIcon,
    available: false,
    comingSoon: true,
  },
]

function ProviderCard({ provider, settings, onSave, onTest, onSync }) {
  const [expanded, setExpanded] = useState(false)
  const [token, setToken] = useState('')
  const [tokenId, setTokenId] = useState('')
  const [testing, setTesting] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [syncingTelemetry, setSyncingTelemetry] = useState(false)
  const toast = useToast()

  useEffect(() => {
    if (provider.tokenKey && settings) {
      const t = settings.find(s => s.key === provider.tokenKey)
      const tid = settings.find(s => s.key === provider.tokenIdKey)
      if (t) setToken(t.value || '')
      if (tid) setTokenId(tid.value || '')
    }
  }, [settings, provider])

  // A masked token (e.g. "abc12345...xyz9") means it IS configured
  const isConnected = token && token.length > 0
  const Icon = provider.icon

  const handleTest = async () => {
    setTesting(true)
    try {
      const res = await api.post('/sync/test')
      if (res.ok) toast.success(`Connected to ${provider.name} successfully`)
      else toast.error(res.message || 'Connection failed')
    } catch (err) {
      toast.error(err.message)
    } finally {
      setTesting(false)
    }
  }

  const handleSync = async (full = false) => {
    setSyncing(true)
    try {
      const res = await api.post(`/sync/now?full=${full}`)
      toast.success(`Synced: ${res.flights_new} new flights, ${res.vehicles_synced} vehicles`)
    } catch (err) {
      toast.error(err.message)
    } finally {
      setSyncing(false)
    }
  }

  const handleSyncTelemetry = async () => {
    setSyncingTelemetry(true)
    try {
      const res = await api.post('/sync/telemetry')
      toast.success(`Telemetry synced for ${res.synced} flights (${res.remaining} remaining)`)
    } catch (err) {
      toast.error(err.message)
    } finally {
      setSyncingTelemetry(false)
    }
  }

  const handleSave = async () => {
    try {
      await api.put('/settings/bulk', [
        { key: provider.tokenKey, value: token },
        { key: provider.tokenIdKey, value: tokenId },
      ])
      toast.success('Credentials saved')
    } catch (err) {
      toast.error(err.message)
    }
  }

  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden">
      <button
        onClick={() => provider.available && setExpanded(!expanded)}
        className={`w-full flex items-center gap-4 p-4 text-left transition-colors ${provider.available ? 'hover:bg-muted/30 cursor-pointer' : 'opacity-60 cursor-default'}`}
      >
        <div className="w-10 h-10 rounded-xl bg-primary/15 flex items-center justify-center text-primary shrink-0">
          <Icon className="w-5 h-5" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-foreground">{provider.name}</h3>
            {provider.comingSoon && (
              <span className="px-2 py-0.5 text-xs rounded-full bg-muted text-muted-foreground">Coming Soon</span>
            )}
            {provider.available && isConnected && (
              <span className="px-2 py-0.5 text-xs rounded-full bg-emerald-500/15 text-emerald-400 flex items-center gap-1">
                <CheckCircle className="w-3 h-3" /> Connected
              </span>
            )}
            {provider.available && !isConnected && (
              <span className="px-2 py-0.5 text-xs rounded-full bg-muted text-muted-foreground flex items-center gap-1">
                <XCircle className="w-3 h-3" /> Not configured
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">{provider.description}</p>
        </div>
        {provider.available && (
          expanded ? <ChevronDown className="w-4 h-4 text-muted-foreground shrink-0" /> : <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0" />
        )}
      </button>

      {expanded && provider.available && (
        <div className="px-4 pb-4 space-y-3 border-t border-border pt-3">
          <div>
            <label htmlFor="api-token" className="block text-xs font-medium text-muted-foreground mb-1">API Token</label>
            <input id="api-token"
              type="password"
              value={token}
              onChange={e => setToken(e.target.value)}
              placeholder="Enter API token"
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          {provider.tokenIdKey && (
            <div>
              <label htmlFor="token-id" className="block text-xs font-medium text-muted-foreground mb-1">Token ID</label>
              <input id="token-id"
                type="text"
                value={tokenId}
                onChange={e => setTokenId(e.target.value)}
                placeholder="Enter Token ID"
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
          )}
          <div className="flex gap-2 flex-wrap">
            <button onClick={handleSave} className="px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90">
              Save Credentials
            </button>
            <button onClick={handleTest} disabled={testing} className="px-3 py-1.5 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90 flex items-center gap-1.5 disabled:opacity-50">
              {testing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle className="w-3.5 h-3.5" />} Test Connection
            </button>
            <button onClick={() => handleSync(false)} disabled={syncing} className="px-3 py-1.5 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90 flex items-center gap-1.5 disabled:opacity-50">
              {syncing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />} Sync Now
            </button>
            <button onClick={() => handleSync(true)} disabled={syncing} className="px-3 py-1.5 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90 flex items-center gap-1.5 disabled:opacity-50">
              <RefreshCw className="w-3.5 h-3.5" /> Full Sync
            </button>
            <button onClick={handleSyncTelemetry} disabled={syncingTelemetry} className="px-3 py-1.5 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90 flex items-center gap-1.5 disabled:opacity-50" title="Fetch detailed telemetry data for up to 10 flights at a time">
              {syncingTelemetry ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />} Sync Telemetry (10)
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function SmtpCard({ settings }) {
  const [expanded, setExpanded] = useState(false)
  const [form, setForm] = useState({
    smtp_host: '', smtp_port: '587', smtp_username: '', smtp_password: '',
    smtp_from_address: '', smtp_from_name: 'Drone Unit Manager', smtp_tls: 'true', smtp_enabled: 'false',
  })
  const [testing, setTesting] = useState(false)
  const toast = useToast()

  useEffect(() => {
    if (settings) {
      const vals = {}
      for (const s of settings) {
        if (s.key.startsWith('smtp_')) vals[s.key] = s.value || ''
      }
      setForm(prev => ({ ...prev, ...vals }))
    }
  }, [settings])

  const handleSave = async () => {
    try {
      const items = Object.entries(form).map(([key, value]) => ({ key, value }))
      await api.put('/settings/bulk', items)
      toast.success('SMTP settings saved')
    } catch (err) {
      toast.error(err.message)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    try {
      const res = await api.post('/settings/smtp/test')
      if (res.ok) toast.success(res.message)
      else toast.error(res.message || 'Test failed')
    } catch (err) {
      toast.error(err.message)
    } finally {
      setTesting(false)
    }
  }

  const isConfigured = form.smtp_host && form.smtp_from_address

  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden">
      <button onClick={() => setExpanded(!expanded)} className="w-full flex items-center gap-4 p-4 text-left hover:bg-muted/30 transition-colors">
        <div className="w-10 h-10 rounded-xl bg-blue-500/15 flex items-center justify-center text-blue-400 shrink-0">
          <Mail className="w-5 h-5" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-foreground">Email (SMTP)</h3>
            {isConfigured ? (
              <span className="px-2 py-0.5 text-xs rounded-full bg-emerald-500/15 text-emerald-400 flex items-center gap-1">
                <CheckCircle className="w-3 h-3" /> {form.smtp_enabled === 'true' ? 'Active' : 'Configured'}
              </span>
            ) : (
              <span className="px-2 py-0.5 text-xs rounded-full bg-muted text-muted-foreground">Not configured</span>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">SMTP server for email digest notifications.</p>
        </div>
        {expanded ? <ChevronDown className="w-4 h-4 text-muted-foreground shrink-0" /> : <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0" />}
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-border pt-3">
          <div className="flex items-center gap-3 mb-2">
            <span className="text-sm text-foreground">Enable Email Notifications</span>
            <button
              onClick={() => setForm({ ...form, smtp_enabled: form.smtp_enabled === 'true' ? 'false' : 'true' })}
              className={`w-10 h-5 rounded-full transition-colors ${form.smtp_enabled === 'true' ? 'bg-primary' : 'bg-muted'}`}
            >
              <div className={`w-4 h-4 bg-white rounded-full transition-transform ${form.smtp_enabled === 'true' ? 'translate-x-5' : 'translate-x-0.5'}`} />
            </button>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="smtp-host" className="block text-xs font-medium text-muted-foreground mb-1">SMTP Host</label>
              <input id="smtp-host" value={form.smtp_host} onChange={e => setForm({ ...form, smtp_host: e.target.value })} placeholder="smtp.gmail.com" className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
            <div>
              <label htmlFor="port" className="block text-xs font-medium text-muted-foreground mb-1">Port</label>
              <input id="port" value={form.smtp_port} onChange={e => setForm({ ...form, smtp_port: e.target.value })} placeholder="587" className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
            <div>
              <label htmlFor="username" className="block text-xs font-medium text-muted-foreground mb-1">Username</label>
              <input id="username" value={form.smtp_username} onChange={e => setForm({ ...form, smtp_username: e.target.value })} className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
            <div>
              <label htmlFor="password" className="block text-xs font-medium text-muted-foreground mb-1">Password</label>
              <input id="password" type="password" value={form.smtp_password} onChange={e => setForm({ ...form, smtp_password: e.target.value })} className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
            <div>
              <label htmlFor="from-address" className="block text-xs font-medium text-muted-foreground mb-1">From Address</label>
              <input id="from-address" value={form.smtp_from_address} onChange={e => setForm({ ...form, smtp_from_address: e.target.value })} placeholder="drones@agency.gov" className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
            <div>
              <label htmlFor="from-name" className="block text-xs font-medium text-muted-foreground mb-1">From Name</label>
              <input id="from-name" value={form.smtp_from_name} onChange={e => setForm({ ...form, smtp_from_name: e.target.value })} className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <input type="checkbox" checked={form.smtp_tls === 'true'} onChange={e => setForm({ ...form, smtp_tls: e.target.checked ? 'true' : 'false' })} id="smtp_tls" className="rounded" />
            <label htmlFor="smtp_tls" className="text-sm text-foreground">Use TLS (recommended)</label>
          </div>
          <div className="flex gap-2">
            <button onClick={handleSave} className="px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90">Save</button>
            <button onClick={handleTest} disabled={testing} className="px-3 py-1.5 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90 flex items-center gap-1.5 disabled:opacity-50">
              {testing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Mail className="w-3.5 h-3.5" />} Send Test Email
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function FlightLogImport() {
  const [files, setFiles] = useState([])
  const [format, setFormat] = useState('auto')
  const [importing, setImporting] = useState(false)
  const [result, setResult] = useState(null)
  const [progress, setProgress] = useState(null)
  const toast = useToast()

  const importSingleFile = async (file) => {
    const formData = new FormData()
    formData.append('file', file)

    if (format === 'skydio_csv') {
      const res = await api.upload('/export/flights/import', formData)
      return { ...res, flight_id: null, points_imported: res.imported || 0, format_detected: 'skydio_csv', error: res.errors?.length ? res.errors.join(', ') : null }
    } else if (format === 'excel') {
      const res = await api.upload('/export/excel/import', formData)
      return { ...res, flight_id: null, points_imported: res.flights_imported || 0, format_detected: 'excel', error: res.errors?.length ? res.errors.join(', ') : null }
    } else if (format === 'airdata_zip') {
      return await api.upload('/export/flights/import/log', formData)
    } else {
      formData.append('format', format)
      return await api.upload('/export/flights/import/log', formData)
    }
  }

  const handleImport = async () => {
    if (files.length === 0) return
    setImporting(true)
    setResult(null)
    setProgress(null)

    try {
      if (files.length === 1) {
        // Single file import
        const res = await importSingleFile(files[0])
        setResult(res)
        if (res.error) {
          toast.error(res.error)
        } else if (res.total !== undefined) {
          toast.success(`Bulk import: ${res.imported} imported, ${res.skipped} skipped out of ${res.total} files`)
        } else if (res.skipped) {
          toast.info(`Flight already exists (skipped)`)
        } else if (res.flight_id) {
          toast.success(`Imported flight #${res.flight_id} with ${res.points_imported} telemetry points`)
        } else {
          toast.success(`Imported ${res.points_imported || res.imported || 0} flights successfully`)
        }
      } else {
        // Multi-file batch import (process sequentially)
        const batch = { total: files.length, imported: 0, skipped: 0, errors: [] }
        for (let i = 0; i < files.length; i++) {
          setProgress(`Processing ${i + 1} of ${files.length}: ${files[i].name}`)
          try {
            const res = await importSingleFile(files[i])
            if (res.total !== undefined) {
              // ZIP result (nested batch)
              batch.imported += res.imported || 0
              batch.skipped += res.skipped || 0
              if (res.errors?.length) batch.errors.push(...res.errors)
            } else if (res.skipped) {
              batch.skipped++
            } else if (res.error) {
              batch.errors.push(`${files[i].name}: ${res.error}`)
            } else {
              batch.imported++
            }
          } catch (err) {
            batch.errors.push(`${files[i].name}: ${err.message}`)
          }
        }
        setResult(batch)
        setProgress(null)
        toast.success(`Batch import: ${batch.imported} imported, ${batch.skipped} skipped out of ${batch.total}`)
        if (batch.errors.length) toast.warning(`${batch.errors.length} error(s) during import`)
      }
    } catch (err) {
      toast.error(err.message)
    } finally {
      setImporting(false)
      setProgress(null)
    }
  }

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-3">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-amber-500/15 flex items-center justify-center text-amber-400 shrink-0">
          <Upload className="w-5 h-5" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-foreground">Flight Log Import</h3>
          <p className="text-xs text-muted-foreground">Import flight logs from Skydio CSV, DJI .txt, Litchi CSV, Airdata CSV/JSON/ZIP, or Excel files.</p>
        </div>
      </div>

      <div className="flex gap-3 items-end flex-wrap">
        <div className="flex-1 min-w-[200px]">
          <label htmlFor="flight-log-files-select-multiple-with-ctrl-shift-click" className="block text-xs font-medium text-muted-foreground mb-1">Flight Log File(s) — select multiple with Ctrl/Shift+click</label>
          <input id="flight-log-files-select-multiple-with-ctrl-shift-click"
            type="file"
            multiple
            accept=".txt,.csv,.xlsx,.xls,.json,.zip"
            onChange={e => { setFiles(Array.from(e.target.files)); setResult(null) }}
            className="w-full px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm file:mr-3 file:bg-primary file:text-primary-foreground file:border-0 file:rounded file:px-2 file:py-1 file:text-xs file:font-medium"
          />
        </div>
        <div>
          <label htmlFor="format" className="block text-xs font-medium text-muted-foreground mb-1">Format</label>
          <select id="format"
            value={format}
            onChange={e => setFormat(e.target.value)}
            className="px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm"
          >
            <option value="auto">Auto-detect</option>
            <option value="skydio_csv">Skydio CSV</option>
            <option value="excel">Excel (Skydio)</option>
            <option value="dji">DJI .txt</option>
            <option value="litchi">Litchi CSV</option>
            <option value="airdata">Airdata CSV</option>
            <option value="airdata_json">Airdata JSON</option>
            <option value="airdata_zip">Airdata ZIP (bulk)</option>
          </select>
        </div>
        <button
          onClick={handleImport}
          disabled={files.length === 0 || importing}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center gap-1.5"
        >
          {importing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
          {files.length > 1 ? `Import ${files.length} files` : 'Import'}
        </button>
      </div>

      {progress && (
        <div className="bg-blue-500/10 border border-blue-500/30 text-blue-400 rounded-lg p-3 text-sm flex items-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin shrink-0" />
          {progress}
        </div>
      )}

      <p className="text-xs text-amber-400/80">After importing, add email addresses to pilot profiles for API sync matching.</p>

      {result && !result.error && result.total !== undefined && (
        <div className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 rounded-lg p-3 text-sm space-y-1">
          <div>Bulk import complete: {result.imported} imported, {result.skipped} skipped, {result.total} total files</div>
          {result.errors?.length > 0 && (
            <div className="text-amber-400 text-xs mt-1">
              {result.errors.map((e) => <div key={e}>{e}</div>)}
            </div>
          )}
        </div>
      )}
      {result && !result.error && result.total === undefined && (
        <div className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 rounded-lg p-3 text-sm">
          {result.skipped
            ? `Flight #${result.flight_id} already exists (skipped)`
            : <>Flight #{result.flight_id} imported successfully — {result.points_imported} telemetry points, format: {result.format_detected}
              {result.date && ` — ${result.date}`}</>
          }
        </div>
      )}
      {result?.error && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg p-3 text-sm">
          {result.error}
        </div>
      )}
    </div>
  )
}

export default function IntegrationsPage() {
  const [settings, setSettings] = useState([])
  const [loading, setLoading] = useState(true)
  const { isAdmin } = useAuth()

  useEffect(() => {
    api.get('/settings')
      .then(setSettings)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
  }

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-primary/15 flex items-center justify-center text-primary">
          <Plug className="w-5 h-5" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-foreground">Integrations</h1>
          <p className="text-sm text-muted-foreground">Connect drone APIs, email, and import flight data.</p>
        </div>
      </div>

      {/* Drone Provider APIs */}
      <div>
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">Drone Providers</h2>
        <div className="space-y-2">
          {PROVIDERS.map(provider => (
            <ProviderCard key={provider.id} provider={provider} settings={settings} />
          ))}
        </div>
      </div>

      {/* Service Integrations */}
      {isAdmin && (
        <div>
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">Services</h2>
          <div className="space-y-2">
            <SmtpCard settings={settings} />
          </div>
        </div>
      )}

      {/* Flight Log Import */}
      <div>
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">Import</h2>
        <FlightLogImport />
      </div>
    </div>
  )
}
