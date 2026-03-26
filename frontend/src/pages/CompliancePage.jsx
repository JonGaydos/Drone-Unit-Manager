import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '@/api/client'
import { useToast } from '@/contexts/ToastContext'
import {
  ShieldCheck, AlertTriangle, Clock, Wrench, Plane, FileText,
  ClipboardCheck, Loader2, ChevronRight, RefreshCw, Download,
} from 'lucide-react'

function ScoreCircle({ score }) {
  const color = score > 80 ? 'text-emerald-400' : score > 60 ? 'text-amber-400' : 'text-red-400'
  const bgColor = score > 80 ? 'bg-emerald-500/10' : score > 60 ? 'bg-amber-500/10' : 'bg-red-500/10'
  const borderColor = score > 80 ? 'border-emerald-500/30' : score > 60 ? 'border-amber-500/30' : 'border-red-500/30'
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

export default function CompliancePage() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const toast = useToast()
  const navigate = useNavigate()

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

  // Build attention items list
  const attentionItems = []
  if (data.expired_certifications > 0) {
    attentionItems.push({
      type: 'Expired Certifications',
      count: data.expired_certifications,
      severity: 'critical',
      link: '/certifications',
    })
  }
  if (data.expiring_certifications?.length > 0) {
    for (const c of data.expiring_certifications) {
      attentionItems.push({
        type: 'Expiring Certification',
        detail: `Pilot #${c.pilot_id} - ${c.days_remaining} days remaining`,
        severity: c.days_remaining <= 30 ? 'high' : 'medium',
        link: '/certifications',
      })
    }
  }
  if (data.expired_registrations > 0) {
    attentionItems.push({
      type: 'Expired FAA Registrations',
      count: data.expired_registrations,
      severity: 'critical',
      link: '/fleet',
    })
  }
  if (data.overdue_maintenance > 0) {
    attentionItems.push({
      type: 'Overdue Maintenance',
      count: data.overdue_maintenance,
      severity: 'high',
      link: '/maintenance',
    })
  }
  if (data.open_incidents > 0) {
    attentionItems.push({
      type: 'Open Incidents',
      count: data.open_incidents,
      severity: 'high',
      link: '/incidents',
    })
  }
  if (data.unreviewed_flights > 0) {
    attentionItems.push({
      type: 'Unreviewed Flights',
      count: data.unreviewed_flights,
      severity: 'medium',
      link: '/flights',
    })
  }
  if (data.pending_flight_plans > 0) {
    attentionItems.push({
      type: 'Pending Flight Plans',
      count: data.pending_flight_plans,
      severity: 'low',
      link: '/flight-plans',
    })
  }

  // Sort by severity
  const severityOrder = { critical: 0, high: 1, medium: 2, low: 3 }
  attentionItems.sort((a, b) => (severityOrder[a.severity] ?? 9) - (severityOrder[b.severity] ?? 9))

  const severityBadge = {
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
            icon={Plane}
            label="Unreviewed Flights"
            value={data.unreviewed_flights}
            color={data.unreviewed_flights > 0 ? 'amber' : 'emerald'}
            onClick={() => navigate('/flights')}
          />
        </div>
      </div>

      {/* Summary Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
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
      </div>

      {/* Attention Items Table */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-border flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">Items Requiring Attention</h2>
          <span className="text-sm text-muted-foreground">{attentionItems.length} item{attentionItems.length !== 1 ? 's' : ''}</span>
        </div>
        {attentionItems.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground">
            <ShieldCheck className="w-10 h-10 mx-auto mb-3 text-emerald-400" />
            <p className="font-medium text-foreground">All Clear</p>
            <p className="text-sm mt-1">No compliance issues found. Great job!</p>
          </div>
        ) : (
          <div className="divide-y divide-border">
            {attentionItems.map((item, i) => (
              <button
                key={i}
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
    </div>
  )
}
