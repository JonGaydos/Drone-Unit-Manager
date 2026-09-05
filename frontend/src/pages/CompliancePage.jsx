import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '@/api/client'
import { useToast } from '@/contexts/ToastContext'
import {
  ShieldCheck, AlertTriangle, Clock, Wrench, FileText,
  ClipboardCheck, Loader2, ChevronRight, RefreshCw, Download, Send, Users, Mail, Stamp,
} from 'lucide-react'
import { QuadcopterIcon } from '@/components/icons/QuadcopterIcon'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { useConfirm } from '@/hooks/useConfirm'
import { daysUntil } from '@/lib/utils'

function getScoreTheme(score) {
  if (score > 80) return { color: 'text-emerald-400', bg: 'bg-emerald-500/10', border: 'border-emerald-500/30' }
  if (score > 60) return { color: 'text-amber-400', bg: 'bg-amber-500/10', border: 'border-amber-500/30' }
  return { color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/30' }
}

function ScoreCircle({ score }) {
  const { color, bg: bgColor, border: borderColor } = getScoreTheme(score)
  const circumference = 2 * Math.PI * 54
  const offset = circumference - (score / 100) * circumference

  return (
    <div className={`relative inline-flex items-center justify-center w-44 h-44 rounded-full ${bgColor} border-2 ${borderColor}`}>
      <svg className="absolute w-36 h-36 -rotate-90" viewBox="0 0 120 120">
        <circle cx="60" cy="60" r="54" fill="none" stroke="currentColor" strokeWidth="8" className="text-border/30" />
        <circle
          cx="60" cy="60" r="54" fill="none" strokeWidth="8"
          stroke="currentColor"
          className={color}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 1s ease-in-out' }}
        />
      </svg>
      <div className="text-center z-10">
        <div className={`text-4xl font-bold ${color}`}>{score}</div>
        <div className="text-xs text-muted-foreground mt-0.5">/ 100</div>
      </div>
    </div>
  )
}

function StatCard({ icon: Icon, label, value, color, onClick }) {
  const colorMap = {
    red: 'bg-red-500/10 border-red-500/30 text-red-400',
    amber: 'bg-amber-500/10 border-amber-500/30 text-amber-400',
    emerald: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400',
    blue: 'bg-blue-500/10 border-blue-500/30 text-blue-400',
    purple: 'bg-purple-500/10 border-purple-500/30 text-purple-400',
  }
  const classes = colorMap[color] || colorMap.blue

  return (
    <button
      onClick={onClick}
      className={`flex flex-col items-center gap-2 p-4 rounded-xl border ${classes} hover:brightness-110 transition-all cursor-pointer min-w-[130px]`}
    >
      <Icon className="w-5 h-5" />
      <span className="text-2xl font-bold">{value}</span>
      <span className="text-xs text-muted-foreground text-center leading-tight">{label}</span>
    </button>
  )
}

function buildAttentionItems(data) {
  const items = []
  if (data.expired_certifications > 0) {
    items.push({ type: 'Expired Certifications', count: data.expired_certifications, severity: 'critical', link: '/certifications' })
  }
  if (data.expiring_certifications?.length > 0) {
    for (const c of data.expiring_certifications) {
      items.push({
        type: 'Expiring Certification',
        detail: `Pilot #${c.pilot_id} - ${c.days_remaining} days remaining`,
        severity: c.days_remaining <= 30 ? 'high' : 'medium',
        link: '/certifications',
      })
    }
  }
  if (data.expired_registrations > 0) {
    items.push({ type: 'Expired FAA Registrations', count: data.expired_registrations, severity: 'critical', link: '/fleet' })
  }
  // Operating authority is org-level: an expired one the unit depends on means
  // every flight is unauthorised, so it outranks any per-pilot or per-aircraft item.
  for (const a of data.expired_authorities || []) {
    items.push({
      type: a.grounds_unit ? 'Operating Authority Expired' : 'Operating Authority Expired (restricted operations)',
      detail: a.identifier ? `${a.title} (${a.identifier})` : a.title,
      severity: a.grounds_unit ? 'grounding' : 'critical',
      link: '/operating-authority',
    })
  }
  for (const a of data.expiring_authorities || []) {
    items.push({
      type: 'Operating Authority Expiring',
      detail: `${a.title} - ${a.days_remaining} days remaining`,
      severity: a.days_remaining <= 30 ? 'high' : 'medium',
      link: '/operating-authority',
    })
  }
  if (data.overdue_maintenance > 0) {
    items.push({ type: 'Overdue Maintenance', count: data.overdue_maintenance, severity: 'high', link: '/maintenance' })
  }
  if (data.open_incidents > 0) {
    items.push({ type: 'Open Incidents', count: data.open_incidents, severity: 'high', link: '/incidents' })
  }
  if (data.unreviewed_flights > 0) {
    items.push({ type: 'Unreviewed Flights', count: data.unreviewed_flights, severity: 'medium', link: '/flights' })
  }
  if (data.pending_flight_plans > 0) {
    items.push({ type: 'Pending Flight Plans', count: data.pending_flight_plans, severity: 'low', link: '/flight-plans' })
  }
  if (data.pilots_lapsed > 0) {
    items.push({ type: 'Pilots Out of Currency', count: data.pilots_lapsed, severity: 'high', link: '#currency' })
  }
  // Pilots expiring currency within 14 days (and currently still current)
  const expiringSoon = (data.pilot_currency_status || []).filter(p => {
    if (!p.is_current || !p.earliest_expires_date) return false
    const days = daysUntil(p.earliest_expires_date)
    return days !== null && days >= 0 && days <= 14
  }).length
  if (expiringSoon > 0) {
    items.push({ type: 'Pilots Expiring Currency Soon', count: expiringSoon, severity: 'medium', link: '#currency' })
  }
  const severityOrder = { grounding: -1, critical: 0, high: 1, medium: 2, low: 3 }
  items.sort((a, b) => (severityOrder[a.severity] ?? 9) - (severityOrder[b.severity] ?? 9))
  return items
}

function CurrencyStatusSection({ data, onSendReminders, sending }) {
  const [filter, setFilter] = useState('lapsed-and-soon')  // 'all' | 'lapsed' | 'lapsed-and-soon'
  const [expanded, setExpanded] = useState(false)
  const navigate = useNavigate()

  const enriched = useMemo(() => {
    return (data.pilot_currency_status || []).map(p => {
      let daysUntilExpiry = null
      if (p.is_current && p.earliest_expires_date) {
        daysUntilExpiry = daysUntil(p.earliest_expires_date)
      }
      return { ...p, daysUntilExpiry }
    }).sort((a, b) => {
      // Lapsed first; then by ascending days-until-expiry; then by name.
      if (a.is_current !== b.is_current) return a.is_current ? 1 : -1
      const ad = a.daysUntilExpiry ?? 9999
      const bd = b.daysUntilExpiry ?? 9999
      if (ad !== bd) return ad - bd
      return (a.pilot_name || '').localeCompare(b.pilot_name || '')
    })
  }, [data.pilot_currency_status])

  const filtered = useMemo(() => {
    if (filter === 'all') return enriched
    if (filter === 'lapsed') return enriched.filter(p => !p.is_current)
    return enriched.filter(p => !p.is_current || (p.daysUntilExpiry !== null && p.daysUntilExpiry <= 30))
  }, [enriched, filter])

  const shown = expanded ? filtered : filtered.slice(0, 8)

  if (data.currency_rules_active === 0) {
    return (
      <div id="currency" className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-border flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
            <Users className="w-5 h-5 text-primary" /> Pilot Currency Status
          </h2>
        </div>
        <div className="p-8 text-center text-muted-foreground">
          <p className="font-medium text-foreground">No currency rules defined</p>
          <p className="text-sm mt-1">Add rules in Settings → Currency Rules to start tracking pilot currency.</p>
          <button
            onClick={() => navigate('/settings')}
            className="mt-4 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90"
          >
            Open Settings
          </button>
        </div>
      </div>
    )
  }

  return (
    <div id="currency" className="bg-card border border-border rounded-xl overflow-hidden">
      <div className="px-5 py-4 border-b border-border flex items-center justify-between gap-2 flex-wrap">
        <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
          <Users className="w-5 h-5 text-primary" /> Pilot Currency Status
          <span className="text-sm font-normal text-muted-foreground ml-2">
            {data.pilots_lapsed} lapsed / {data.total_pilots} total
          </span>
        </h2>
        <div className="flex items-center gap-2">
          <select
            value={filter}
            onChange={e => { setFilter(e.target.value); setExpanded(false) }}
            className="px-2 py-1 text-xs bg-secondary border border-border rounded-lg text-foreground"
          >
            <option value="lapsed-and-soon">Lapsed + Expiring 30d</option>
            <option value="lapsed">Lapsed only</option>
            <option value="all">All pilots</option>
          </select>
          <button
            onClick={onSendReminders}
            disabled={sending || data.pilots_lapsed === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-primary text-primary-foreground rounded-lg disabled:opacity-50 hover:opacity-90"
            title={data.pilots_lapsed === 0 ? 'No lapsed pilots to remind' : 'Email a reminder to every lapsed pilot with an email on file'}
          >
            {sending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
            Send Reminders
          </button>
        </div>
      </div>
      {filtered.length === 0 ? (
        <div className="p-8 text-center text-muted-foreground">
          <ShieldCheck className="w-10 h-10 mx-auto mb-3 text-emerald-400" />
          <p className="font-medium text-foreground">All pilots current</p>
          <p className="text-sm mt-1">Nobody is lapsed or expiring within 30 days.</p>
        </div>
      ) : (
        <>
          <div className="divide-y divide-border">
            {shown.map(p => {
              let badgeClasses, badgeText
              if (!p.is_current) {
                badgeClasses = 'bg-red-500/15 text-red-400 border-red-500/30'
                badgeText = 'LAPSED'
              } else if (p.daysUntilExpiry !== null && p.daysUntilExpiry <= 14) {
                badgeClasses = 'bg-amber-500/15 text-amber-400 border-amber-500/30'
                badgeText = `${p.daysUntilExpiry}d`
              } else if (p.daysUntilExpiry !== null && p.daysUntilExpiry <= 30) {
                badgeClasses = 'bg-blue-500/15 text-blue-400 border-blue-500/30'
                badgeText = `${p.daysUntilExpiry}d`
              } else {
                badgeClasses = 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                badgeText = 'CURRENT'
              }
              return (
                <button
                  key={p.pilot_id}
                  onClick={() => navigate(`/pilots/${p.pilot_id}`)}
                  className="w-full flex items-center gap-3 px-5 py-3 hover:bg-secondary/50 transition-colors text-left"
                >
                  <span className={`inline-flex items-center justify-center px-2 py-0.5 rounded-full text-xs font-medium border w-20 ${badgeClasses}`}>
                    {badgeText}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-foreground truncate">{p.pilot_name}</p>
                    <p className="text-xs text-muted-foreground truncate flex gap-2 flex-wrap mt-0.5">
                      {p.rules.map(r => {
                        const ratioOk = r.actual_hours >= r.required_hours
                        const colorCls = r.is_current ? 'text-emerald-400' : 'text-red-400'
                        return (
                          <span key={r.rule_id} className={colorCls}>
                            {r.rule_name}: {r.actual_hours}/{r.required_hours} hours flown
                            {r.required_flights ? `, ${r.actual_flights}/${r.required_flights} flights` : ''}
                            {` in the last ${r.period_days} days`}
                            {!ratioOk && r.is_current ? ' ✓' : ''}
                          </span>
                        )
                      })}
                    </p>
                  </div>
                  {p.email ? (
                    <Mail className="w-3.5 h-3.5 text-muted-foreground" title={p.email} />
                  ) : (
                    <span className="text-xs text-amber-400" title="No email on file">no email</span>
                  )}
                  <ChevronRight className="w-4 h-4 text-muted-foreground" />
                </button>
              )
            })}
          </div>
          {filtered.length > shown.length && (
            <button
              onClick={() => setExpanded(true)}
              className="w-full px-5 py-2 text-sm text-primary hover:bg-secondary/50 transition-colors border-t border-border"
            >
              Show all {filtered.length} pilots
            </button>
          )}
        </>
      )}
    </div>
  )
}

// A dash rather than a percentage when no currency rule exists at all: 100%
// against no rule reads as a pass the unit has not actually earned.
function currencyCompliance(data) {
  if (data.currency_rules_active === 0) return '—'
  // Falsy rather than <= 0, so a missing or unparsed count does not divide.
  if (!data.total_pilots) return '100%'
  return `${Math.round((data.pilots_current / data.total_pilots) * 100)}%`
}

export default function CompliancePage() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const toast = useToast()
  const navigate = useNavigate()
  const [confirmProps, requestConfirm] = useConfirm()

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.get('/dashboard/compliance')
      setData(res)
    } catch (err) {
      toast.error(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleSendReminders = async () => {
    if (!data || data.pilots_lapsed === 0) return
    requestConfirm({
      title: 'Send currency reminders',
      message: `Send currency reminder emails to ${data.pilots_lapsed} lapsed pilot${data.pilots_lapsed === 1 ? '' : 's'}? Pilots without an email on file will be skipped.`,
      confirmLabel: 'Send',
      confirmVariant: 'primary',
      onConfirm: async () => {
        setSending(true)
        try {
          const res = await api.post('/currency/send-reminders', {}, { timeout: 120000 })
          const bits = [`${res.sent} sent`]
          if (res.skipped_no_email) bits.push(`${res.skipped_no_email} skipped (no email)`)
          if (res.skipped_current) bits.push(`${res.skipped_current} already current`)
          if (res.failed) bits.push(`${res.failed} failed`)
          toast.success(`Reminders: ${bits.join(', ')}`)
        } catch (err) {
          toast.error(err.message)
        } finally { setSending(false) }
      },
    })
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    )
  }

  if (!data) {
    return (
      <div className="p-6 text-center text-muted-foreground">
        Failed to load compliance data.
      </div>
    )
  }

  const attentionItems = buildAttentionItems(data)

  const severityBadge = {
    // Filled rather than outlined: a grounded unit is not the same class of
    // problem as one pilot's lapsed certificate.
    grounding: 'bg-red-600 text-white border-red-500',
    critical: 'bg-red-500/15 text-red-400 border-red-500/30',
    high: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
    medium: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    low: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  }

  return (
    <div className="p-4 md:p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <ShieldCheck className="w-7 h-7 text-primary" />
          <h1 className="text-2xl font-bold text-foreground">Compliance Dashboard</h1>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => api.download('/export/equipment-checkouts/csv')}
            className="flex items-center gap-2 px-3 py-2 text-sm bg-secondary border border-border rounded-lg text-muted-foreground hover:text-foreground transition-colors"
          >
            <Download className="w-4 h-4" /> Export CSV
          </button>
          <button
            onClick={load}
            className="flex items-center gap-2 px-3 py-2 text-sm bg-secondary border border-border rounded-lg text-muted-foreground hover:text-foreground transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </div>
      </div>

      {/* Score + Stats Row */}
      <div className="flex flex-col lg:flex-row items-center gap-6">
        {/* Score Circle */}
        <div className="flex flex-col items-center gap-2">
          <ScoreCircle score={data.compliance_score} />
          <span className="text-sm font-medium text-muted-foreground">Compliance Score</span>
          {data.score_cap_reason && (
            <span className="text-xs text-red-400 text-center max-w-[12rem] leading-snug">
              {data.score_cap_reason}
            </span>
          )}
        </div>

        {/* Stat Cards */}
        <div className="flex-1 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          <StatCard
            icon={AlertTriangle}
            label="Expired Certs"
            value={data.expired_certifications}
            color={data.expired_certifications > 0 ? 'red' : 'emerald'}
            onClick={() => navigate('/certifications')}
          />
          <StatCard
            icon={Clock}
            label="Expiring Soon"
            value={data.expiring_certifications?.length || 0}
            color={data.expiring_certifications?.length > 0 ? 'amber' : 'emerald'}
            onClick={() => navigate('/certifications')}
          />
          <StatCard
            icon={FileText}
            label="Expired Registrations"
            value={data.expired_registrations}
            color={data.expired_registrations > 0 ? 'red' : 'emerald'}
            onClick={() => navigate('/fleet')}
          />
          <StatCard
            icon={Stamp}
            label="Expired Authorities"
            value={data.expired_authorities?.length || 0}
            color={data.expired_authorities?.length > 0 ? 'red' : 'emerald'}
            onClick={() => navigate('/operating-authority')}
          />
          <StatCard
            icon={Wrench}
            label="Overdue Maintenance"
            value={data.overdue_maintenance}
            color={data.overdue_maintenance > 0 ? 'red' : 'emerald'}
            onClick={() => navigate('/maintenance')}
          />
          <StatCard
            icon={AlertTriangle}
            label="Open Incidents"
            value={data.open_incidents}
            color={data.open_incidents > 0 ? 'amber' : 'emerald'}
            onClick={() => navigate('/incidents')}
          />
          <StatCard
            icon={ClipboardCheck}
            label="Pending Approvals"
            value={data.pending_flight_plans}
            color={data.pending_flight_plans > 0 ? 'blue' : 'emerald'}
            onClick={() => navigate('/flight-plans')}
          />
          <StatCard
            icon={QuadcopterIcon}
            label="Unreviewed Flights"
            value={data.unreviewed_flights}
            color={data.unreviewed_flights > 0 ? 'amber' : 'emerald'}
            onClick={() => navigate('/flights')}
          />
          <StatCard
            icon={Users}
            label="Out of Currency"
            value={data.pilots_lapsed || 0}
            color={data.pilots_lapsed > 0 ? 'red' : 'emerald'}
            onClick={() => {
              const el = document.getElementById('currency')
              if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
            }}
          />
        </div>
      </div>

      {/* Summary Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        <div className="bg-card border border-border rounded-xl p-4 text-center">
          <div className="text-sm text-muted-foreground">Active Pilots</div>
          <div className="text-2xl font-bold text-foreground mt-1">{data.total_pilots}</div>
        </div>
        <div className="bg-card border border-border rounded-xl p-4 text-center">
          <div className="text-sm text-muted-foreground">Active Vehicles</div>
          <div className="text-2xl font-bold text-foreground mt-1">{data.total_vehicles}</div>
        </div>
        <div className="bg-card border border-border rounded-xl p-4 text-center">
          <div className="text-sm text-muted-foreground">Cert Compliance</div>
          <div className="text-2xl font-bold text-foreground mt-1">
            {data.total_pilots > 0 ? Math.round(((data.total_pilots - data.expired_certifications) / data.total_pilots) * 100) : 100}%
          </div>
        </div>
        <div className="bg-card border border-border rounded-xl p-4 text-center">
          <div className="text-sm text-muted-foreground">Reg Compliance</div>
          <div className="text-2xl font-bold text-foreground mt-1">
            {data.total_vehicles > 0 ? Math.round(((data.total_vehicles - data.expired_registrations) / data.total_vehicles) * 100) : 100}%
          </div>
        </div>
        <div className="bg-card border border-border rounded-xl p-4 text-center">
          <div className="text-sm text-muted-foreground">Currency Compliance</div>
          <div className="text-2xl font-bold text-foreground mt-1">
            {currencyCompliance(data)}
          </div>
          {data.currency_rules_active === 0 && (
            <div className="text-[10px] text-muted-foreground mt-0.5">no rules</div>
          )}
        </div>
      </div>

      {/* Pilot Currency Status */}
      <CurrencyStatusSection
        data={data}
        sending={sending}
        onSendReminders={handleSendReminders}
      />

      {/* Attention Items Table */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-border flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">Items Requiring Attention</h2>
          <span className="text-sm text-muted-foreground">{attentionItems.length} item{attentionItems.length === 1 ? '' : 's'}</span>
        </div>
        {attentionItems.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground">
            <ShieldCheck className="w-10 h-10 mx-auto mb-3 text-emerald-400" />
            <p className="font-medium text-foreground">All Clear</p>
            <p className="text-sm mt-1">No compliance issues found. Great job!</p>
          </div>
        ) : (
          <div className="divide-y divide-border">
            {attentionItems.map((item) => (
              <button
                key={`${item.severity}-${item.type}-${item.count || ''}-${item.detail || ''}`}
                onClick={() => navigate(item.link)}
                className="w-full flex items-center gap-3 px-5 py-3 hover:bg-secondary/50 transition-colors text-left"
              >
                <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${severityBadge[item.severity]}`}>
                  {item.severity}
                </span>
                <span className="flex-1 text-sm text-foreground">
                  {item.type}
                  {item.count ? <span className="text-muted-foreground ml-1">({item.count})</span> : null}
                  {item.detail ? <span className="text-muted-foreground ml-2 text-xs">{item.detail}</span> : null}
                </span>
                <ChevronRight className="w-4 h-4 text-muted-foreground" />
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Generate Report Button */}
      <div className="flex justify-end">
        <button
          onClick={() => navigate('/reports')}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors text-sm font-medium"
        >
          <FileText className="w-4 h-4" />
          Generate Compliance Report
        </button>
      </div>

      <ConfirmDialog {...confirmProps} />
    </div>
  )
}
