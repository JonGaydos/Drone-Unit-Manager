import { useCallback, useEffect, useState } from 'react'
import { Loader2, Mail, Save, Eye, Send } from 'lucide-react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { formatDateTime } from '@/lib/utils'

// The digest categories, in the order the email lists them.
const DIGEST_CATEGORIES = [
  { key: 'pending_approvals', label: 'Pending Flight Plan Approvals' },
  { key: 'needs_review', label: 'Flights Needing Review' },
  { key: 'expiring_certs', label: 'Expiring Certifications' },
  { key: 'expiring_registrations', label: 'Expiring FAA Registrations' },
  { key: 'overdue_maintenance', label: 'Overdue Maintenance' },
  { key: 'assigned_missions', label: 'Assigned Missions' },
  { key: 'overdue_checkouts', label: 'Overdue Equipment Checkouts' },
  { key: 'recent_incidents', label: 'Recent Incidents' },
]

const CATEGORY_LABEL = Object.fromEntries(DIGEST_CATEGORIES.map(c => [c.key, c.label]))

const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

// The scheduler sends during the chosen hour, so whole hours are offered.
const HOURS = Array.from({ length: 24 }, (_, h) => `${String(h).padStart(2, '0')}:00`)

const STATUS_LABEL = { sent: 'Sent', failed: 'Failed', skipped: 'Skipped', test: 'Test' }

const inputClass = 'w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring'

/** How many items a preview section holds. Flights needing review arrive as
 *  one row carrying the count. */
function sectionCount(key, items) {
  if (key === 'needs_review' && items[0]?.count !== undefined) return items[0].count
  return items.length
}

/** Settings > General card where each user sets up their own email digest. */
export default function DigestPreferencesCard() {
  const { can } = useAuth()
  const toast = useToast()
  const canRedirect = can('digest.redirect')
  const [form, setForm] = useState(null)
  const [log, setLog] = useState([])
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState('')

  const loadLog = useCallback(() => {
    api.get('/notifications/log?limit=10')
      .then(rows => { if (Array.isArray(rows)) setLog(rows) })
      .catch(() => {})
  }, [])

  useEffect(() => {
    api.get('/notifications/preferences')
      .then(p => setForm({
        enabled: p.enabled !== false,
        frequency: p.frequency || 'daily',
        send_time: p.send_time || '07:00',
        send_day: p.send_day ?? 0,
        categories: Array.isArray(p.categories) ? p.categories : DIGEST_CATEGORIES.map(c => c.key),
        email_override: p.email_override || '',
      }))
      .catch(err => toast.error(`Could not load digest preferences: ${err.message}`))
    loadLog()
  }, [loadLog]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!form) return null

  const set = (patch) => setForm(f => ({ ...f, ...patch }))
  const toggleCategory = (key) => set({
    categories: form.categories.includes(key)
      ? form.categories.filter(c => c !== key)
      : DIGEST_CATEGORIES.map(c => c.key).filter(c => c === key || form.categories.includes(c)),
  })

  const save = async () => {
    setBusy('save')
    try {
      const payload = {
        enabled: form.enabled,
        frequency: form.frequency,
        send_time: form.send_time,
        send_day: form.frequency === 'weekly' ? Number(form.send_day) : null,
        categories: form.categories,
      }
      if (canRedirect) payload.email_override = form.email_override.trim()
      await api.put('/notifications/preferences', payload)
      toast.success('Digest preferences saved')
    } catch (err) {
      toast.error(err.message)
    } finally {
      setBusy('')
    }
  }

  const loadPreview = async () => {
    setBusy('preview')
    try {
      setPreview(await api.get('/notifications/preview'))
    } catch (err) {
      toast.error(err.message)
    } finally {
      setBusy('')
    }
  }

  const sendTest = async () => {
    setBusy('test')
    try {
      const res = await api.post('/notifications/send-test')
      if (res?.ok) toast.success(res.message)
      else toast.warning(res?.message || 'Test digest not sent')
      loadLog()
    } catch (err) {
      toast.error(err.message)
    } finally {
      setBusy('')
    }
  }

  const hourOptions = HOURS.includes(form.send_time) ? HOURS : [...HOURS, form.send_time].sort()
  const previewSections = preview && !preview.empty ? Object.entries(preview.sections || {}) : []

  return (
    <div className="bg-card border border-border rounded-xl p-6">
      <h3 className="text-lg font-semibold text-foreground mb-1 flex items-center gap-2">
        <Mail className="w-5 h-5" /> Email Digest
      </h3>
      <p className="text-sm text-muted-foreground mb-4">
        A summary of items that need your attention, sent by email once SMTP is set up on the Integrations tab.
        Each section follows what your role can see.
      </p>

      <div className="space-y-4">
        <label className="flex items-center gap-2 cursor-pointer select-none">
          <input type="checkbox" checked={form.enabled} onChange={e => set({ enabled: e.target.checked })}
            className="w-4 h-4 rounded border-border text-primary focus:ring-ring" />
          <span className="text-sm text-foreground">Send me email digests</span>
        </label>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div>
            <label htmlFor="digest-frequency" className="block text-sm font-medium text-foreground mb-1">Frequency</label>
            <select id="digest-frequency" value={form.frequency} onChange={e => set({ frequency: e.target.value })} className={inputClass}>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="off">Off</option>
            </select>
          </div>
          {form.frequency === 'weekly' && (
            <div>
              <label htmlFor="digest-day" className="block text-sm font-medium text-foreground mb-1">Send on</label>
              <select id="digest-day" value={String(form.send_day)} onChange={e => set({ send_day: Number(e.target.value) })} className={inputClass}>
                {WEEKDAYS.map((d, i) => <option key={d} value={String(i)}>{d}</option>)}
              </select>
            </div>
          )}
          <div>
            <label htmlFor="digest-time" className="block text-sm font-medium text-foreground mb-1">Send at</label>
            <select id="digest-time" value={form.send_time} onChange={e => set({ send_time: e.target.value })} className={inputClass}>
              {hourOptions.map(h => <option key={h} value={h}>{h}</option>)}
            </select>
          </div>
        </div>

        <fieldset>
          <legend className="block text-sm font-medium text-foreground mb-1">Include</legend>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
            {DIGEST_CATEGORIES.map(c => (
              <label key={c.key} className="flex items-center gap-2 cursor-pointer select-none">
                <input type="checkbox" checked={form.categories.includes(c.key)} onChange={() => toggleCategory(c.key)}
                  className="w-4 h-4 rounded border-border text-primary focus:ring-ring" />
                <span className="text-sm text-foreground">{c.label}</span>
              </label>
            ))}
          </div>
        </fieldset>

        {canRedirect && (
          <div>
            <label htmlFor="digest-override" className="block text-sm font-medium text-foreground mb-1">Send to another address</label>
            <p className="text-xs text-muted-foreground mb-1.5">Leave blank to use the email on your account or linked pilot.</p>
            <input id="digest-override" type="email" value={form.email_override}
              onChange={e => set({ email_override: e.target.value })} className={inputClass} />
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          <button onClick={save} disabled={Boolean(busy)}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50">
            {busy === 'save' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Save Preferences
          </button>
          <button onClick={loadPreview} disabled={Boolean(busy)}
            className="flex items-center gap-2 px-4 py-2 bg-secondary border border-border rounded-lg text-sm text-foreground hover:bg-accent/30 disabled:opacity-50">
            {busy === 'preview' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Eye className="w-4 h-4" />}
            Preview
          </button>
          <button onClick={sendTest} disabled={Boolean(busy)}
            className="flex items-center gap-2 px-4 py-2 bg-secondary border border-border rounded-lg text-sm text-foreground hover:bg-accent/30 disabled:opacity-50">
            {busy === 'test' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            Send Test
          </button>
        </div>
        <p className="text-xs text-muted-foreground">Preview and Send Test use your saved preferences.</p>

        {preview && (
          <div className="p-3 bg-muted/20 border border-border rounded-lg text-sm">
            {preview.empty ? (
              <p className="text-muted-foreground">{preview.message || 'Nothing to report'}</p>
            ) : (
              <ul className="space-y-1">
                {previewSections.map(([key, items]) => (
                  <li key={key} className="text-foreground">
                    {`${CATEGORY_LABEL[key] || key}: ${sectionCount(key, items)}`}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {log.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" aria-label="Digest send log">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left px-2 py-1.5 font-medium text-muted-foreground">Date</th>
                  <th className="text-left px-2 py-1.5 font-medium text-muted-foreground">Status</th>
                  <th className="text-right px-2 py-1.5 font-medium text-muted-foreground">Items</th>
                </tr>
              </thead>
              <tbody>
                {log.map(row => (
                  <tr key={row.id} className="border-b border-border/50">
                    <td className="px-2 py-1.5 text-muted-foreground whitespace-nowrap">{formatDateTime(row.sent_at)}</td>
                    <td className="px-2 py-1.5 text-foreground" title={row.error_message || undefined}>{STATUS_LABEL[row.status] || row.status}</td>
                    <td className="px-2 py-1.5 text-right text-foreground">{row.item_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
