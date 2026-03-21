import { useState, useEffect } from 'react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { Save, TestTube, Loader2, Upload, FileSpreadsheet, RefreshCw } from 'lucide-react'

export default function SettingsPage() {
  const [settings, setSettings] = useState({})
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [importResult, setImportResult] = useState(null)
  const [importing, setImporting] = useState(false)
  const { isAdmin } = useAuth()

  useEffect(() => {
    api.get('/settings').then(data => {
      const map = {}
      data.forEach(s => { map[s.key] = s.value })
      setSettings(map)
    }).catch(console.error)
  }, [])

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
    </div>
  )
}
