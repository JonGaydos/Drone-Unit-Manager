import { useState, useRef } from 'react'
import { api } from '@/api/client'
import { Shield, ArrowRight, Upload, Loader2, Image as ImageIcon, Mail, Plug, FileUp, CheckCircle2 } from 'lucide-react'
import { QuadcopterIcon } from '@/components/icons/QuadcopterIcon'
import { TIMEZONES } from '@/lib/utils'

export default function SetupPage({ recovery = false }) {
  const [step, setStep] = useState(1)
  const [form, setForm] = useState({
    display_name: '',
    org_name: '',
    email: '',
    username: '',
    password: '',
    password_confirm: '',
    timezone: 'America/Chicago',
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showRestore, setShowRestore] = useState(false)
  const [restoring, setRestoring] = useState(false)
  const [restoreFile, setRestoreFile] = useState(null)
  const [restoreResult, setRestoreResult] = useState(null)
  const [installToken, setInstallToken] = useState('')
  const fileRef = useRef(null)

  // Step 3 (optional setup) state
  const [logoFile, setLogoFile] = useState(null)
  const [logoSaved, setLogoSaved] = useState(false)
  const [savingLogo, setSavingLogo] = useState(false)
  const logoFileRef = useRef(null)

  const [skydioForm, setSkydioForm] = useState({ skydio_api_token: '', skydio_token_id: '' })
  const [skydioSaved, setSkydioSaved] = useState(false)
  const [savingSkydio, setSavingSkydio] = useState(false)

  const [smtpForm, setSmtpForm] = useState({
    smtp_enabled: 'false', smtp_host: '', smtp_port: '587',
    smtp_username: '', smtp_password: '',
    smtp_from_address: '', smtp_from_name: '', smtp_tls: 'true',
  })
  const [smtpSaved, setSmtpSaved] = useState(false)
  const [savingSmtp, setSavingSmtp] = useState(false)

  const [importFiles, setImportFiles] = useState([])
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState(null)
  const importFileRef = useRef(null)

  const handleSubmit = async () => {
    setError('')
    if (form.password !== form.password_confirm) {
      setError('Passwords do not match')
      return
    }
    if (form.password.length < 12) {
      setError('Password must be at least 12 characters')
      return
    }
    if (!/[A-Z]/.test(form.password)) {
      setError('Password must contain at least one uppercase letter')
      return
    }
    if (!/\d/.test(form.password)) {
      setError('Password must contain at least one number')
      return
    }

    setLoading(true)
    try {
      const result = await api.post('/auth/setup', form)
      localStorage.setItem('token', result.token)
      // Move to optional setup (logo, Skydio, SMTP, initial import).
      setStep(3)
    } catch (err) {
      setError(err.message || 'Setup failed')
    } finally {
      setLoading(false)
    }
  }

  const handleSaveLogo = async () => {
    if (!logoFile) return
    setSavingLogo(true); setError('')
    try {
      const fd = new FormData()
      fd.append('file', logoFile)
      await api.upload('/settings/logo', fd)
      setLogoSaved(true)
    } catch (err) {
      setError(err.message || 'Logo upload failed')
    } finally { setSavingLogo(false) }
  }

  const handleSaveSkydio = async () => {
    if (!skydioForm.skydio_api_token && !skydioForm.skydio_token_id) {
      setError('Enter API token and token ID')
      return
    }
    setSavingSkydio(true); setError('')
    try {
      const payload = [
        { key: 'skydio_api_token', value: skydioForm.skydio_api_token },
        { key: 'skydio_token_id', value: skydioForm.skydio_token_id },
      ]
      await api.put('/settings/bulk', payload)
      setSkydioSaved(true)
    } catch (err) {
      setError(err.message || 'Skydio save failed')
    } finally { setSavingSkydio(false) }
  }

  const handleSaveSmtp = async () => {
    if (smtpForm.smtp_enabled === 'true' && (!smtpForm.smtp_host || !smtpForm.smtp_from_address)) {
      setError('SMTP host and From address are required when enabling email')
      return
    }
    setSavingSmtp(true); setError('')
    try {
      const payload = Object.entries(smtpForm).map(([key, value]) => ({ key, value: String(value) }))
      await api.put('/settings/bulk', payload)
      setSmtpSaved(true)
    } catch (err) {
      setError(err.message || 'SMTP save failed')
    } finally { setSavingSmtp(false) }
  }

  const handleImportLogs = async () => {
    if (importFiles.length === 0) return
    setImporting(true); setError('')
    const results = []
    try {
      for (const f of importFiles) {
        const fd = new FormData()
        fd.append('file', f)
        try {
          const res = await api.upload('/export/flights/import/log', fd)
          results.push({ filename: f.name, ok: true, ...res })
        } catch (err) {
          results.push({ filename: f.name, ok: false, error: err.message })
        }
      }
      setImportResult(results)
    } finally { setImporting(false) }
  }

  return (
    <div className="min-h-screen bg-bg flex items-center justify-center p-4">
      <div className="w-full max-w-lg">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="w-16 h-16 bg-primary/15 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <QuadcopterIcon className="w-8 h-8 text-primary" />
          </div>
          <h1 className="text-3xl font-bold text-foreground">Drone Unit Manager</h1>
          <p className="text-muted-foreground mt-2">
            {recovery ? 'Backup restored. Reactivate an administrator to sign in.' : "Welcome! Let's set up your account."}
          </p>
        </div>

        {recovery && (
          <div className="bg-amber-500/10 border border-amber-500/30 text-amber-300 rounded-xl p-4 mb-4 text-sm">
            <p className="font-medium text-amber-200">Restored backup detected</p>
            <p className="mt-1">
              Your data is back, but passwords are never included in a backup. Enter the
              <span className="font-medium"> username of an administrator from the restored data</span> and
              a new password to regain access. Organization and name fields are ignored in this step.
            </p>
          </div>
        )}

        <div className="bg-card border border-border rounded-xl p-6 space-y-4">
          {step === 1 && (
            <>
              <h2 className="text-lg font-semibold flex items-center gap-2">
                <Shield className="w-5 h-5 text-primary" /> Organization
              </h2>
              <div>
                <label htmlFor="organization-name" className="block text-sm font-medium mb-1">Organization Name</label>
                <input id="organization-name"
                  type="text"
                  value={form.org_name}
                  onChange={e => setForm({...form, org_name: e.target.value})}
                  placeholder="e.g., Sheriff's Office"
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground"
                />
              </div>
              <div>
                <label htmlFor="timezone" className="block text-sm font-medium mb-1">Time Zone</label>
                <select id="timezone"
                  value={form.timezone}
                  onChange={e => setForm({...form, timezone: e.target.value})}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground"
                >
                  {TIMEZONES.map(tz => <option key={tz} value={tz}>{tz}</option>)}
                </select>
                <p className="text-xs text-muted-foreground mt-1">All flight times display in this zone. Stored data stays in UTC.</p>
              </div>
              <div>
                <label htmlFor="your-name" className="block text-sm font-medium mb-1">Your Name</label>
                <input id="your-name"
                  type="text"
                  value={form.display_name}
                  onChange={e => setForm({...form, display_name: e.target.value})}
                  placeholder="e.g., John Doe"
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground"
                />
              </div>
              <div>
                <label htmlFor="email" className="block text-sm font-medium mb-1">Email Address</label>
                <input id="email"
                  type="email"
                  value={form.email}
                  onChange={e => setForm({...form, email: e.target.value})}
                  placeholder="e.g., jdoe@agency.gov"
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground"
                />
                <p className="text-xs text-muted-foreground mt-1">Used for email digests and pilot profile matching</p>
              </div>
              <button
                onClick={() => setStep(2)}
                disabled={!form.display_name}
                className="w-full py-2.5 bg-primary text-primary-foreground rounded-lg font-medium disabled:opacity-50 flex items-center justify-center gap-2"
              >
                Continue <ArrowRight className="w-4 h-4" />
              </button>
            </>
          )}

          {step === 3 && (
            <>
              <div>
                <h2 className="text-lg font-semibold flex items-center gap-2">
                  <CheckCircle2 className="w-5 h-5 text-emerald-400" /> Account created
                </h2>
                <p className="text-sm text-muted-foreground mt-1">
                  Optional setup below — each section is independent. Skip whatever you'll configure later. Everything here can also be changed in Settings after you start using the app.
                </p>
              </div>

              {/* Organization logo */}
              <div className="border-t border-border pt-3">
                <h3 className="text-sm font-semibold text-foreground flex items-center gap-2 mb-2">
                  <ImageIcon className="w-4 h-4 text-primary" /> Organization Logo
                  {logoSaved && <span className="text-xs text-emerald-400 ml-1">saved</span>}
                </h3>
                <p className="text-xs text-muted-foreground mb-2">Appears on PDF report headers and on the login screen. PNG, JPG, or SVG.</p>
                <input ref={logoFileRef} type="file" accept="image/*" className="hidden" onChange={e => { setLogoFile(e.target.files[0] || null); setLogoSaved(false) }} />
                <div className="flex gap-2">
                  <button type="button" onClick={() => logoFileRef.current?.click()} className="flex-1 px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm hover:bg-accent text-left truncate">
                    {logoFile ? logoFile.name : 'Choose file...'}
                  </button>
                  <button type="button" onClick={handleSaveLogo} disabled={!logoFile || savingLogo || logoSaved}
                    className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium disabled:opacity-50">
                    {savingLogo ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Upload'}
                  </button>
                </div>
              </div>

              {/* Skydio integration */}
              <div className="border-t border-border pt-3">
                <h3 className="text-sm font-semibold text-foreground flex items-center gap-2 mb-2">
                  <Plug className="w-4 h-4 text-primary" /> Skydio Integration
                  {skydioSaved && <span className="text-xs text-emerald-400 ml-1">saved</span>}
                </h3>
                <p className="text-xs text-muted-foreground mb-2">Auto-sync flights, fleet, and accessories from Skydio Cloud. Generate a token at <span className="font-mono text-foreground">skydio.com → Account → API Tokens</span>.</p>
                <input type="text" value={skydioForm.skydio_token_id}
                  onChange={e => { setSkydioForm({ ...skydioForm, skydio_token_id: e.target.value }); setSkydioSaved(false) }}
                  placeholder="Token ID"
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm mb-2" />
                <input type="password" value={skydioForm.skydio_api_token}
                  onChange={e => { setSkydioForm({ ...skydioForm, skydio_api_token: e.target.value }); setSkydioSaved(false) }}
                  placeholder="API Token (kept private)"
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm mb-2 font-mono text-xs" />
                <button type="button" onClick={handleSaveSkydio} disabled={savingSkydio || skydioSaved}
                  className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium disabled:opacity-50">
                  {savingSkydio ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Save Skydio'}
                </button>
              </div>

              {/* SMTP / email */}
              <div className="border-t border-border pt-3">
                <h3 className="text-sm font-semibold text-foreground flex items-center gap-2 mb-2">
                  <Mail className="w-4 h-4 text-primary" /> Email (SMTP)
                  {smtpSaved && <span className="text-xs text-emerald-400 ml-1">saved</span>}
                </h3>
                <p className="text-xs text-muted-foreground mb-2">Enable to send daily digests and notifications. Works with Gmail, Microsoft 365, or any SMTP relay.</p>
                <label className="flex items-center gap-2 mb-2 cursor-pointer">
                  <input type="checkbox" checked={smtpForm.smtp_enabled === 'true'}
                    onChange={() => { setSmtpForm({ ...smtpForm, smtp_enabled: smtpForm.smtp_enabled === 'true' ? 'false' : 'true' }); setSmtpSaved(false) }}
                    className="w-4 h-4" />
                  <span className="text-sm text-foreground">Enable email sending</span>
                </label>
                {smtpForm.smtp_enabled === 'true' && (
                  <div className="space-y-2">
                    <div className="grid grid-cols-3 gap-2">
                      <input type="text" placeholder="Host (smtp.gmail.com)" value={smtpForm.smtp_host}
                        onChange={e => { setSmtpForm({ ...smtpForm, smtp_host: e.target.value }); setSmtpSaved(false) }}
                        className="col-span-2 px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
                      <input type="number" placeholder="Port" value={smtpForm.smtp_port}
                        onChange={e => { setSmtpForm({ ...smtpForm, smtp_port: e.target.value }); setSmtpSaved(false) }}
                        className="px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
                    </div>
                    <input type="text" placeholder="Username" value={smtpForm.smtp_username}
                      onChange={e => { setSmtpForm({ ...smtpForm, smtp_username: e.target.value }); setSmtpSaved(false) }}
                      className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
                    <input type="password" placeholder="Password / App Password" value={smtpForm.smtp_password}
                      onChange={e => { setSmtpForm({ ...smtpForm, smtp_password: e.target.value }); setSmtpSaved(false) }}
                      className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
                    <input type="text" placeholder="From address (alerts@agency.gov)" value={smtpForm.smtp_from_address}
                      onChange={e => { setSmtpForm({ ...smtpForm, smtp_from_address: e.target.value }); setSmtpSaved(false) }}
                      className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
                    <input type="text" placeholder="From name (DUM Notifications)" value={smtpForm.smtp_from_name}
                      onChange={e => { setSmtpForm({ ...smtpForm, smtp_from_name: e.target.value }); setSmtpSaved(false) }}
                      className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm" />
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input type="checkbox" checked={smtpForm.smtp_tls === 'true'}
                        onChange={() => { setSmtpForm({ ...smtpForm, smtp_tls: smtpForm.smtp_tls === 'true' ? 'false' : 'true' }); setSmtpSaved(false) }}
                        className="w-4 h-4" />
                      <span className="text-sm text-foreground">Use TLS / STARTTLS</span>
                    </label>
                  </div>
                )}
                <button type="button" onClick={handleSaveSmtp} disabled={savingSmtp || smtpSaved}
                  className="mt-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium disabled:opacity-50">
                  {savingSmtp ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Save Email Settings'}
                </button>
              </div>

              {/* Initial flight log import */}
              <div className="border-t border-border pt-3">
                <h3 className="text-sm font-semibold text-foreground flex items-center gap-2 mb-2">
                  <FileUp className="w-4 h-4 text-primary" /> Initial Flight Log Import
                </h3>
                <p className="text-xs text-muted-foreground mb-2">Upload existing logs (DJI .txt, Litchi CSV, Airdata CSV/JSON/ZIP, Parrot GUTMA JSON, Skydio CSV/XLSX). Format is auto-detected. You can also do this later from Settings → Integrations.</p>
                <input ref={importFileRef} type="file" multiple className="hidden"
                  onChange={e => { setImportFiles(Array.from(e.target.files || [])); setImportResult(null) }} />
                <div className="flex gap-2">
                  <button type="button" onClick={() => importFileRef.current?.click()}
                    className="flex-1 px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm hover:bg-accent text-left truncate">
                    {importFiles.length > 0 ? `${importFiles.length} file(s) selected` : 'Choose files...'}
                  </button>
                  <button type="button" onClick={handleImportLogs} disabled={importFiles.length === 0 || importing}
                    className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium disabled:opacity-50">
                    {importing ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Import'}
                  </button>
                </div>
                {importResult && (
                  <div className="mt-2 text-xs space-y-0.5">
                    {importResult.map((r, idx) => (
                      <p key={`${idx}-${r.filename}`} className={r.ok ? 'text-emerald-400' : 'text-red-400'}>
                        {r.ok ? '✓' : '✗'} {r.filename}{r.ok && r.points_imported ? ` — ${r.points_imported} points` : ''}{r.error ? ` — ${r.error}` : ''}
                      </p>
                    ))}
                  </div>
                )}
              </div>

              {error && (
                <div className="bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg p-3 text-sm">{error}</div>
              )}

              <button
                onClick={() => { globalThis.location.href = '/' }}
                className="w-full py-2.5 bg-primary text-primary-foreground rounded-lg font-medium flex items-center justify-center gap-2"
              >
                Go to Dashboard <ArrowRight className="w-4 h-4" />
              </button>
            </>
          )}

          {step === 2 && (
            <>
              <h2 className="text-lg font-semibold flex items-center gap-2">
                <Shield className="w-5 h-5 text-primary" /> Create Admin Account
              </h2>
              <div>
                <label htmlFor="username" className="block text-sm font-medium mb-1">Username</label>
                <input id="username"
                  type="text"
                  value={form.username}
                  onChange={e => setForm({...form, username: e.target.value})}
                  placeholder="Choose a username"
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground"
                />
              </div>
              <div>
                <label htmlFor="password" className="block text-sm font-medium mb-1">Password</label>
                <input id="password"
                  type="password"
                  value={form.password}
                  onChange={e => setForm({...form, password: e.target.value})}
                  placeholder="Min 12 chars, 1 uppercase, 1 number"
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground"
                />
              </div>
              <div>
                <label htmlFor="confirm-password" className="block text-sm font-medium mb-1">Confirm Password</label>
                <input id="confirm-password"
                  type="password"
                  value={form.password_confirm}
                  onChange={e => setForm({...form, password_confirm: e.target.value})}
                  placeholder="Confirm your password"
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground"
                />
              </div>
              {error && (
                <div className="bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg p-3 text-sm">{error}</div>
              )}
              <div className="flex gap-2">
                <button onClick={() => setStep(1)} className="px-4 py-2.5 bg-secondary text-foreground rounded-lg">Back</button>
                <button
                  onClick={handleSubmit}
                  disabled={loading || !form.username || !form.password}
                  className="flex-1 py-2.5 bg-primary text-primary-foreground rounded-lg font-medium disabled:opacity-50"
                >
                  {loading ? 'Creating...' : 'Create Account & Start'}
                </button>
              </div>
            </>
          )}
        </div>

        {/* Restore from Backup */}
        <div className="mt-4">
          <button
            onClick={() => setShowRestore(!showRestore)}
            className="w-full text-center text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            {showRestore ? 'Hide restore option' : 'Restore from a backup instead?'}
          </button>
          {showRestore && (
            <div className="bg-card border border-border rounded-xl p-6 mt-3 space-y-4">
              <h3 className="text-base font-semibold text-foreground">Restore from Backup</h3>
              <p className="text-sm text-muted-foreground">
                Upload a backup ZIP file exported from another Drone Unit Manager instance. This will restore all data, settings, and uploaded files.
              </p>
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                className="w-full border-2 border-dashed border-border rounded-xl p-6 text-center cursor-pointer hover:border-primary/50 transition-colors bg-transparent"
              >
                <Upload className="w-8 h-8 mx-auto text-muted-foreground/50 mb-2" />
                <p className="text-sm text-muted-foreground">
                  {restoreFile ? restoreFile.name : 'Click to select backup ZIP file'}
                </p>
              </button>
              <input ref={fileRef} type="file" accept=".zip" className="hidden" onChange={e => setRestoreFile(e.target.files[0])} />
              {restoreFile && !restoreResult && (
                <>
                  <div>
                    <label htmlFor="install-token" className="block text-sm font-medium mb-1">Install Token</label>
                    <input
                      id="install-token"
                      type="text"
                      autoComplete="off"
                      spellCheck="false"
                      value={installToken}
                      onChange={e => setInstallToken(e.target.value.trim())}
                      placeholder="64-character token from container logs"
                      className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-xs font-mono focus:outline-none focus:ring-2 focus:ring-ring"
                    />
                    <p className="text-xs text-muted-foreground mt-1">
                      Required for fresh-install backup restore. Either run <code className="text-foreground">docker logs &lt;container&gt;</code> and look for "install token", or read <code className="text-foreground">install_token.txt</code> from the container's data directory.
                    </p>
                  </div>
                  <button
                    onClick={async () => {
                      if (!installToken) {
                        setError('Install token is required. Check the container logs.')
                        return
                      }
                      setRestoring(true)
                      setError('')
                      try {
                        const fd = new FormData()
                        fd.append('file', restoreFile)
                        const result = await api.upload('/backup/import', fd, { 'X-Install-Token': installToken }, { timeout: 0 })
                        setRestoreResult(result)
                        setTimeout(() => { globalThis.location.href = '/login' }, 3000)
                      } catch (err) {
                        setError(err.message || 'Restore failed')
                      } finally {
                        setRestoring(false)
                      }
                    }}
                    disabled={restoring || !installToken}
                    className="w-full py-2.5 bg-emerald-600 text-white rounded-lg font-medium disabled:opacity-50 flex items-center justify-center gap-2"
                  >
                    {restoring ? <><Loader2 className="w-4 h-4 animate-spin" /> Restoring...</> : 'Restore Backup'}
                  </button>
                </>
              )}
              {restoreResult && (
                <div className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 rounded-lg p-4 text-sm space-y-1">
                  <p className="font-medium">Restore complete!</p>
                  <p>Restored {restoreResult.rows_imported} rows across {restoreResult.tables_imported} tables.</p>
                  {restoreResult.files_restored > 0 && <p>{restoreResult.files_restored} files restored.</p>}
                  {restoreResult.telemetry_imported && <p>Telemetry data restored.</p>}
                  <p className="text-emerald-300 mt-2">Redirecting to login...</p>
                </div>
              )}
              {error && !restoreResult && (
                <div className="bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg p-3 text-sm">{error}</div>
              )}
            </div>
          )}
        </div>

        <p className="text-center text-xs text-muted-foreground mt-4">
          This account will have full administrator access.
        </p>
      </div>
    </div>
  )
}
