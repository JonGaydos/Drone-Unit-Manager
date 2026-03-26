import { useState } from 'react'
import { api } from '@/api/client'
import { Plane, Shield, ArrowRight } from 'lucide-react'

export default function SetupPage() {
  const [step, setStep] = useState(1)
  const [form, setForm] = useState({
    display_name: '',
    org_name: '',
    username: '',
    password: '',
    password_confirm: '',
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

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
      window.location.href = '/'
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
            <Plane className="w-8 h-8 text-primary" />
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
                <label className="block text-sm font-medium mb-1">Organization Name</label>
                <input
                  type="text"
                  value={form.org_name}
                  onChange={e => setForm({...form, org_name: e.target.value})}
                  placeholder="e.g., Walton County Sheriff's Office"
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Your Name</label>
                <input
                  type="text"
                  value={form.display_name}
                  onChange={e => setForm({...form, display_name: e.target.value})}
                  placeholder="e.g., Jonathan Gaydos"
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground"
                />
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
                <label className="block text-sm font-medium mb-1">Username</label>
                <input
                  type="text"
                  value={form.username}
                  onChange={e => setForm({...form, username: e.target.value})}
                  placeholder="Choose a username"
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Password</label>
                <input
                  type="password"
                  value={form.password}
                  onChange={e => setForm({...form, password: e.target.value})}
                  placeholder="Min 12 chars, 1 uppercase, 1 number"
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Confirm Password</label>
                <input
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

        <p className="text-center text-xs text-muted-foreground mt-4">
          This account will have full administrator access.
        </p>
      </div>
    </div>
  )
}
