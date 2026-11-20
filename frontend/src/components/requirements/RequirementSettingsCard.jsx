import { useState } from 'react'
import { Loader2 } from 'lucide-react'

const INPUT = 'w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50'
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
  'September', 'October', 'November', 'December']

/**
 * Grace days, the fiscal year start month and the requirement emails switch.
 * `settings` is null until it loads; `onSave({ grace_days, fiscal_year_start_month, emails_enabled })` resolves to
 * whether it saved; it reports its own errors.
 */
export default function RequirementSettingsCard({ settings, onSave }) {
  const [form, setForm] = useState(null)
  const [saving, setSaving] = useState(false)
  // Show the loaded values until the user edits one.
  const shown = form || settings || { grace_days: '', fiscal_year_start_month: 10, emails_enabled: false }

  const save = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      const saved = await onSave({
        grace_days: Number.parseInt(shown.grace_days, 10),
        fiscal_year_start_month: Number(shown.fiscal_year_start_month),
        emails_enabled: shown.emails_enabled === true,
      })
      if (saved) setForm(null)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={save} aria-labelledby="req-settings-title" className="bg-card border border-border rounded-xl p-6">
      <h2 id="req-settings-title" className="text-lg font-semibold text-foreground mb-1">Requirement Settings</h2>
      <p className="text-sm text-muted-foreground mb-4">
        Grace days give reviewers time to finish reviewing flights after a period ends, before its results are saved.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="req-grace" className="block text-sm font-medium text-foreground mb-1">Grace days</label>
          <input id="req-grace" type="number" inputMode="numeric" min={0} max={60} required disabled={!settings}
            value={shown.grace_days} onChange={e => setForm({ ...shown, grace_days: e.target.value })} className={INPUT} />
        </div>
        <div>
          <label htmlFor="req-fiscal" className="block text-sm font-medium text-foreground mb-1">Fiscal year starts in</label>
          <select id="req-fiscal" disabled={!settings} value={shown.fiscal_year_start_month}
            onChange={e => setForm({ ...shown, fiscal_year_start_month: e.target.value })} className={INPUT}>
            {MONTHS.map((name, i) => <option key={name} value={i + 1}>{name}</option>)}
          </select>
        </div>
      </div>
      <div className="mt-4 flex items-start gap-2">
        <input id="req-emails" type="checkbox" disabled={!settings} checked={shown.emails_enabled === true}
          onChange={e => setForm({ ...shown, emails_enabled: e.target.checked })} className="mt-1" />
        <div>
          <label htmlFor="req-emails" className="block text-sm font-medium text-foreground">Send requirement emails</label>
          <p className="text-sm text-muted-foreground">
            Emails each pilot an assignment, a reminder before the period ends and a missed requirement, and tells
            managers about misses. Off until you turn it on. SMTP must be set up in Settings.
          </p>
        </div>
      </div>
      <button type="submit" disabled={!settings || saving}
        className="mt-4 flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50">
        {saving && <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />}
        Save settings
      </button>
    </form>
  )
}
