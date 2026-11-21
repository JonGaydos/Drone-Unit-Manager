/**
 * Bento-style dashboard hub. Tiles of intentionally varying sizes arranged
 * on a 12-column grid, surfacing the most operationally relevant signals up
 * front: compliance score, recent flights, trend deltas,
 * activity tempo, top performers.
 */
import { useState, useEffect, useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, getSection } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { formatHours } from '@/lib/utils'
import {
  Clock, Users, Box, AlertTriangle, ClipboardCheck, ArrowRight, Wrench,
  TrendingUp, TrendingDown, Minus, Target, GraduationCap, ChevronRight,
} from 'lucide-react'
import { QuadcopterIcon } from '@/components/icons/QuadcopterIcon'
import ThisPeriodTile from '@/components/requirements/ThisPeriodTile'
import ArrangeableGrid from '@/components/layout/ArrangeableGrid'
import { usePageLayout } from '@/components/layout/usePageLayout'
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip as RTooltip } from 'recharts'

/* ───────────────────── helpers ───────────────────── */

// Every countdown badge on this page shares one three-tier palette: red once
// the deadline has passed, amber as it approaches, blue otherwise.
const TONE_PAST = 'bg-red-500/15 text-red-400 border-red-500/30'
const TONE_SOON = 'bg-amber-500/15 text-amber-400 border-amber-500/30'
const TONE_OK = 'bg-blue-500/15 text-blue-400 border-blue-500/30'

function countdownTone(past, soon) {
  if (past) return TONE_PAST
  if (soon) return TONE_SOON
  return TONE_OK
}

/** "12d" before the deadline, "3d -" after it, "—" with no date at all. */
function countdownLabel(days) {
  if (days == null) return '—'
  return days < 0 ? `${Math.abs(days)}d -` : `${days}d`
}

/** The same countdown, said in full: "31d overdue" rather than "31d -". */
function dueLabel(days) {
  if (days == null) return '—'
  if (days < 0) return `${Math.abs(days)}d overdue`
  return `${days}d`
}

/** "1 cert", "2 certs". */
function pluralise(count, noun) {
  return `${count} ${noun}${count === 1 ? '' : 's'}`
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
    <Tile className="p-5 flex flex-col sm:flex-row gap-5 items-center">
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
              {pluralise(compliance.total_pilots, 'active pilot')}
              {' · '}
              {compliance.expired_certifications > 0
                ? pluralise(compliance.expired_certifications, 'expired cert')
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

function StatTile({ label, value, subtitle, deltaPct, icon: Icon, to }) {
  const card = (
    <Tile className="p-4 hover:border-primary/50 transition-colors h-full">
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
  return to ? <Link to={to} className="block">{card}</Link> : card
}

function RecentFlightsTile({ flights }) {
  return (
    <Tile className="overflow-hidden">
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

function ListTile({ title, icon: Icon, items, emptyLabel, renderItem, link, linkLabel = 'View all' }) {
  return (
    <Tile className="overflow-hidden">
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

function LocationsTile({ items, pilots, places, onChange, canSetLocation }) {
  return (
    <Tile className="overflow-hidden">
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
              {canSetLocation && (
                <select
                  aria-label={`Set location for ${it.label}`}
                  className="h-8 rounded-md border border-border bg-secondary px-2 text-xs text-foreground max-w-[10rem]"
                  value=""
                  onChange={(e) => { if (e.target.value) onChange(it.vehicle_id, e.target.value) }}
                >
                  <option value="">Set location…</option>
                  <optgroup label="Places">
                    {places.map(pl => <option key={`place:${pl}`} value={`place:${pl}`}>{pl}</option>)}
                  </optgroup>
                  <optgroup label="Pilots">
                    {pilots.map(p => <option key={`pilot:${p.id}`} value={`pilot:${p.id}`}>{p.full_name}</option>)}
                  </optgroup>
                </select>
              )}
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
    <Tile className="p-4 overflow-hidden">
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

/** Coerce a value that should be a list into an array ([] when it isn't one). */
function asArray(x) {
  return Array.isArray(x) ? x : []
}

/** Accept either a bare array or an object wrapping the list under keyA/keyB
 *  (the shapes different endpoints return). Falls back to []. */
function asItemList(x, keyA, keyB) {
  if (Array.isArray(x)) return x
  return x?.[keyA] || x?.[keyB] || []
}

/** Parse the configured drone-location place labels from the settings row,
 *  falling back to the North/Central/South default on missing or bad JSON. */
function parseLocationPlaces(placesRow) {
  const fallback = ['North', 'Central', 'South']
  if (!placesRow?.value) return fallback
  try {
    const j = JSON.parse(placesRow.value)
    if (Array.isArray(j) && j.length) return j
  } catch { /* keep default */ }
  return fallback
}

/* ───────────────────── page ───────────────────── */

export default function DashboardPage() {
  const { user, can } = useAuth()
  const canSeeFlights = can('flights.view')
  const canSeeFleet = can('fleet.view')
  const canSeeMaintenance = can('maintenance.view')
  const canSetLocation = can('fleet.location')
  const navigate = useNavigate()
  const [stats, setStats] = useState(null)
  const [trends, setTrends] = useState(null)
  const [recentFlights, setRecentFlights] = useState([])
  const [upcomingMaintenance, setUpcomingMaintenance] = useState([])
  const [compliance, setCompliance] = useState(null)
  const [topPilots, setTopPilots] = useState([])
  const [topVehicles, setTopVehicles] = useState([])
  const [activity, setActivity] = useState([])
  const [locations, setLocations] = useState([])
  const [pilots, setPilots] = useState([])
  const [locationPlaces, setLocationPlaces] = useState(['North', 'Central', 'South'])
  const [loading, setLoading] = useState(true)
  const toast = useToast()
  const pageLayout = usePageLayout('dashboard_layout', 'default_dashboard_layout')

  useEffect(() => {
    let alive = true
    void Promise.all([
      api.get('/dashboard/stats').catch(() => null),
      api.get('/dashboard/trends').catch(() => null),
      getSection(canSeeFlights, '/flights?per_page=10', []),
      getSection(canSeeMaintenance, '/dashboard/maintenance-due', []),
      api.get('/dashboard/compliance').catch(() => null),
      getSection(canSeeFlights, '/dashboard/top-pilots-30d', []),
      getSection(canSeeFleet, '/dashboard/top-vehicles-30d', []),
      getSection(canSeeFlights, '/dashboard/activity-by-month', []),
      getSection(canSeeFleet, '/vehicles/locations', []),
      getSection(canSetLocation, '/pilots/options', []),
      api.get('/settings').catch(() => []),
    ]).then(([s, t, f, m, c, tp, tv, ac, locs, pilotList, settingsList]) => {
      if (!alive) return
      setStats(s)
      setTrends(t)
      setRecentFlights(asItemList(f, 'items', 'flights'))
      setUpcomingMaintenance(asItemList(m, 'items', 'maintenance'))
      setCompliance(c)
      setTopPilots(asArray(tp))
      setTopVehicles(asArray(tv))
      setActivity(asArray(ac))
      setLocations(asArray(locs))
      setPilots(asArray(pilotList).filter(p => p.status === 'active'))
      const placesRow = asArray(settingsList).find(s => s.key === 'drone_location_places')
      setLocationPlaces(parseLocationPlaces(placesRow))
    }).finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [canSeeFlights, canSeeFleet, canSeeMaintenance, canSetLocation])

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

  const reviewCount = stats?.flights_needing_review || 0
  const reviewItems = reviewCount > 0 ? [{ id: 'review' }] : []

  // Each tile's id is stored in saved layouts: never rename one.
  const tiles = [
    {
      id: 'compliance-summary', label: 'Compliance summary', span: 'lg:col-span-12',
      render: () => <HeroTile user={user} compliance={compliance} />,
    },
    {
      id: 'flights-30d', label: 'Flights (30d)', span: 'lg:col-span-3',
      render: () => (
        <StatTile
          label="Flights (30d)"
          value={trends?.current?.flights ?? stats?.total_flights ?? 0}
          deltaPct={trends?.deltas_pct?.flights}
          subtitle={`${stats?.total_flights ?? 0} total`}
          icon={QuadcopterIcon}
          to="/flights"
        />
      ),
    },
    {
      id: 'hours-30d', label: 'Hours (30d)', span: 'lg:col-span-3',
      render: () => (
        <StatTile
          label="Hours (30d)"
          value={trends?.current?.hours ?? formatHours((stats?.total_flight_hours ?? 0) * 3600)}
          deltaPct={trends?.deltas_pct?.hours}
          subtitle={`${formatHours((stats?.total_flight_hours ?? 0) * 3600)} total`}
          icon={Clock}
          to="/analytics"
        />
      ),
    },
    // Value and delta are who flew in the last 30 days; the roster total is
    // the subtitle, as on the flights and hours cards.
    {
      id: 'pilots-flying', label: 'Pilots Flying (30d)', span: 'lg:col-span-3',
      render: () => (
        <StatTile
          label="Pilots Flying (30d)"
          value={trends?.current?.active_pilots ?? '—'}
          deltaPct={trends?.deltas_pct?.active_pilots}
          subtitle={`${stats?.active_pilots ?? 0} active`}
          icon={Users}
          to="/pilots"
        />
      ),
    },
    {
      id: 'vehicles-flown', label: 'Vehicles Flown (30d)', span: 'lg:col-span-3',
      render: () => (
        <StatTile
          label="Vehicles Flown (30d)"
          value={trends?.current?.active_vehicles ?? '—'}
          deltaPct={trends?.deltas_pct?.active_vehicles}
          subtitle={`${stats?.fleet_size ?? 0} in fleet`}
          icon={Box}
          to="/fleet"
        />
      ),
    },
    {
      id: 'recent-flights', label: 'Recent Flights', span: 'lg:col-span-6 lg:row-span-2',
      render: () => <RecentFlightsTile flights={recentFlights} />,
    },
    {
      id: 'needs-review', label: 'Needs Review', span: 'lg:col-span-3',
      render: () => (
        <ListTile
          title="Needs Review"
          icon={ClipboardCheck}
          items={reviewItems}
          emptyLabel="Queue is clear"
          link="/flights?review_status=needs_review"
          linkLabel="Open"
          renderItem={() => (
            <li key="rev" className="px-4 py-3">
              <div className="flex items-center justify-between">
                <span className="text-3xl font-bold text-amber-400">{reviewCount}</span>
                <button onClick={() => navigate('/flights?review_status=needs_review')} className="text-xs text-primary hover:underline">Review →</button>
              </div>
              <p className="text-xs text-muted-foreground mt-1">flights awaiting supervisor review</p>
            </li>
          )}
        />
      ),
    },
    {
      id: 'maintenance-due', label: 'Maintenance Due', span: 'lg:col-span-3',
      render: () => (
        <ListTile
          title="Maintenance Due"
          icon={Wrench}
          items={upcomingMaintenance}
          emptyLabel="No maintenance due"
          link="/maintenance"
          renderItem={(m) => (
            // The endpoint returns both schedules and records, already deduped
            // and sorted most-overdue first, so the tile just renders them.
            <li key={`${m.source}-${m.id}`}>
              <Link to="/maintenance" className="flex items-center gap-2 px-4 py-2 hover:bg-secondary/50 transition-colors">
                <span className={`inline-flex min-w-14 justify-center px-1.5 py-0.5 rounded-full text-[10px] font-medium border whitespace-nowrap ${
                  countdownTone(m.days_remaining < 0, m.days_remaining <= 7)
                }`}>
                  {dueLabel(m.days_remaining)}
                </span>
                <span className="text-xs text-foreground truncate flex-1">{m.name}</span>
              </Link>
            </li>
          )}
        />
      ),
    },
    // Wide enough to close the row beside Recent Flights.
    {
      id: 'cert-expirations', label: 'Cert Expirations', span: 'lg:col-span-6',
      render: () => (
        <ListTile
          title="Cert Expirations"
          icon={AlertTriangle}
          items={expiringCerts}
          emptyLabel="None expiring soon"
          link="/certifications"
          renderItem={(c, idx) => (
            <li key={`${c.pilot_id}-${idx}`}>
              <Link to={`/pilots/${c.pilot_id}`} className="flex items-center gap-2 px-4 py-2 hover:bg-secondary/50 transition-colors">
                <span className={`inline-flex w-14 justify-center px-1.5 py-0.5 rounded-full text-[10px] font-medium border ${
                  countdownTone(c.days_remaining < 0, c.days_remaining <= 30)
                }`}>
                  {countdownLabel(c.days_remaining)}
                </span>
                <span className="text-xs text-foreground truncate flex-1">
                  {[c.pilot_name || `Pilot #${c.pilot_id}`, c.cert_type_name].filter(Boolean).join(' - ')}
                </span>
              </Link>
            </li>
          )}
        />
      ),
    },
    {
      id: 'activity', label: 'Activity by Month', span: 'lg:col-span-6',
      render: () => <ActivityChartTile data={activity} />,
    },
    {
      id: 'top-pilots', label: 'Top Pilots (30d)', span: 'lg:col-span-3',
      render: () => (
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
      ),
    },
    {
      id: 'top-vehicles', label: 'Top Vehicles (30d)', span: 'lg:col-span-3',
      render: () => (
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
      ),
    },
    // Flight requirements this period, beside the drone locations
    {
      id: 'this-period', label: 'This Period', span: 'lg:col-span-8', visible: can('requirements.view'),
      render: () => <ThisPeriodTile />,
    },
    {
      id: 'locations', label: 'Locations', span: 'lg:col-span-4',
      render: () => (
        <LocationsTile items={locations} pilots={pilots} places={locationPlaces} onChange={handleSetLocation} canSetLocation={canSetLocation} />
      ),
    },
  ]

  return <ArrangeableGrid tiles={tiles} className="grid-cols-1 sm:grid-cols-2 lg:grid-cols-12" {...pageLayout} />
}
