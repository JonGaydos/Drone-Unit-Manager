import { useState, useRef } from 'react'
import { api } from '@/api/client'
import { Shield, ArrowRight, Upload, Loader2 } from 'lucide-react'
import { QuadcopterIcon } from '@/components/icons/QuadcopterIcon'

export default function SetupPage() {
  const [step, setStep] = useState(1)
  const [form, setForm] = useState({
    display_name: '',
    org_name: '',
    email: '',
    username: '',
    password: '',
    password_confirm: '',
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showRestore, setShowRestore] = useState(false)
  const [restoring, setRestoring] = useState(false)
  const [restoreFile, setRestoreFile] = useState(null)
  const [restoreResult, setRestoreResult] = useState(null)
  const fileRef = useRef(null)

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
    if (!/[0-9]/.test(form.password)) {
      setError('Password must contain at least one number')
      return
    }

    setLoading(true)
    try {
      const result = await api.post('/auth/setup', form)
      localStorage.setItem('token', result.token)
      globalThis.location.href = '/'
    } catch (err) {
      setError(err.message || 'Setup failed')
    } finally {
      setLoading(false)
    }
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
          <p className="text-muted-foreground mt-2">Welcome! Let's set up your account.</p>
        </div>

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
              <div
                className="border-2 border-dashed border-border rounded-xl p-6 text-center cursor-pointer hover:border-primary/50 transition-colors"
                onClick={() => fileRef.current?.click()}
              >
                <Upload className="w-8 h-8 mx-auto text-muted-foreground/50 mb-2" />
                <p className="text-sm text-muted-foreground">
                  {restoreFile ? restoreFile.name : 'Click to select backup ZIP file'}
                </p>
                <input ref={fileRef} type="file" accept=".zip" className="hidden" onChange={e => setRestoreFile(e.target.files[0])} />
              </div>
              {restoreFile && !restoreResult && (
                <button
                  onClick={async () => {
                    setRestoring(true)
                    setError('')
                    try {
                      const fd = new FormData()
                      fd.append('file', restoreFile)
                      const result = await api.upload('/backup/import', fd)
                      setRestoreResult(result)
                      setTimeout(() => { globalThis.location.href = '/login' }, 3000)
                    } catch (err) {
                      setError(err.message || 'Restore failed')
                    } finally {
                      setRestoring(false)
                    }
                  }}
                  disabled={restoring}
                  className="w-full py-2.5 bg-emerald-600 text-white rounded-lg font-medium disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {restoring ? <><Loader2 className="w-4 h-4 animate-spin" /> Restoring...</> : 'Restore Backup'}
                </button>
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
