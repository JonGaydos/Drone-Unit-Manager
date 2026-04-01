import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { formatHours, formatDuration } from '@/lib/utils'
import { CERT_STATUS_COLORS } from '@/lib/constants'
import { ArrowLeft, Clock, Calendar, ShieldCheck, Edit, Save, X, Camera, CheckCircle, XCircle, Target, GraduationCap, AlertTriangle, TrendingUp } from 'lucide-react'
import { QuadcopterIcon } from '@/components/icons/QuadcopterIcon'
import {
  BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import DocumentUpload from '@/components/DocumentUpload'

export default function PilotDetailPage() {
  const { id } = useParams()
  const { isAdmin, isPilot, isSupervisor, user } = useAuth()
  const toast = useToast()

  // Auto-file documents to General folder
  const [generalFolderId, setGeneralFolderId] = useState(null)
  useEffect(() => {
    api.get('/folders').then(folders => {
      const f = (Array.isArray(folders) ? folders : folders.folders || []).find(f => f.name === 'General')
      if (f) setGeneralFolderId(f.id)
    }).catch(() => {})
  }, [])

  const [pilot, setPilot] = useState(null)
  const [stats, setStats] = useState(null)
  const [flights, setFlights] = useState([])
  const [certifications, setCertifications] = useState([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [editForm, setEditForm] = useState({})
  const [saving, setSaving] = useState(false)
  const [currencyStatus, setCurrencyStatus] = useState(null)
  const [performance, setPerformance] = useState(null)

  useEffect(() => {
    Promise.all([
      api.get(`/pilots/${id}`),
      api.get(`/pilots/${id}/stats`),
      api.get(`/flights?pilot_id=${id}&per_page=20`),
      api.get(`/pilot-certifications?pilot_id=${id}`).catch(() => []),
      api.get(`/currency/status/${id}`).catch(() => null),
      api.get(`/dashboard/analytics/pilot-performance/${id}`).catch(() => null),
    ]).then(([p, s, fData, c, cur, perf]) => {
      setPilot(p)
      setStats(s)
      setFlights(fData.flights || fData)
      setCertifications(c)
      setCurrencyStatus(cur)
      setPerformance(perf)
    }).catch(() => {}).finally(() => setLoading(false))
  }, [id])

  const startEditing = () => {
    setEditForm({
      first_name: pilot.first_name || '',
      last_name: pilot.last_name || '',
      email: pilot.email || '',
      phone: pilot.phone || '',
      phone_type: pilot.phone_type || 'work',
      phone_work: pilot.phone_work || '',
      badge_number: pilot.badge_number || '',
      status: pilot.status || 'active',
      notes: pilot.notes || '',
    })
    setEditing(true)
  }

  const cancelEditing = () => {
    setEditForm({})
    setEditing(false)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const updated = await api.patch(`/pilots/${id}`, editForm)
      setPilot(updated)
      setEditing(false)
    } catch (err) {
      toast.error(err.message)
    } finally {
      setSaving(false)
    }
  }

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
          <div className="relative shrink-0">
            {pilot.photo_url ? (
              <img src={pilot.photo_url} alt={pilot.full_name}
                className="w-16 h-16 rounded-2xl object-cover" />
            ) : (
              <div className="w-16 h-16 rounded-2xl bg-primary/15 flex items-center justify-center text-primary text-xl font-bold">
                {(editing ? editForm.first_name : pilot.first_name)?.[0]}{(editing ? editForm.last_name : pilot.last_name)?.[0]}
              </div>
            )}
            {isAdmin && !editing && (
              <label className="absolute -bottom-1 -right-1 w-6 h-6 bg-primary text-primary-foreground rounded-full flex items-center justify-center cursor-pointer hover:opacity-90 shadow-sm">
                <Camera className="w-3 h-3" />
                <input type="file" accept="image/*" className="hidden" onChange={async (e) => {
                  const file = e.target.files[0]
                  if (!file) return
                  const formData = new FormData()
                  formData.append('file', file)
                  try {
                    const result = await api.upload(`/pilots/${id}/photo`, formData)
                    setPilot({ ...pilot, photo_url: result.photo_url + '?t=' + Date.now() })
                  } catch (err) { toast.error(err.message) }
                  e.target.value = ''
                }} />
              </label>
            )}
          </div>
          <div className="flex-1">
            {editing ? (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label htmlFor="first-name" className="block text-xs font-medium text-muted-foreground mb-1">First Name</label>
                    <input id="first-name" type="text" value={editForm.first_name} onChange={e => setEditForm({...editForm, first_name: e.target.value})}
                      className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                  </div>
                  <div>
                    <label htmlFor="last-name" className="block text-xs font-medium text-muted-foreground mb-1">Last Name</label>
                    <input id="last-name" type="text" value={editForm.last_name} onChange={e => setEditForm({...editForm, last_name: e.target.value})}
                      className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label htmlFor="email" className="block text-xs font-medium text-muted-foreground mb-1">Email</label>
                    <input id="email" type="email" value={editForm.email} onChange={e => setEditForm({...editForm, email: e.target.value})}
                      className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                  </div>
                  <div>
                    <label htmlFor="personal-cell" className="block text-xs font-medium text-muted-foreground mb-1">Personal Cell</label>
                    <input id="personal-cell"
                      type="tel"
                      value={editForm.phone || ''}
                      onChange={(e) => {
                        const digits = e.target.value.replace(/\D/g, '').slice(0, 10)
                        let formatted = digits
                        if (digits.length > 3) formatted = digits.slice(0,3) + '-' + digits.slice(3)
                        if (digits.length > 6) formatted = digits.slice(0,3) + '-' + digits.slice(3,6) + '-' + digits.slice(6)
                        setEditForm({...editForm, phone: formatted})
                      }}
                      placeholder="###-###-####"
                      className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                    />
                  </div>
                </div>
                <div>
                  <label htmlFor="work-cell" className="block text-xs font-medium text-muted-foreground mb-1">Work Cell</label>
                  <input id="work-cell"
                    type="tel"
                    value={editForm.phone_work || ''}
                    onChange={(e) => {
                      const digits = e.target.value.replace(/\D/g, '').slice(0, 10)
                      let formatted = digits
                      if (digits.length > 3) formatted = digits.slice(0,3) + '-' + digits.slice(3)
                      if (digits.length > 6) formatted = digits.slice(0,3) + '-' + digits.slice(3,6) + '-' + digits.slice(6)
                      setEditForm({...editForm, phone_work: formatted})
                    }}
                    placeholder="###-###-####"
                    className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label htmlFor="badge-number" className="block text-xs font-medium text-muted-foreground mb-1">Badge Number</label>
                    <input id="badge-number" type="text" value={editForm.badge_number} onChange={e => setEditForm({...editForm, badge_number: e.target.value})}
                      className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                  </div>
                  <div>
                    <label htmlFor="status" className="block text-xs font-medium text-muted-foreground mb-1">Status</label>
                    <select id="status" value={editForm.status} onChange={e => setEditForm({...editForm, status: e.target.value})}
                      className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm">
                      <option value="active">Active</option>
                      <option value="inactive">Inactive</option>
                    </select>
                  </div>
                </div>
                <div>
                  <label htmlFor="notes" className="block text-xs font-medium text-muted-foreground mb-1">Notes</label>
                  <textarea id="notes" value={editForm.notes} onChange={e => setEditForm({...editForm, notes: e.target.value})}
                    className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm h-20 resize-none focus:outline-none focus:ring-2 focus:ring-ring" />
                </div>
                <div className="flex gap-2">
                  <button onClick={handleSave} disabled={saving}
                    className="flex items-center gap-1.5 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50">
                    <Save className="w-4 h-4" /> {saving ? 'Saving...' : 'Save'}
                  </button>
                  <button onClick={cancelEditing}
                    className="flex items-center gap-1.5 px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90">
                    <X className="w-4 h-4" /> Cancel
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div className="flex items-center gap-3">
                  <h2 className="text-xl font-bold text-foreground">{pilot.full_name}</h2>
                  {(isSupervisor || (isPilot && user?.pilot_id === Number.parseInt(id, 10))) && (
                    <button onClick={startEditing}
                      className="p-1.5 text-muted-foreground hover:text-foreground rounded-lg hover:bg-accent transition-colors">
                      <Edit className="w-4 h-4" />
                    </button>
                  )}
                </div>
                <div className="flex flex-wrap gap-4 mt-2 text-sm text-muted-foreground">
                  {pilot.email && <span>{pilot.email}</span>}
                  {pilot.phone && (
                    <div>
                      <p className="text-xs text-muted-foreground">Personal Cell</p>
                      <p className="text-foreground">{pilot.phone}</p>
                    </div>
                  )}
                  {pilot.phone_work && (
                    <div>
                      <p className="text-xs text-muted-foreground">Work Cell</p>
                      <p className="text-foreground">{pilot.phone_work}</p>
                    </div>
                  )}
                  {pilot.badge_number && <span>Badge: {pilot.badge_number}</span>}
                </div>
                <span className={`inline-flex mt-2 px-2 py-0.5 rounded-full text-xs font-medium ${
                  pilot.status === 'active' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-red-500/15 text-red-400'
                }`}>
                  {pilot.status}
                </span>
                {pilot.notes && (
                  <p className="mt-2 text-sm text-muted-foreground">{pilot.notes}</p>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary/15 flex items-center justify-center text-primary"><QuadcopterIcon className="w-5 h-5" /></div>
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

      {/* Performance Analytics */}
      {performance && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-primary/15 flex items-center justify-center text-primary"><QuadcopterIcon className="w-5 h-5" /></div>
              <div><p className="text-2xl font-bold text-foreground">{performance.total_flights}</p><p className="text-xs text-muted-foreground">Total Flights</p></div>
            </div>
            <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-blue-500/15 flex items-center justify-center text-blue-400"><Clock className="w-5 h-5" /></div>
              <div><p className="text-2xl font-bold text-foreground">{performance.total_flight_hours}h</p><p className="text-xs text-muted-foreground">Flight Hours</p></div>
            </div>
            <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-emerald-500/15 flex items-center justify-center text-emerald-400"><TrendingUp className="w-5 h-5" /></div>
              <div><p className="text-2xl font-bold text-foreground">{performance.avg_duration_min}m</p><p className="text-xs text-muted-foreground">Avg Duration</p></div>
            </div>
            <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-violet-500/15 flex items-center justify-center text-violet-400"><GraduationCap className="w-5 h-5" /></div>
              <div><p className="text-2xl font-bold text-foreground">{performance.training_hours}h</p><p className="text-xs text-muted-foreground">Training Hours</p></div>
            </div>
            <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-amber-500/15 flex items-center justify-center text-amber-400"><Target className="w-5 h-5" /></div>
              <div><p className="text-2xl font-bold text-foreground">{performance.mission_hours}h</p><p className="text-xs text-muted-foreground">Mission Hours</p></div>
            </div>
            <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-red-500/15 flex items-center justify-center text-red-400"><AlertTriangle className="w-5 h-5" /></div>
              <div><p className="text-2xl font-bold text-foreground">{performance.incidents}</p><p className="text-xs text-muted-foreground">Incidents</p></div>
            </div>
          </div>

          {/* Charts Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Flights by Month Bar Chart */}
            {performance.flights_by_month.length > 0 && (
              <div className="bg-card border border-border rounded-xl p-5">
                <h3 className="text-sm font-semibold text-foreground mb-4">Flights by Month</h3>
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={performance.flights_by_month}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                    <XAxis dataKey="month" tick={{ fill: 'var(--muted-fg)', fontSize: 11 }} />
                    <YAxis tick={{ fill: 'var(--muted-fg)', fontSize: 11 }} allowDecimals={false} />
                    <Tooltip
                      contentStyle={{ background: 'var(--card)', border: '1px solid var(--border-color)', borderRadius: '8px', color: 'var(--fg)' }}
                      labelStyle={{ color: 'var(--fg)' }}
                    />
                    <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} name="Flights" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* Flights by Purpose Pie Chart */}
            {performance.flights_by_purpose.length > 0 && (
              <div className="bg-card border border-border rounded-xl p-5">
                <h3 className="text-sm font-semibold text-foreground mb-4">Flights by Purpose</h3>
                <ResponsiveContainer width="100%" height={250}>
                  <PieChart>
                    <Pie
                      data={performance.flights_by_purpose}
                      dataKey="count"
                      nameKey="purpose"
                      cx="50%"
                      cy="50%"
                      outerRadius={90}
                      label={({ purpose, count }) => `${purpose} (${count})`}
                    >
                      {performance.flights_by_purpose.map((entry, i) => (
                        <Cell key={entry.purpose || `purpose-${i}`} fill={['#6366f1','#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6','#ec4899','#14b8a6','#f97316','#06b6d4'][i % 10]} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{ background: 'var(--card)', border: '1px solid var(--border-color)', borderRadius: '8px', color: 'var(--fg)' }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        </>
      )}

      {/* Recent Flights */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-border"><h3 className="font-semibold text-foreground">Recent Flights</h3></div>
        <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/30">
              <th className="text-left px-4 py-2 text-foreground font-medium">Date</th>
              <th className="text-left px-4 py-2 text-foreground font-medium">Vehicle</th>
              <th className="text-left px-4 py-2 text-foreground font-medium hidden md:table-cell">Purpose</th>
              <th className="text-left px-4 py-2 text-foreground font-medium">Duration</th>
              <th className="text-left px-4 py-2 text-foreground font-medium hidden md:table-cell">Location</th>
            </tr>
          </thead>
          <tbody>
            {flights.map(f => (
              <tr key={f.id} className="border-b border-border/50 hover:bg-accent/30">
                <td className="px-4 py-2 text-foreground"><Link to={`/flights/${f.id}`} className="text-primary hover:underline">{f.date || '—'}</Link></td>
                <td className="px-4 py-2 text-foreground">{f.vehicle_id ? <Link to={`/fleet/vehicles/${f.vehicle_id}`} className="text-primary hover:underline">{f.vehicle_name || '—'}</Link> : (f.vehicle_name || '—')}</td>
                <td className="px-4 py-2 text-foreground hidden md:table-cell">{f.purpose ? <Link to={`/flights?purpose=${encodeURIComponent(f.purpose)}`} className="text-primary hover:underline">{f.purpose}</Link> : '—'}</td>
                <td className="px-4 py-2 text-foreground">{formatDuration(f.duration_seconds)}</td>
                <td className="px-4 py-2 text-foreground truncate max-w-[200px] hidden md:table-cell">{f.takeoff_address || '—'}</td>
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
              <th className="text-left px-4 py-2 text-foreground font-medium">Certification</th>
              <th className="text-left px-4 py-2 text-foreground font-medium">Status</th>
              <th className="text-left px-4 py-2 text-foreground font-medium hidden md:table-cell">Issue Date</th>
              <th className="text-left px-4 py-2 text-foreground font-medium">Expiration</th>
              <th className="text-left px-4 py-2 text-foreground font-medium hidden md:table-cell">Certificate #</th>
            </tr>
          </thead>
          <tbody>
            {certifications.map(c => (
              <tr key={c.id} className="border-b border-border/50 hover:bg-accent/30">
                <td className="px-4 py-2 text-foreground font-medium">{c.cert_type_name}</td>
                <td className="px-4 py-2">
                  <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${CERT_STATUS_COLORS[c.status] || CERT_STATUS_COLORS.not_started}`}>
                    {(c.status || 'not_started').replaceAll('_', ' ')}
                  </span>
                </td>
                <td className="px-4 py-2 text-foreground hidden md:table-cell">{c.issue_date || '—'}</td>
                <td className="px-4 py-2 text-foreground">{c.expiration_date || '—'}</td>
                <td className="px-4 py-2 text-foreground hidden md:table-cell">{c.certificate_number || '—'}</td>
              </tr>
            ))}
            {certifications.length === 0 && <tr><td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">No certifications assigned</td></tr>}
          </tbody>
        </table>
        </div>
      </div>

      {/* Currency Status */}
      {currencyStatus && currencyStatus.rules && currencyStatus.rules.length > 0 && (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-border flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-primary" />
              <h3 className="font-semibold text-foreground">Currency Status</h3>
            </div>
            <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
              currencyStatus.is_current
                ? 'bg-emerald-500/15 text-emerald-400'
                : 'bg-red-500/15 text-red-400'
            }`}>
              {currencyStatus.is_current ? (
                <><CheckCircle className="w-3.5 h-3.5" /> Current</>
              ) : (
                <><XCircle className="w-3.5 h-3.5" /> Lapsed</>
              )}
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/30">
                  <th className="text-left px-4 py-2 text-foreground font-medium">Rule</th>
                  <th className="text-left px-4 py-2 text-foreground font-medium hidden md:table-cell">Model</th>
                  <th className="text-left px-4 py-2 text-foreground font-medium">Hours</th>
                  <th className="text-left px-4 py-2 text-foreground font-medium">Flights</th>
                  <th className="text-left px-4 py-2 text-foreground font-medium">Status</th>
                  <th className="text-left px-4 py-2 text-foreground font-medium hidden md:table-cell">Expires</th>
                </tr>
              </thead>
              <tbody>
                {currencyStatus.rules.map(r => (
                  <tr key={r.rule_id} className="border-b border-border/50 hover:bg-accent/30">
                    <td className="px-4 py-2 text-foreground font-medium">{r.rule_name}</td>
                    <td className="px-4 py-2 text-foreground hidden md:table-cell">{r.vehicle_model || 'All'}</td>
                    <td className="px-4 py-2 text-foreground">
                      <span className={r.actual_hours >= r.required_hours ? 'text-emerald-400' : 'text-red-400'}>
                        {r.actual_hours}
                      </span>
                      <span className="text-muted-foreground"> / {r.required_hours}h</span>
                      <span className="text-xs text-muted-foreground ml-1">({r.period_days}d)</span>
                    </td>
                    <td className="px-4 py-2 text-foreground">
                      {r.required_flights != null ? (
                        <>
                          <span className={r.actual_flights >= r.required_flights ? 'text-emerald-400' : 'text-red-400'}>
                            {r.actual_flights}
                          </span>
                          <span className="text-muted-foreground"> / {r.required_flights}</span>
                        </>
                      ) : '—'}
                    </td>
                    <td className="px-4 py-2">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
                        r.is_current ? 'bg-emerald-500/15 text-emerald-400' : 'bg-red-500/15 text-red-400'
                      }`}>
                        {r.is_current ? <CheckCircle className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                        {r.is_current ? 'Current' : 'Lapsed'}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-foreground hidden md:table-cell">{r.expires_date || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Documents */}
      <DocumentUpload entityType="pilot" entityId={id} folderId={generalFolderId} />
    </div>
  )
}
