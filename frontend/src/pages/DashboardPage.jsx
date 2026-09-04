/**
 * Bento-style dashboard hub. Tiles of intentionally varying sizes arranged
 * on a 12-column grid, surfacing the most operationally relevant signals up
 * front: compliance score, currency risk, recent flights, trend deltas,
 * activity tempo, top performers.
 */
import { useState, useEffect, useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { formatHours } from '@/lib/utils'
import { resolveOrgLocation } from '@/lib/location'
import {
  Clock, Users, Box, AlertTriangle, ClipboardCheck, ArrowRight, Wrench, ShieldCheck,
  CloudSun, TrendingUp, TrendingDown, Minus, Target, GraduationCap, ChevronRight,
} from 'lucide-react'
import { QuadcopterIcon } from '@/components/icons/QuadcopterIcon'
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip as RTooltip } from 'recharts'

/* ───────────────────── helpers ───────────────────── */

function getDaysRemaining(dateStr) {
  if (!dateStr) return null
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const target = new Date(dateStr); target.setHours(0, 0, 0, 0)
  return Math.ceil((target - today) / (1000 * 60 * 60 * 24))
}

function formatDelta(pct) {
  if (pct == null) return null
  if (Math.abs(pct) < 0.1) return { text: 'flat', sign: 0 }
  return { text: `${pct > 0 ? '+' : ''}${pct}%`, sign: pct > 0 ? 1 : -1 }
}

function DeltaArrow({ pct }) {
  const d = formatDelta(pct)
  if (!d) return null
  if (d.sign === 0) return <span className="inline-flex items-center text-xs text-muted-foreground"><Minus className="w-3 h-3 mr-0.5" />{d.text}</span>
  if (d.sign > 0) return <span className="inline-flex items-center text-xs text-emerald-400"><TrendingUp className="w-3 h-3 mr-0.5" />{d.text}</span>
  return <span className="inline-flex items-center text-xs text-amber-400"><TrendingDown className="w-3 h-3 mr-0.5" />{d.text}</span>
}

function getScoreTheme(score) {
  if (score == null) return { color: 'text-muted-foreground', bg: 'bg-card' }
  if (score >= 80) return { color: 'text-emerald-400', bg: 'bg-emerald-500/10', border: 'border-emerald-500/30' }
  if (score >= 60) return { color: 'text-amber-400', bg: 'bg-amber-500/10', border: 'border-amber-500/30' }
  return { color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/30' }
}

/* ───────────────────── tile components ───────────────────── */

function Tile({ className = '', children }) {
  return (
    <div className={`bg-card border border-border rounded-xl ${className}`}>
      {children}
    </div>
  )
}

/** Operating-authority clause for the hero line, once the unit tracks any. */
function authoritySummary(compliance) {
  const expired = compliance.expired_authorities?.length || 0
  if (expired > 0) return ` · ${expired} expired authorit${expired === 1 ? 'y' : 'ies'}`
  const expiring = compliance.expiring_authorities?.length || 0
  if (expiring > 0) return ` · ${expiring} authorit${expiring === 1 ? 'y' : 'ies'} expiring`
  return ' · authority current'
}

function HeroTile({ user, compliance }) {
  const theme = getScoreTheme(compliance?.compliance_score)
  const greeting = (() => {
    const h = new Date().getHours()
    if (h < 12) return 'Good morning'
    if (h < 17) return 'Good afternoon'
    return 'Good evening'
  })()
  return (
    <Tile className="lg:col-span-8 p-5 flex flex-col sm:flex-row gap-5 items-center">
      <div className={`relative w-24 h-24 sm:w-28 sm:h-28 rounded-2xl flex items-center justify-center border-2 ${theme.bg} ${theme.border || 'border-border'} shrink-0`}>
        <div className="text-center">
          <div className={`text-3xl font-bold ${theme.color}`}>{compliance?.compliance_score ?? '—'}</div>
          <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Compliance</div>
        </div>
      </div>
      <div className="flex-1 min-w-0">
        <h2 className="text-xl font-semibold text-foreground">
          {greeting}{user?.display_name ? `, ${user.display_name}` : ''}
        </h2>
        <p className="text-sm text-muted-foreground mt-1">
          {compliance ? (
            <>
              {compliance.pilots_current} of {compliance.total_pilots} pilots current
              {compliance.currency_rules_active === 0 ? ' (no currency rules)' : ''}
              {' · '}
              {compliance.expired_certifications > 0
                ? `${compliance.expired_certifications} expired cert${compliance.expired_certifications === 1 ? '' : 's'}`
                : 'all certs current'}
              {compliance.overdue_maintenance > 0 ? ` · ${compliance.overdue_maintenance} overdue maint` : ''}
              {compliance.operating_authorities_tracked > 0 && authoritySummary(compliance)}
            </>
          ) : 'Loading…'}
        </p>
        {compliance?.score_cap_reason && (
          <p className="text-xs text-red-400 mt-1">{compliance.score_cap_reason}</p>
        )}
        <Link to="/compliance" className="inline-flex items-center gap-1 text-xs text-primary hover:underline mt-2">
          Open compliance dashboard <ArrowRight className="w-3 h-3" />
        </Link>
      </div>
    </Tile>
  )
}

function WeatherTile({ weather }) {
  if (!weather) {
    return (
      <Tile className="lg:col-span-4 p-5 flex flex-col items-center justify-center text-center min-h-[140px]">
        <CloudSun className="w-8 h-8 text-muted-foreground/50 mb-2" />
        <p className="text-sm text-muted-foreground">Weather widget unavailable</p>
        <Link to="/settings" className="text-xs text-primary hover:underline mt-1">Set location in Settings</Link>
      </Tile>
    )
  }
  const advisory = weather.advisory || {}
  const advClass =
    advisory.status === 'GO' ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' :
    advisory.status === 'NO-GO' ? 'bg-red-500/15 text-red-400 border-red-500/30' :
    'bg-amber-500/15 text-amber-400 border-amber-500/30'
  return (
    <Tile className="lg:col-span-4 p-5 flex flex-col gap-2">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-1.5"><CloudSun className="w-4 h-4 text-primary" /> Weather</h3>
          <p className="text-xs text-muted-foreground truncate">{weather.station?.name || 'Local'}</p>
        </div>
        {advisory.status && (
          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${advClass}`}>
            {advisory.status}
          </span>
        )}
      </div>
      <div className="grid grid-cols-3 gap-2 mt-1">
        <div className="text-center">
          <p className="text-xs text-muted-foreground">Wind</p>
          <p className="text-sm font-medium text-foreground">{weather.wind_kts != null ? `${weather.wind_kts}kt` : '—'}</p>
        </div>
        <div className="text-center">
          <p className="text-xs text-muted-foreground">Vis</p>
          <p className="text-sm font-medium text-foreground">{weather.visibility_sm != null ? `${weather.visibility_sm}sm` : '—'}</p>
        </div>
        <div className="text-center">
          <p className="text-xs text-muted-foreground">Ceil</p>
          <p className="text-sm font-medium text-foreground">{weather.ceiling_ft != null ? `${weather.ceiling_ft}ft` : '—'}</p>
        </div>
      </div>
      <Link to="/weather" className="inline-flex items-center gap-1 text-xs text-primary hover:underline self-end">
        Full briefing <ArrowRight className="w-3 h-3" />
      </Link>
    </Tile>
  )
}

function StatTile({ label, value, subtitle, deltaPct, icon: Icon, to }) {
  const card = (
    <Tile className="lg:col-span-3 p-4 hover:border-primary/50 transition-colors h-full">
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-xs text-muted-foreground uppercase tracking-wider">{label}</p>
          <p className="text-2xl font-semibold text-foreground mt-1">{value}</p>
          {(subtitle || deltaPct !== undefined) && (
            <div className="flex items-center gap-2 mt-1">
              {deltaPct !== undefined && <DeltaArrow pct={deltaPct} />}
              {subtitle && <span className="text-xs text-muted-foreground">{subtitle}</span>}
            </div>
          )}
        </div>
        <div className="w-9 h-9 rounded-xl bg-primary/10 text-primary flex items-center justify-center shrink-0">
          <Icon className="w-4 h-4" />
        </div>
      </div>
    </Tile>
  )
  return to ? <Link to={to} className="lg:col-span-3 block">{card}</Link> : card
}

function RecentFlightsTile({ flights }) {
  return (
    <Tile className="lg:col-span-6 lg:row-span-2 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <h3 className="text-sm font-semibold text-foreground flex items-center gap-1.5"><QuadcopterIcon className="w-4 h-4 text-primary" /> Recent Flights</h3>
        <Link to="/flights" className="text-xs text-primary hover:underline flex items-center gap-1">All <ArrowRight className="w-3 h-3" /></Link>
      </div>
      {flights.length === 0 ? (
        <div className="p-6 text-center text-sm text-muted-foreground">No recent flights</div>
      ) : (
        <ul className="divide-y divide-border">
          {flights.slice(0, 10).map(f => (
            <li key={f.id}>
              <Link to={`/flights/${f.id}`} className="flex items-center gap-3 px-4 py-2.5 hover:bg-secondary/50 transition-colors">
                <span className="text-xs font-mono text-primary w-16 truncate">
                  {f.external_id ? f.external_id.slice(0, 8) : `#${f.id}`}
                </span>
                <span className="text-xs text-foreground w-24 truncate">{f.pilot_name || 'Unassigned'}</span>
                <span className="text-xs text-muted-foreground hidden sm:inline w-28 truncate">{f.vehicle_name || '—'}</span>
                <span className="text-xs text-muted-foreground flex-1 truncate hidden md:inline">{f.purpose || '—'}</span>
                <span className="text-xs text-foreground">{f.duration_seconds ? `${Math.round(f.duration_seconds / 60)}m` : '—'}</span>
                <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Tile>
  )
}

function CurrencyRiskTile({ compliance }) {
  const lapsedAndSoon = useMemo(() => {
    if (!compliance?.pilot_currency_status) return []
    return compliance.pilot_currency_status
      .map(p => ({ ...p, daysUntilExpiry: getDaysRemaining(p.earliest_expires_date) }))
      .filter(p => !p.is_current || (p.daysUntilExpiry != null && p.daysUntilExpiry <= 30))
      .sort((a, b) => {
        if (a.is_current !== b.is_current) return a.is_current ? 1 : -1
        return (a.daysUntilExpiry ?? 9999) - (b.daysUntilExpiry ?? 9999)
      })
      .slice(0, 5)
  }, [compliance])

  return (
    <Tile className="lg:col-span-3 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <h3 className="text-sm font-semibold text-foreground flex items-center gap-1.5"><Users className="w-4 h-4 text-primary" /> Currency Risk</h3>
        {compliance && (
          <span className="text-xs text-muted-foreground">{compliance.pilots_lapsed || 0} lapsed</span>
        )}
      </div>
      {compliance?.currency_rules_active === 0 ? (
        <div className="p-4 text-center text-xs text-muted-foreground">
          No rules defined.{' '}
          <Link to="/settings" className="text-primary hover:underline">Set up rules</Link>
        </div>
      ) : lapsedAndSoon.length === 0 ? (
        <div className="p-4 text-center text-xs text-emerald-400">All pilots current</div>
      ) : (
        <ul className="divide-y divide-border">
          {lapsedAndSoon.map(p => (
            <li key={p.pilot_id}>
              <Link to={`/pilots/${p.pilot_id}`} className="flex items-center gap-2 px-4 py-2 hover:bg-secondary/50 transition-colors">
                <span className={`inline-flex w-14 justify-center px-1.5 py-0.5 rounded-full text-[10px] font-medium border ${
                  !p.is_current ? 'bg-red-500/15 text-red-400 border-red-500/30' :
                  p.daysUntilExpiry <= 14 ? 'bg-amber-500/15 text-amber-400 border-amber-500/30' :
                  'bg-blue-500/15 text-blue-400 border-blue-500/30'
                }`}>
                  {!p.is_current ? 'LAPSED' : `${p.daysUntilExpiry}d`}
                </span>
                <span className="text-xs text-foreground truncate flex-1">{p.pilot_name}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Tile>
  )
}

function ListTile({ title, icon: Icon, items, emptyLabel, renderItem, link, linkLabel = 'View all', colSpan = 'lg:col-span-3' }) {
  return (
    <Tile className={`${colSpan} overflow-hidden`}>
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <h3 className="text-sm font-semibold text-foreground flex items-center gap-1.5"><Icon className="w-4 h-4 text-primary" /> {title}</h3>
        {link && (
          <Link to={link} className="text-xs text-primary hover:underline flex items-center gap-1">{linkLabel} <ArrowRight className="w-3 h-3" /></Link>
        )}
      </div>
      {items.length === 0 ? (
        <div className="p-4 text-center text-xs text-muted-foreground">{emptyLabel}</div>
      ) : (
        <ul className="divide-y divide-border">
          {items.map(renderItem)}
        </ul>
      )}
    </Tile>
  )
}

function LocationsTile({ items, pilots, places, onChange, colSpan = 'lg:col-span-4' }) {
  return (
    <Tile className={`${colSpan} overflow-hidden`}>
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <h3 className="text-sm font-semibold text-foreground flex items-center gap-1.5"><Box className="w-4 h-4 text-primary" /> Locations</h3>
      </div>
      {items.length === 0 ? (
        <div className="p-4 text-center text-xs text-muted-foreground">No drones</div>
      ) : (
        <ul className="divide-y divide-border">
          {items.map(it => (
            <li key={it.vehicle_id} className="flex items-center justify-between gap-3 px-4 py-2.5">
              <div className="min-w-0">
                <p className="text-sm text-foreground truncate">{it.label}</p>
                <p className="text-xs text-muted-foreground truncate">{it.location_text}</p>
              </div>
              <select
                className="h-8 rounded-md border border-border bg-secondary px-2 text-xs text-foreground max-w-[10rem]"
                value=""
                onChange={(e) => { if (e.target.value) onChange(it.vehicle_id, e.target.value) }}
              >
                <option value="">Set location…</option>
                <optgroup label="Places">
                  {places.map(pl => <option key={`place:${pl}`} value={`place:${pl}`}>{pl}</option>)}
                </optgroup>
                <optgroup label="Pilots">
                  {pilots.map(p => <option key={`pilot:${p.id}`} value={`pilot:${p.id}`}>{p.first_name} {p.last_name}</option>)}
                </optgroup>
              </select>
            </li>
          ))}
        </ul>
      )}
    </Tile>
  )
}

function ActivityChartTile({ data }) {
  const display = useMemo(() => data.slice(-12).map(d => ({
    label: d.label.slice(2),  // "26-05" instead of "2026-05"
    flights: d.flights,
    hours: d.hours,
  })), [data])
  return (
    <Tile className="lg:col-span-6 p-4 overflow-hidden">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-foreground flex items-center gap-1.5"><TrendingUp className="w-4 h-4 text-primary" /> Activity by Month</h3>
        <Link to="/analytics" className="text-xs text-primary hover:underline flex items-center gap-1">Analytics <ArrowRight className="w-3 h-3" /></Link>
      </div>
      <div className="h-44">
        {display.length === 0 ? (
          <div className="flex items-center justify-center h-full text-xs text-muted-foreground">No flights yet</div>
        ) : (
          <ResponsiveContainer>
            <BarChart data={display}>
              <XAxis dataKey="label" tick={{ fontSize: 10, fill: 'var(--muted-fg)' }} stroke="var(--border-color)" axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: 'var(--muted-fg)' }} stroke="var(--border-color)" axisLine={false} tickLine={false} width={28} />
              <RTooltip
                cursor={{ fill: 'rgba(255,255,255,0.03)' }}
                contentStyle={{ background: 'var(--card)', border: '1px solid var(--border-color)', borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: 'var(--fg)' }}
              />
              <Bar dataKey="flights" radius={[4, 4, 0, 0]} fill="#3b82f6" />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </Tile>
  )
}

/* ───────────────────── page ───────────────────── */

export default function DashboardPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [stats, setStats] = useState(null)
  const [trends, setTrends] = useState(null)
  const [recentFlights, setRecentFlights] = useState([])
  const [upcomingMaintenance, setUpcomingMaintenance] = useState([])
  const [compliance, setCompliance] = useState(null)
  const [topPilots, setTopPilots] = useState([])
  const [topVehicles, setTopVehicles] = useState([])
  const [activity, setActivity] = useState([])
  const [weather, setWeather] = useState(null)
  const [locations, setLocations] = useState([])
  const [pilots, setPilots] = useState([])
  const [locationPlaces, setLocationPlaces] = useState(['North', 'Central', 'South'])
  const [loading, setLoading] = useState(true)
  const toast = useToast()

  useEffect(() => {
    let alive = true
    Promise.all([
      api.get('/dashboard/stats').catch(() => null),
      api.get('/dashboard/trends').catch(() => null),
      api.get('/flights?per_page=10').catch(() => []),
      api.get('/maintenance?upcoming=true').catch(() => []),
      api.get('/dashboard/compliance').catch(() => null),
      api.get('/dashboard/top-pilots-30d').catch(() => []),
      api.get('/dashboard/top-vehicles-30d').catch(() => []),
      api.get('/dashboard/activity-by-month').catch(() => []),
      api.get('/vehicles/locations').catch(() => []),
      api.get('/pilots').catch(() => []),
      api.get('/settings').catch(() => []),
    ]).then(async ([s, t, f, m, c, tp, tv, ac, locs, pilotList, settingsList]) => {
      if (!alive) return
      setStats(s)
      setTrends(t)
      const flights = Array.isArray(f) ? f : (f?.items || f?.flights || [])
      setRecentFlights(flights)
      const maint = Array.isArray(m) ? m : (m?.items || m?.maintenance || [])
      setUpcomingMaintenance(maint)
      setCompliance(c)
      setTopPilots(Array.isArray(tp) ? tp : [])
      setTopVehicles(Array.isArray(tv) ? tv : [])
      setActivity(Array.isArray(ac) ? ac : [])
      setLocations(Array.isArray(locs) ? locs : [])
      setPilots(Array.isArray(pilotList) ? pilotList.filter(p => p.status === 'active') : [])
      const placesRow = Array.isArray(settingsList) ? settingsList.find(s => s.key === 'drone_location_places') : null
      let places = ['North', 'Central', 'South']
      if (placesRow?.value) { try { const j = JSON.parse(placesRow.value); if (Array.isArray(j) && j.length) places = j } catch { /* keep default */ } }
      setLocationPlaces(places)
      // Weather tile: /weather/briefing requires lat/lon, so resolve the org
      // default (or White House) from settings before building the URL.
      const { lat, lon } = resolveOrgLocation(settingsList)
      const w = await api.get(`/weather/briefing?lat=${lat}&lon=${lon}`).catch(() => null)
      if (alive) setWeather(w)
    }).finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  const expiringCerts = (compliance?.expiring_certifications || []).slice(0, 5)

  const handleSetLocation = async (vehicleId, encoded) => {
    const idx = encoded.indexOf(':')
    const type = encoded.slice(0, idx)
    const val = encoded.slice(idx + 1)
    const body = type === 'pilot' ? { pilot_id: Number(val) } : { place: val }
    try {
      await api.patch(`/vehicles/${vehicleId}/location`, body)
      const locs = await api.get('/vehicles/locations').catch(() => locations)
      setLocations(Array.isArray(locs) ? locs : [])
    } catch (err) { toast.error(err.message) }
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-12 gap-4 auto-rows-min">
      {/* Row 1: Hero + Weather */}
      <HeroTile user={user} compliance={compliance} />
      <WeatherTile weather={weather} />

      {/* Row 2: 4 trend stats */}
      <StatTile
        label="Flights (30d)"
        value={trends?.current?.flights ?? stats?.total_flights ?? 0}
        deltaPct={trends?.deltas_pct?.flights}
        subtitle={`${stats?.total_flights ?? 0} total`}
        icon={QuadcopterIcon}
        to="/flights"
      />
      <StatTile
        label="Hours (30d)"
        value={trends?.current?.hours ?? formatHours((stats?.total_flight_hours ?? 0) * 3600)}
        deltaPct={trends?.deltas_pct?.hours}
        subtitle={`${formatHours((stats?.total_flight_hours ?? 0) * 3600)} total`}
        icon={Clock}
        to="/analytics"
      />
      <StatTile
        label="Active Pilots"
        value={stats?.active_pilots ?? 0}
        deltaPct={trends?.deltas_pct?.active_pilots}
        subtitle="flying last 30d"
        icon={Users}
        to="/pilots"
      />
      <StatTile
        label="Fleet Size"
        value={stats?.fleet_size ?? 0}
        deltaPct={trends?.deltas_pct?.active_vehicles}
        subtitle="flying last 30d"
        icon={Box}
        to="/fleet"
      />

      {/* Row 3: Recent flights (tall) + supporting tiles */}
      <RecentFlightsTile flights={recentFlights} />

      <CurrencyRiskTile compliance={compliance} />

      <ListTile
        title="Needs Review"
        icon={ClipboardCheck}
        items={(stats?.flights_needing_review || 0) > 0 ? [{ id: 'review' }] : []}
        emptyLabel="Queue is clear"
        link="/flights?review_status=needs_review"
        linkLabel="Open"
        renderItem={() => (
          <li key="rev" className="px-4 py-3">
            <div className="flex items-center justify-between">
              <span className="text-3xl font-bold text-amber-400">{stats?.flights_needing_review || 0}</span>
              <button onClick={() => navigate('/flights?review_status=needs_review')} className="text-xs text-primary hover:underline">Review →</button>
            </div>
            <p className="text-xs text-muted-foreground mt-1">flights awaiting supervisor review</p>
          </li>
        )}
      />

      <ListTile
        title="Maintenance Due"
        icon={Wrench}
        items={upcomingMaintenance.slice(0, 3)}
        emptyLabel="No maintenance due"
        link="/maintenance"
        renderItem={(m) => {
          const days = getDaysRemaining(m.next_due)
          const overdue = days != null && days < 0
          return (
            <li key={m.id}>
              <Link to="/maintenance" className="flex items-center gap-2 px-4 py-2 hover:bg-secondary/50 transition-colors">
                <span className={`inline-flex w-14 justify-center px-1.5 py-0.5 rounded-full text-[10px] font-medium border ${
                  overdue ? 'bg-red-500/15 text-red-400 border-red-500/30' :
                  (days != null && days <= 7) ? 'bg-amber-500/15 text-amber-400 border-amber-500/30' :
                  'bg-blue-500/15 text-blue-400 border-blue-500/30'
                }`}>
                  {days == null ? '—' : overdue ? `${Math.abs(days)}d -` : `${days}d`}
                </span>
                <span className="text-xs text-foreground truncate flex-1">{m.description || m.maintenance_type || 'Maintenance'}</span>
              </Link>
            </li>
          )
        }}
      />

      <ListTile
        title="Cert Expirations"
        icon={AlertTriangle}
        items={expiringCerts}
        emptyLabel="None expiring soon"
        link="/certifications"
        renderItem={(c, idx) => {
          const days = c.days_remaining
          return (
            <li key={`${c.pilot_id}-${idx}`}>
              <Link to="/certifications" className="flex items-center gap-2 px-4 py-2 hover:bg-secondary/50 transition-colors">
                <span className={`inline-flex w-14 justify-center px-1.5 py-0.5 rounded-full text-[10px] font-medium border ${
                  days < 0 ? 'bg-red-500/15 text-red-400 border-red-500/30' :
                  days <= 30 ? 'bg-amber-500/15 text-amber-400 border-amber-500/30' :
                  'bg-blue-500/15 text-blue-400 border-blue-500/30'
                }`}>
                  {days < 0 ? `${Math.abs(days)}d -` : `${days}d`}
                </span>
                <span className="text-xs text-foreground truncate flex-1">Pilot #{c.pilot_id}</span>
              </Link>
            </li>
          )
        }}
      />

      {/* Row 4: Activity chart + leaderboards */}
      <ActivityChartTile data={activity} />

      <ListTile
        title="Top Pilots (30d)"
        icon={GraduationCap}
        items={topPilots}
        emptyLabel="No flight activity"
        link="/pilots"
        renderItem={(p, i) => (
          <li key={p.pilot_id}>
            <Link to={`/pilots/${p.pilot_id}`} className="flex items-center gap-2 px-4 py-2 hover:bg-secondary/50 transition-colors">
              <span className="text-xs text-muted-foreground w-5">{i + 1}</span>
              <span className="text-xs text-foreground truncate flex-1">{p.pilot_name || `Pilot #${p.pilot_id}`}</span>
              <span className="text-xs text-primary font-medium">{p.hours}h</span>
            </Link>
          </li>
        )}
      />

      <ListTile
        title="Top Vehicles (30d)"
        icon={Target}
        items={topVehicles}
        emptyLabel="No flight activity"
        link="/fleet"
        renderItem={(v, i) => (
          <li key={v.vehicle_id}>
            <Link to={`/fleet/vehicles/${v.vehicle_id}`} className="flex items-center gap-2 px-4 py-2 hover:bg-secondary/50 transition-colors">
              <span className="text-xs text-muted-foreground w-5">{i + 1}</span>
              <span className="text-xs text-foreground truncate flex-1">{v.label || `Vehicle #${v.vehicle_id}`}</span>
              <span className="text-xs text-primary font-medium">{v.hours}h</span>
            </Link>
          </li>
        )}
      />

      {/* Drone locations */}
      <LocationsTile items={locations} pilots={pilots} places={locationPlaces} onChange={handleSetLocation} />
    </div>
  )
}
