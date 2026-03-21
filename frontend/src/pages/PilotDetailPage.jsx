import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '@/api/client'
import { formatHours, formatDuration } from '@/lib/utils'
import { ArrowLeft, Plane, Clock, Calendar, ShieldCheck, FileText } from 'lucide-react'

const STATUS_COLORS = {
  not_issued: 'bg-zinc-500/15 text-zinc-400',
  not_eligible: 'bg-zinc-500/15 text-zinc-400',
  not_started: 'bg-zinc-500/15 text-zinc-400',
  in_progress: 'bg-blue-500/15 text-blue-400',
  pending: 'bg-amber-500/15 text-amber-400',
  complete: 'bg-emerald-500/15 text-emerald-400',
  active: 'bg-emerald-500/15 text-emerald-400',
  expired: 'bg-red-500/15 text-red-400',
}

export default function PilotDetailPage() {
  const { id } = useParams()
  const [pilot, setPilot] = useState(null)
  const [stats, setStats] = useState(null)
  const [flights, setFlights] = useState([])
  const [certifications, setCertifications] = useState([])
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      api.get(`/pilots/${id}`),
      api.get(`/pilots/${id}/stats`),
      api.get(`/flights?pilot_id=${id}&limit=20`),
      api.get(`/pilot-certifications?pilot_id=${id}`).catch(() => []),
      api.get(`/documents?entity_type=pilot&entity_id=${id}`).catch(() => []),
    ]).then(([p, s, f, c, d]) => {
      setPilot(p)
      setStats(s)
      setFlights(f)
      setCertifications(c)
      setDocuments(d)
    }).catch(console.error).finally(() => setLoading(false))
  }, [id])

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
  if (!pilot) return <div className="text-center text-muted-foreground py-12">Pilot not found</div>

  return (
    <div className="space-y-6">
      <Link to="/pilots" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="w-4 h-4" /> Back to Pilots
      </Link>

      {/* Profile Header */}
      <div className="bg-card border border-border rounded-xl p-6">
        <div className="flex items-start gap-4">
          <div className="w-16 h-16 rounded-2xl bg-primary/15 flex items-center justify-center text-primary text-xl font-bold">
            {pilot.first_name[0]}{pilot.last_name[0]}
          </div>
          <div className="flex-1">
            <h2 className="text-xl font-bold text-foreground">{pilot.full_name}</h2>
            <div className="flex flex-wrap gap-4 mt-2 text-sm text-muted-foreground">
              {pilot.email && <span>{pilot.email}</span>}
              {pilot.phone && <span>{pilot.phone}</span>}
              {pilot.badge_number && <span>Badge: {pilot.badge_number}</span>}
            </div>
            <span className={`inline-flex mt-2 px-2 py-0.5 rounded-full text-xs font-medium ${
              pilot.status === 'active' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-red-500/15 text-red-400'
            }`}>
              {pilot.status}
            </span>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary/15 flex items-center justify-center text-primary"><Plane className="w-5 h-5" /></div>
          <div><p className="text-2xl font-bold text-foreground">{stats?.total_flights || 0}</p><p className="text-xs text-muted-foreground">Total Flights</p></div>
        </div>
        <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-500/15 flex items-center justify-center text-blue-400"><Clock className="w-5 h-5" /></div>
          <div><p className="text-2xl font-bold text-foreground">{formatHours(stats?.total_flight_hours * 3600 || 0)}</p><p className="text-xs text-muted-foreground">Flight Hours</p></div>
        </div>
        <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-500/15 flex items-center justify-center text-emerald-400"><Calendar className="w-5 h-5" /></div>
          <div><p className="text-2xl font-bold text-foreground">{formatDuration(stats?.avg_flight_duration_seconds || 0)}</p><p className="text-xs text-muted-foreground">Avg Duration</p></div>
        </div>
      </div>

      {/* Recent Flights */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-border"><h3 className="font-semibold text-foreground">Recent Flights</h3></div>
        <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/30">
              <th className="text-left px-4 py-2 text-muted-foreground font-medium">Date</th>
              <th className="text-left px-4 py-2 text-muted-foreground font-medium">Vehicle</th>
              <th className="text-left px-4 py-2 text-muted-foreground font-medium hidden md:table-cell">Purpose</th>
              <th className="text-left px-4 py-2 text-muted-foreground font-medium">Duration</th>
              <th className="text-left px-4 py-2 text-muted-foreground font-medium hidden md:table-cell">Location</th>
            </tr>
          </thead>
          <tbody>
            {flights.map(f => (
              <tr key={f.id} className="border-b border-border/50 hover:bg-accent/30">
                <td className="px-4 py-2 text-foreground"><Link to={`/flights/${f.id}`} className="hover:text-primary">{f.date || '—'}</Link></td>
                <td className="px-4 py-2 text-muted-foreground">{f.vehicle_name || '—'}</td>
                <td className="px-4 py-2 text-muted-foreground hidden md:table-cell">{f.purpose || '—'}</td>
                <td className="px-4 py-2 text-muted-foreground">{formatDuration(f.duration_seconds)}</td>
                <td className="px-4 py-2 text-muted-foreground truncate max-w-[200px] hidden md:table-cell">{f.takeoff_address || '—'}</td>
              </tr>
            ))}
            {flights.length === 0 && <tr><td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">No flights yet</td></tr>}
          </tbody>
        </table>
        </div>
      </div>

      {/* Certifications */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-primary" />
          <h3 className="font-semibold text-foreground">Certifications</h3>
        </div>
        <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/30">
              <th className="text-left px-4 py-2 text-muted-foreground font-medium">Certification</th>
              <th className="text-left px-4 py-2 text-muted-foreground font-medium">Status</th>
              <th className="text-left px-4 py-2 text-muted-foreground font-medium hidden md:table-cell">Issue Date</th>
              <th className="text-left px-4 py-2 text-muted-foreground font-medium">Expiration</th>
              <th className="text-left px-4 py-2 text-muted-foreground font-medium hidden md:table-cell">Certificate #</th>
            </tr>
          </thead>
          <tbody>
            {certifications.map(c => (
              <tr key={c.id} className="border-b border-border/50 hover:bg-accent/30">
                <td className="px-4 py-2 text-foreground font-medium">{c.cert_type_name}</td>
                <td className="px-4 py-2">
                  <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[c.status] || STATUS_COLORS.not_started}`}>
                    {(c.status || 'not_started').replace(/_/g, ' ')}
                  </span>
                </td>
                <td className="px-4 py-2 text-muted-foreground hidden md:table-cell">{c.issue_date || '—'}</td>
                <td className="px-4 py-2 text-muted-foreground">{c.expiration_date || '—'}</td>
                <td className="px-4 py-2 text-muted-foreground hidden md:table-cell">{c.certificate_number || '—'}</td>
              </tr>
            ))}
            {certifications.length === 0 && <tr><td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">No certifications assigned</td></tr>}
          </tbody>
        </table>
        </div>
      </div>

      {/* Documents */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center gap-2">
          <FileText className="w-4 h-4 text-primary" />
          <h3 className="font-semibold text-foreground">Documents</h3>
        </div>
        <div className="divide-y divide-border/50">
          {documents.map(doc => (
            <button
              key={doc.id}
              onClick={() => window.open(doc.view_url, '_blank')}
              className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-accent/30 transition-colors"
            >
              <FileText className="w-4 h-4 text-muted-foreground shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-foreground truncate">{doc.title || doc.filename}</p>
                <p className="text-xs text-muted-foreground">{doc.mime_type}</p>
              </div>
            </button>
          ))}
          {documents.length === 0 && (
            <div className="px-4 py-8 text-center text-muted-foreground text-sm">No documents uploaded</div>
          )}
        </div>
      </div>
    </div>
  )
}
