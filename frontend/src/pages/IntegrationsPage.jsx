/**
 * Integrations page for managing drone provider APIs, SMTP email,
 * ADS-B settings, and flight log imports.
 */
import { useState, useEffect } from 'react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { useConfirm } from '@/hooks/useConfirm'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import {
  Plug, RefreshCw, CheckCircle, XCircle, Upload, Loader2,
  Mail, ChevronDown, ChevronRight,
} from 'lucide-react'
import { QuadcopterIcon } from '@/components/icons/QuadcopterIcon'

/** Format an ISO timestamp as a short relative string ("6 min ago", "2 hr ago"). */
function relativeTime(iso) {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return null
  const diffMin = Math.round((Date.now() - then) / 60000)
  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${diffMin} min ago`
  const diffHr = Math.round(diffMin / 60)
  if (diffHr < 24) return `${diffHr} hr ago`
  const diffDay = Math.round(diffHr / 24)
  return `${diffDay} day${diffDay === 1 ? '' : 's'} ago`
}

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
  const [tokenConfigured, setTokenConfigured] = useState(false)
  const [tokenIdConfigured, setTokenIdConfigured] = useState(false)
  const [testing, setTesting] = useState(false)
  const [syncType, setSyncType] = useState(null) // null | 'sync' | 'full'
  const [syncingTelemetry, setSyncingTelemetry] = useState(false)
  const [syncInterval, setSyncInterval] = useState('')
  const [telemetrySyncInterval, setTelemetrySyncInterval] = useState('')
  const [syncStatus, setSyncStatus] = useState(null)
  const [lastResult, setLastResult] = useState(null)
  const [confirmProps, requestConfirm] = useConfirm()
  const toast = useToast()

  useEffect(() => {
    if (provider.tokenKey && settings) {
      const t = settings.find(s => s.key === provider.tokenKey)
      const tid = settings.find(s => s.key === provider.tokenIdKey)
      const interval = settings.find(s => s.key === 'sync_interval')
      setTokenConfigured(!!(t && t.value))      // never seed the secret into the input
      setTokenIdConfigured(!!(tid && tid.value))
      if (interval) setSyncInterval(interval.value || '')
      const tInterval = settings.find(s => s.key === 'telemetry_sync_interval')
      if (tInterval) setTelemetrySyncInterval(tInterval.value || '')
    }
    // Fetch sync status
    api.get('/sync/status').then(s => setSyncStatus(s)).catch(() => {})
  }, [settings, provider])

  // A stored token means it IS configured (we never seed the secret into the input)
  const isConnected = tokenConfigured || (token && token.length > 0)
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
    setSyncType(full ? 'full' : 'sync')
    try {
      const res = await api.post(`/sync/now?full=${full}`, undefined, { timeout: 0 })
      setLastResult(res)
      const parts = [`${res.flights_new} new flights`]
      if (res.flights_skipped) parts.push(`${res.flights_skipped} existing`)
      if (res.vehicles_synced) parts.push(`${res.vehicles_synced} vehicles`)
      if (res.batteries_synced) parts.push(`${res.batteries_synced} batteries`)
      if (res.controllers_synced) parts.push(`${res.controllers_synced} controllers`)
      if (res.errors?.length) parts.push(`${res.errors.length} warnings`)
      toast.success(`Synced: ${parts.join(', ')}`)
    } catch (err) {
      toast.error(err.message)
    } finally {
      setSyncType(null)
      // Refresh sync status so the status block updates without a reload
      api.get('/sync/status').then(s => setSyncStatus(s)).catch(() => {})
    }
  }

  const handleSyncTelemetry = async () => {
    setSyncingTelemetry(true)
    try {
      const res = await api.post('/sync/telemetry', undefined, { timeout: 0 })
      toast.success(`Telemetry synced for ${res.synced} flights (${res.remaining} remaining)`)
    } catch (err) {
      toast.error(err.message)
    } finally {
      setSyncingTelemetry(false)
      // Refresh sync status so the status block updates without a reload
      api.get('/sync/status').then(s => setSyncStatus(s)).catch(() => {})
    }
  }

  const handleSave = async () => {
    try {
      const items = []
      if (token) items.push({ key: provider.tokenKey, value: token })
      if (tokenId) items.push({ key: provider.tokenIdKey, value: tokenId })
      if (items.length === 0) { toast.info('No changes to save'); return }
      await api.put('/settings/bulk', items)
      setTokenConfigured(p => p || !!token)
      setTokenIdConfigured(p => p || !!tokenId)
      setToken('')
      setTokenId('')
      toast.success('Credentials saved')
    } catch (err) {
      toast.error(err.message)
    }
  }

  const handleDisconnect = () => {
    requestConfirm({
      title: `Disconnect ${provider.name}`,
      message: `Disconnect ${provider.name}? You'll need to re-enter the token to reconnect.`,
      confirmLabel: 'Disconnect',
      confirmVariant: 'danger',
      onConfirm: async () => {
        try {
          await api.post('/sync/disconnect')
          setTokenConfigured(false)
          setTokenIdConfigured(false)
          setToken('')
          setTokenId('')
          toast.success(`${provider.name} disconnected`)
          api.get('/sync/status').then(s => setSyncStatus(s)).catch(() => {})
        } catch (err) {
          toast.error(err.message)
        }
      },
    })
  }

  const metaRun = summarizeMetaRun(lastResult || syncStatus?.last_sync_result)

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
              placeholder={tokenConfigured ? 'Token saved (enter new to replace)' : 'Enter API token'}
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
                placeholder={tokenIdConfigured ? 'Token ID saved (enter new to replace)' : 'Enter Token ID'}
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
            {tokenConfigured && (
              <button onClick={handleDisconnect} className="px-3 py-1.5 bg-red-500/15 text-red-400 rounded-lg text-sm hover:bg-red-500/25 flex items-center gap-1.5">
                <XCircle className="w-3.5 h-3.5" /> Disconnect
              </button>
            )}
            <div className="flex flex-wrap gap-2">
              <div className="flex flex-col items-start">
                <button onClick={() => handleSync(false)} disabled={!!syncType} className="px-3 py-1.5 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90 flex items-center gap-1.5 disabled:opacity-50">
                  {syncType === 'sync' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />} Sync Now
                </button>
                <span className="text-[10px] text-muted-foreground mt-0.5 px-1">New flights since last sync + telemetry</span>
              </div>
              <div className="flex flex-col items-start">
                <button onClick={() => handleSync(true)} disabled={!!syncType} className="px-3 py-1.5 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90 flex items-center gap-1.5 disabled:opacity-50">
                  {syncType === 'full' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />} Full Sync
                </button>
                <span className="text-[10px] text-muted-foreground mt-0.5 px-1">All flights + cleanup empties + telemetry</span>
              </div>
              <div className="flex flex-col items-start">
                <button onClick={handleSyncTelemetry} disabled={syncingTelemetry} className="px-3 py-1.5 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90 flex items-center gap-1.5 disabled:opacity-50">
                  {syncingTelemetry ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />} Sync Telemetry (10)
                </button>
                <span className="text-[10px] text-muted-foreground mt-0.5 px-1">Fetch GPS/altitude data for 10 flights</span>
              </div>
            </div>
          </div>

          {/* Auto-Sync Interval */}
          <div className="pt-2 border-t border-border">
            <div className="flex items-center gap-3">
              <label htmlFor="sync-interval" className="text-xs text-muted-foreground whitespace-nowrap">Auto-Sync Interval</label>
              <select
                id="sync-interval"
                value={syncInterval}
                onChange={async (e) => {
                  const val = e.target.value
                  setSyncInterval(val)
                  try {
                    await api.put('/settings/bulk', [{ key: 'sync_interval', value: val }])
                    toast.success(val ? `Auto-sync set to every ${val} minutes` : 'Auto-sync disabled')
                  } catch (err) { toast.error(err.message) }
                }}
                className="px-2 py-1 bg-secondary border border-border rounded-lg text-foreground text-xs focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="">Disabled</option>
                <option value="360">Every 6 hours</option>
                <option value="720">Every 12 hours</option>
                <option value="1440">Every 24 hours</option>
              </select>
              {syncStatus?.provider && (
                <span className="text-[10px] text-muted-foreground">{syncStatus.provider}</span>
              )}
            </div>
            <p className="text-[10px] text-muted-foreground mt-1">Automatically pulls new flights, vehicles, batteries, and equipment from Skydio on this schedule. Telemetry is handled separately by Telemetry Auto-Sync below.</p>
            <div className="mt-2">
              <SyncStatusBlock
                syncedLabel="Last synced"
                live={syncType === 'full' ? 'full' : syncType === 'sync' ? 'incremental' : null}
                lastTime={syncStatus?.last_sync}
                intervalMin={Number(syncStatus?.sync_interval) || 0}
                runSummary={metaRun.summary}
                runStatus={metaRun.status}
                firstError={metaRun.firstError}
                moreErrors={metaRun.moreErrors}
              />
            </div>
          </div>

          {/* Telemetry Auto-Sync Interval */}
          <div className="pt-2 border-t border-border">
            <div className="flex items-center gap-3">
              <label htmlFor="telemetry-sync-interval" className="text-xs text-muted-foreground whitespace-nowrap">Telemetry Auto-Sync</label>
              <select
                id="telemetry-sync-interval"
                value={telemetrySyncInterval}
                onChange={async (e) => {
                  const val = e.target.value
                  setTelemetrySyncInterval(val)
                  try {
                    await api.put('/settings/bulk', [{ key: 'telemetry_sync_interval', value: val }])
                    toast.success(val ? `Telemetry auto-sync set to every ${val} minutes` : 'Telemetry auto-sync disabled')
                  } catch (err) { toast.error(err.message) }
                }}
                className="px-2 py-1 bg-secondary border border-border rounded-lg text-foreground text-xs focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="">Disabled</option>
                <option value="30">Every 30 minutes</option>
                <option value="60">Every hour</option>
                <option value="120">Every 2 hours</option>
                <option value="360">Every 6 hours</option>
              </select>
            </div>
            <p className="text-[10px] text-muted-foreground mt-1">Fetches telemetry for up to 10 flights that are missing it each run, newest first. Only contacts Skydio when flights are actually missing telemetry, and stops once every flight has telemetry.</p>
            <div className="mt-2">
              <SyncStatusBlock
                syncedLabel="Last telemetry"
                live={syncingTelemetry ? 'telemetry' : null}
                lastTime={syncStatus?.last_telemetry_sync}
                intervalMin={Number(syncStatus?.telemetry_sync_interval) || 0}
                runSummary={syncStatus?.last_telemetry_sync_result ? `${syncStatus.last_telemetry_sync_result.synced ?? 0} flights fetched` : null}
                extra={syncStatus?.telemetry_remaining != null ? { label: 'Missing', value: `${syncStatus.telemetry_remaining} flights` } : null}
              />
            </div>
          </div>
        </div>
      )}
      <ConfirmDialog {...confirmProps} />
    </div>
  )
}

/** "in N min" until the next scheduled sync, or null if not schedulable. */
function nextSyncLabel(lastSync, intervalMin) {
  if (!(intervalMin > 0) || !lastSync) return null
  const next = new Date(lastSync).getTime() + intervalMin * 60000
  if (Number.isNaN(next)) return null
  const inMin = Math.round((next - Date.now()) / 60000)
  return inMin > 0 ? `in ${inMin} min` : 'due now'
}

/** Status colors for the last-run dot by SyncResult status. */
const STATUS_DOT = {
  success: 'bg-emerald-400',
  partial: 'bg-amber-400',
  failure: 'bg-red-400',
}

/** Presentational status block for one sync: state, last/next time, last-run, optional extra line. */
function SyncStatusBlock({ syncedLabel = 'Last synced', live = null, lastTime = null, intervalMin = 0, runSummary = null, runStatus = 'success', firstError = null, moreErrors = 0, extra = null }) {
  const nextSync = nextSyncLabel(lastTime, intervalMin)

  return (
    <div className="rounded-lg bg-secondary/40 border border-border p-3 space-y-1.5 text-xs">
      <div className="flex items-center gap-2">
        <span className="text-muted-foreground w-24 shrink-0">State</span>
        {live ? (
          <span className="flex items-center gap-1.5 text-foreground">
            <Loader2 className="w-3 h-3 animate-spin" /> Syncing… ({live})
          </span>
        ) : (
          <span className="text-muted-foreground">Idle</span>
        )}
      </div>

      <div className="flex items-center gap-2">
        <span className="text-muted-foreground w-24 shrink-0">{syncedLabel}</span>
        {lastTime ? (
          <span className="text-foreground">
            {relativeTime(lastTime)} <span className="text-muted-foreground">({new Date(lastTime).toLocaleString()})</span>
          </span>
        ) : (
          <span className="text-muted-foreground">Never</span>
        )}
      </div>

      {nextSync && (
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground w-24 shrink-0">Next sync</span>
          <span className="text-foreground">{nextSync}</span>
        </div>
      )}

      {runSummary && (
        <div className="flex items-start gap-2">
          <span className="text-muted-foreground w-24 shrink-0">Last run</span>
          <div className="space-y-0.5">
            <span className="flex items-center gap-1.5 text-foreground">
              <span className={`w-2 h-2 rounded-full shrink-0 ${STATUS_DOT[runStatus] || 'bg-muted'}`} />
              {runSummary}
            </span>
            {firstError && (
              <span className="block text-red-400">
                {firstError}{moreErrors > 0 ? ` (+${moreErrors} more)` : ''}
              </span>
            )}
          </div>
        </div>
      )}

      {extra && (
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground w-24 shrink-0">{extra.label}</span>
          <span className="text-foreground">{extra.value}</span>
        </div>
      )}
    </div>
  )
}

/** Summarize a metadata sync-run object into {summary, status, firstError, moreErrors}. */
function summarizeMetaRun(run) {
  if (!run) return { summary: null, status: 'success', firstError: null, moreErrors: 0 }
  const status = run.status || (run.errors?.length ? 'partial' : 'success')
  const summary = [
    run.flights_new != null ? `${run.flights_new} flights` : null,
    run.vehicles_synced ? `${run.vehicles_synced} vehicles` : null,
    run.batteries_synced ? `${run.batteries_synced} batteries` : null,
    run.controllers_synced ? `${run.controllers_synced} controllers` : null,
    `${run.errors?.length || 0} errors`,
  ].filter(Boolean).join(', ')
  return {
    summary,
    status,
    firstError: run.errors?.length ? run.errors[0] : null,
    moreErrors: run.errors?.length ? run.errors.length - 1 : 0,
  }
}

function SmtpCard({ settings }) {
  const [expanded, setExpanded] = useState(false)
  const [form, setForm] = useState({
    smtp_host: '', smtp_port: '587', smtp_username: '', smtp_password: '',
    smtp_from_address: '', smtp_from_name: 'Drone Unit Manager', smtp_tls: 'true', smtp_enabled: 'false',
  })
  const [testing, setTesting] = useState(false)
  const [passwordConfigured, setPasswordConfigured] = useState(false)
  const toast = useToast()

  useEffect(() => {
    if (settings) {
      const vals = {}
      for (const s of settings) {
        if (s.key === 'smtp_password') { setPasswordConfigured(!!s.value); continue }
        if (s.key.startsWith('smtp_')) vals[s.key] = s.value || ''
      }
      setForm(prev => ({ ...prev, ...vals }))
    }
  }, [settings])

  const handleSave = async () => {
    try {
      const items = Object.entries(form)
        .filter(([k, v]) => !(k === 'smtp_password' && v === ''))
        .map(([key, value]) => ({ key, value }))
      await api.put('/settings/bulk', items)
      if (form.smtp_password) setPasswordConfigured(true)
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
              <input id="password" type="password" value={form.smtp_password} onChange={e => setForm({ ...form, smtp_password: e.target.value })} placeholder={passwordConfigured ? 'Password saved (enter new to replace)' : ''} className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
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

const ERRORS_SHOWN = 5

/**
 * Everything an import decided not to do.
 *
 * "Imported 62 flights" on its own is a dangerous success message: a BRINC
 * export whose drone is not in the fleet skips every row belonging to it, and
 * without this the operator sees only the 62 that worked. Rendered for any
 * importer; every field it reads is optional.
 */
function ImportNotices({ result }) {
  const unmatched = Object.entries(result.unmatched_drones || {})
  const warnings = result.warnings || []
  const errors = result.errors || []
  const notes = []
  if (result.flights_skipped_zero_duration) {
    notes.push(`${result.flights_skipped_zero_duration} row(s) had no flight time and were skipped`)
  }
  if (result.pilots_created_names?.length) {
    notes.push(`Added to the roster, confirm these are unit pilots: ${result.pilots_created_names.join(', ')}`)
  }
  if (result.coordinates_backfilled) {
    notes.push(`${result.coordinates_backfilled} earlier flight(s) placed on the map`)
  }
  if (!unmatched.length && !warnings.length && !errors.length && !notes.length) return null

  return (
    <div className="text-xs mt-2 pt-2 border-t border-emerald-500/20 space-y-1 text-amber-400">
      {warnings.map(w => <div key={w}>{w}</div>)}
      {unmatched.length > 0 && (
        <div>
          Not in the fleet, so their flights were skipped:{' '}
          {unmatched.map(([name, n]) => `${name || 'unnamed'} (${n} flight${n === 1 ? '' : 's'})`).join(', ')}
        </div>
      )}
      {notes.map(n => <div key={n}>{n}</div>)}
      {errors.slice(0, ERRORS_SHOWN).map(e => <div key={e}>{e}</div>)}
      {errors.length > ERRORS_SHOWN && <div>and {errors.length - ERRORS_SHOWN} more</div>}
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

    if (format === 'skydio') {
      // Skydio export (CSV or Excel) -> full importer: fleet, pilots, accessories, flights
      const res = await api.upload('/export/excel/import', formData)
      return { ...res, flight_id: null, points_imported: res.flights_imported ?? res.imported ?? 0, format_detected: 'skydio', error: res.errors?.length ? res.errors.join(', ') : null }
    } else if (format === 'airdata_zip') {
      return await api.upload('/export/flights/import/log', formData)
    } else {
      formData.append('format', format)
      return await api.upload('/export/flights/import/log', formData)
    }
  }

  const toastImportResult = (res) => {
    if (res.error) {
      toast.error(res.error)
    } else if (res.total !== undefined) {
      toast.success(`Bulk import: ${res.imported} imported, ${res.skipped} skipped out of ${res.total} files`)
    } else if (res.skipped) {
      toast.info('Flight already exists (skipped)')
    } else if (res.flight_id) {
      toast.success(`Imported flight #${res.flight_id} with ${res.points_imported} telemetry points`)
    } else {
      const n = res.points_imported || res.imported || res.flights_imported || 0
      const extras = []
      if (res.pilots_created) extras.push(`${res.pilots_created} pilots`)
      if (res.vehicles_created) extras.push(`${res.vehicles_created} vehicles`)
      if (res.flights_skipped) extras.push(`${res.flights_skipped} duplicates skipped`)
      const suffix = extras.length ? ` (${extras.join(', ')})` : ''
      toast.success(`Imported ${n} flights successfully${suffix}`)
    }
  }

  const processBatchResult = (batch, res, fileName) => {
    if (res.total !== undefined) {
      batch.imported += res.imported || 0
      batch.skipped += res.skipped || 0
      if (res.errors?.length) batch.errors.push(...res.errors)
    } else if (res.skipped) {
      batch.skipped++
    } else if (res.error) {
      batch.errors.push(`${fileName}: ${res.error}`)
    } else {
      batch.imported++
    }
  }

  const handleImport = async () => {
    if (files.length === 0) return
    setImporting(true)
    setResult(null)
    setProgress(null)

    try {
      if (files.length === 1) {
        const res = await importSingleFile(files[0])
        setResult(res)
        toastImportResult(res)
      } else {
        const batch = { total: files.length, imported: 0, skipped: 0, errors: [] }
        for (let i = 0; i < files.length; i++) {
          setProgress(`Processing ${i + 1} of ${files.length}: ${files[i].name}`)
          try {
            const res = await importSingleFile(files[i])
            processBatchResult(batch, res, files[i].name)
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
          <p className="text-xs text-muted-foreground">A Skydio export (CSV or Excel) creates fleet, pilots, accessories, and flights. Also imports flight logs from DJI .txt, Litchi CSV, Airdata CSV/JSON/ZIP, or Parrot/ANAFI (GUTMA JSON). Manufacturer is auto-detected.</p>
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
            <option value="skydio">Skydio (CSV or Excel)</option>
            <option value="dji">DJI .txt</option>
            <option value="litchi">Litchi CSV</option>
            <option value="airdata">Airdata CSV</option>
            <option value="airdata_json">Airdata JSON</option>
            <option value="airdata_zip">Airdata ZIP (bulk)</option>
            <option value="parrot">Parrot / ANAFI (GUTMA JSON)</option>
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
            : result.flight_id
              ? <>Flight #{result.flight_id} imported successfully — {result.points_imported} telemetry points, format: {result.format_detected}
                {result.date && ` — ${result.date}`}</>
              : <>
                  Imported {result.points_imported || result.flights_imported || 0} flight{(result.points_imported || result.flights_imported || 0) === 1 ? '' : 's'} ({result.format_detected})
                  {(result.pilots_created || result.vehicles_created || result.flights_skipped) ? (
                    <div className="text-xs mt-1 text-emerald-400/80">
                      {result.pilots_created || 0} pilot(s) and {result.vehicles_created || 0} vehicle(s) created
                      {result.flights_skipped ? `, ${result.flights_skipped} duplicate(s) skipped` : ''}
                    </div>
                  ) : null}
                  <ImportNotices result={result} />
                </>
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
