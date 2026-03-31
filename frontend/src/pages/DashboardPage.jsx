import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { api } from '@/api/client'
import { Clock, Users, Box, AlertTriangle, ClipboardCheck, ArrowRight, Wrench } from 'lucide-react'
import { QuadcopterIcon } from '@/components/icons/QuadcopterIcon'
import { formatDuration, formatHours } from '@/lib/utils'

function StatCard({ title, value, subtitle, icon: Icon, color = 'primary', to }) {
  const colorMap = {
    primary: 'bg-primary/15 text-primary',
    blue: 'bg-blue-500/15 text-blue-400',
    green: 'bg-emerald-500/15 text-emerald-400',
    amber: 'bg-amber-500/15 text-amber-400',
    red: 'bg-red-500/15 text-red-400',
    purple: 'bg-purple-500/15 text-purple-400',
  }

  const card = (
    <div className="bg-card border border-border rounded-xl p-5 hover:border-primary/50 cursor-pointer transition-all h-full">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-muted-foreground">{title}</p>
          <p className="text-3xl font-bold text-foreground mt-1">{value}</p>
          {subtitle && <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>}
        </div>
        <div className={`w-11 h-11 rounded-xl flex items-center justify-center ${colorMap[color]}`}>
          <Icon className="w-5 h-5" />
        </div>
      </div>
    </div>
  )

  if (to) {
    return <Link to={to} className="block">{card}</Link>
  }
  return card
}

function getDaysRemaining(dateStr) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const target = new Date(dateStr)
  target.setHours(0, 0, 0, 0)
  return Math.ceil((target - today) / (1000 * 60 * 60 * 24))
}

function getDaysColor(days) {
  if (days < 0) return 'text-red-400'
  if (days <= 30) return 'text-red-400'
  if (days <= 60) return 'text-amber-400'
  return 'text-emerald-400'
}

function getDaysBadge(days) {
  if (days < 0) return 'bg-red-500/15 text-red-400'
  if (days <= 30) return 'bg-red-500/15 text-red-400'
  if (days <= 60) return 'bg-amber-500/15 text-amber-400'
  return 'bg-emerald-500/15 text-emerald-400'
}

export default function DashboardPage() {
  const [stats, setStats] = useState(null)
  const [recentFlights, setRecentFlights] = useState([])
  const [upcomingCerts, setUpcomingCerts] = useState([])
  const [upcomingMaintenance, setUpcomingMaintenance] = useState([])
  const [fleetHealth, setFleetHealth] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      api.get('/dashboard/stats').catch(() => null),
      api.get('/flights?per_page=10').catch(() => []),
      api.get('/pilot-certifications').catch(() => []),
      api.get('/maintenance?upcoming=true').catch(() => []),
      api.get('/dashboard/analytics/fleet-health').catch(() => null),
    ])
      .then(([statsData, flightsData, certsData, maintenanceData, fleetHealthData]) => {
        setStats(statsData)

        // Handle flights - could be paginated or plain array
        const flights = Array.isArray(flightsData) ? flightsData : (flightsData?.items || flightsData?.flights || [])
        setRecentFlights(flights.slice(0, 10))

        // Filter certifications expiring within 90 days
        const certs = Array.isArray(certsData) ? certsData : (certsData?.items || certsData?.certifications || [])
        const today = new Date()
        const ninetyDaysOut = new Date(today)
        ninetyDaysOut.setDate(ninetyDaysOut.getDate() + 90)

        const expiringSoon = certs
          .filter(cert => {
            if (!cert.expiration_date) return false
            const expDate = new Date(cert.expiration_date)
            return expDate <= ninetyDaysOut && expDate >= today
          })
          .sort((a, b) => new Date(a.expiration_date) - new Date(b.expiration_date))

        setUpcomingCerts(expiringSoon)

        // Handle maintenance
        const maint = Array.isArray(maintenanceData) ? maintenanceData : (maintenanceData?.items || maintenanceData?.maintenance || [])
        setUpcomingMaintenance(maint)

        // Fleet health
        setFleetHealth(fleetHealthData)
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
        <StatCard
          title="Total Flights"
          value={stats?.total_flights || 0}
          icon={QuadcopterIcon}
          color="primary"
          to="/flights"
        />
        <StatCard
          title="Flight Hours"
          value={formatHours(stats?.total_flight_hours * 3600 || 0)}
          subtitle="hours"
          icon={Clock}
          color="blue"
          to="/analytics"
        />
        <StatCard
          title="Active Pilots"
          value={stats?.active_pilots || 0}
          icon={Users}
          color="green"
          to="/pilots"
        />
        <StatCard
          title="Fleet Size"
          value={stats?.fleet_size || 0}
          icon={Box}
          color="purple"
          to="/fleet"
        />
        <StatCard
          title="Needs Review"
          value={stats?.flights_needing_review || 0}
          icon={ClipboardCheck}
          color={stats?.flights_needing_review > 0 ? 'amber' : 'green'}
          to="/flights?review_status=needs_review"
        />
        <StatCard
          title="Cert Expirations"
          value={stats?.upcoming_cert_expirations || 0}
          subtitle="next 90 days"
          icon={AlertTriangle}
          color={stats?.upcoming_cert_expirations > 0 ? 'red' : 'green'}
          to="/certifications"
        />
      </div>

      {/* Recent Flights + Cert Expirations */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Recent Flights - 2/3 width */}
        <div className="lg:col-span-2 bg-card border border-border rounded-xl overflow-hidden">
          <div className="flex items-center justify-between p-5 border-b border-border">
            <h3 className="font-semibold text-foreground">Recent Flights</h3>
            <Link to="/flights" className="text-sm text-primary hover:text-primary/80 flex items-center gap-1 transition-colors">
              View all <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
          {recentFlights.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left">
                    <th className="px-5 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wider">Flight ID</th>
                    <th className="px-5 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wider">Date</th>
                    <th className="px-5 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wider">Pilot</th>
                    <th className="px-5 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wider hidden md:table-cell">Vehicle</th>
                    <th className="px-5 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wider hidden md:table-cell">Purpose</th>
                    <th className="px-5 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wider">Duration</th>
                    <th className="px-5 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wider">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {recentFlights.map((flight) => (
                    <tr key={flight.id} className="hover:bg-muted/50 transition-colors">
                      <td className="px-5 py-3 text-xs font-mono">
                        <Link to={`/flights/${flight.id}`} className="text-primary hover:underline">
                          {flight.external_id ? flight.external_id.slice(0, 8) : `#${flight.id}`}
                        </Link>
                      </td>
                      <td className="px-5 py-3 text-foreground">
                        {flight.date
                          ? new Date(flight.date + 'T00:00:00').toLocaleDateString()
                          : '—'}
                      </td>
                      <td className="px-5 py-3 text-foreground">
                        {flight.pilot_id
                          ? <Link to={`/pilots/${flight.pilot_id}`} className="text-primary hover:underline">{flight.pilot_name || flight.pilot?.name || '—'}</Link>
                          : (flight.pilot_name || flight.pilot?.name || '—')
                        }
                      </td>
                      <td className="px-5 py-3 text-foreground hidden md:table-cell">
                        {flight.vehicle_id
                          ? <Link to={`/fleet/vehicles/${flight.vehicle_id}`} className="text-primary hover:underline">{flight.vehicle_name || flight.vehicle?.name || flight.vehicle?.serial_number || '—'}</Link>
                          : (flight.vehicle_name || flight.vehicle?.name || flight.vehicle?.serial_number || '—')
                        }
                      </td>
                      <td className="px-5 py-3 text-foreground hidden md:table-cell">
                        {(flight.purpose || flight.flight_purpose) ? <Link to={`/flights?purpose=${encodeURIComponent(flight.purpose || flight.flight_purpose)}`} className="text-primary hover:underline">{flight.purpose || flight.flight_purpose}</Link> : '—'}
                      </td>
                      <td className="px-5 py-3 text-foreground">
                        {flight.duration_seconds
                          ? formatDuration(flight.duration_seconds)
                          : flight.duration
                            ? formatDuration(flight.duration)
                            : '—'}
                      </td>
                      <td className="px-5 py-3">
                        <FlightStatusBadge status={flight.review_status || flight.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-8 text-center text-muted-foreground text-sm">
              No flights recorded yet.
            </div>
          )}
        </div>

        {/* Upcoming Cert Expirations - 1/3 width */}
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <div className="flex items-center justify-between p-5 border-b border-border">
            <h3 className="font-semibold text-foreground">Cert Expirations</h3>
            <Link to="/certifications" className="text-sm text-primary hover:text-primary/80 flex items-center gap-1 transition-colors">
              View all <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
          {upcomingCerts.length > 0 ? (
            <div className="divide-y divide-border">
              {upcomingCerts.map((cert, idx) => {
                const days = getDaysRemaining(cert.expiration_date)
                return (
                  <div key={cert.id || idx} className="px-5 py-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-foreground truncate">
                          {cert.pilot_name || cert.pilot?.name || 'Unknown Pilot'}
                        </p>
                        <p className="text-xs text-muted-foreground truncate">
                          {cert.certification_name || cert.certification?.name || cert.name || 'Certification'}
                        </p>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          Exp: {new Date(cert.expiration_date).toLocaleDateString()}
                        </p>
                      </div>
                      <span className={`text-xs font-medium px-2 py-1 rounded-full whitespace-nowrap ${getDaysBadge(days)}`}>
                        {days <= 0 ? 'Expired' : `${days}d`}
                      </span>
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <div className="p-8 text-center text-muted-foreground text-sm">
              No certifications expiring soon.
            </div>
          )}
        </div>
      </div>

      {/* Upcoming Maintenance */}
      {upcomingMaintenance.length > 0 && (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <div className="flex items-center justify-between p-5 border-b border-border">
            <h3 className="font-semibold text-foreground">Upcoming Maintenance</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="px-5 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wider">Description</th>
                  <th className="px-5 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wider">Entity</th>
                  <th className="px-5 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wider">Next Due</th>
                  <th className="px-5 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wider">Days Remaining</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {upcomingMaintenance.map((item, idx) => {
                  const dueDate = item.next_due_date || item.due_date
                  const days = dueDate ? getDaysRemaining(dueDate) : null
                  return (
                    <tr key={item.id || idx} className="hover:bg-muted/50 transition-colors">
                      <td className="px-5 py-3 text-foreground">
                        {item.description || item.name || '—'}
                      </td>
                      <td className="px-5 py-3 text-foreground">
                        {item.entity_type || item.vehicle_name || item.vehicle?.name || '—'}
                      </td>
                      <td className="px-5 py-3 text-foreground">
                        {dueDate ? new Date(dueDate).toLocaleDateString() : '—'}
                      </td>
                      <td className="px-5 py-3">
                        {days !== null ? (
                          <span className={`text-sm font-medium ${getDaysColor(days)}`}>
                            {days <= 0 ? 'Overdue' : `${days} days`}
                          </span>
                        ) : '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Fleet Overview */}
      {fleetHealth && fleetHealth.summary && (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <div className="flex items-center justify-between p-5 border-b border-border">
            <h3 className="font-semibold text-foreground">Fleet Overview</h3>
            <Link to="/fleet" className="text-sm text-primary hover:text-primary/80 flex items-center gap-1 transition-colors">
              Manage fleet <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 p-5">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-blue-500/15 flex items-center justify-center text-blue-400">
                <Clock className="w-5 h-5" />
              </div>
              <div>
                <p className="text-2xl font-bold text-foreground">{fleetHealth.summary.total_flight_hours}h</p>
                <p className="text-xs text-muted-foreground">Total Fleet Hours</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-blue-500/15 flex items-center justify-center text-blue-400">
                <QuadcopterIcon className="w-5 h-5" />
              </div>
              <div>
                {(() => {
                  const topVehicles = [...(fleetHealth.vehicles || [])].sort((a, b) => (b.hours || 0) - (a.hours || 0)).slice(0, 3)
                  return topVehicles.length > 0 ? (
                    <div className="space-y-0.5">
                      {topVehicles.map((v) => (
                        <p key={v.id} className="text-xs">
                          <Link to={`/fleet/vehicles/${v.id}`} className="text-primary font-medium hover:underline">{v.name}</Link>
                          <span className="text-muted-foreground ml-1">{v.hours}h / {v.flights} flights</span>
                        </p>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">No vehicle data</p>
                  )
                })()}
                <p className="text-xs text-muted-foreground mt-0.5">Top Vehicles</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-purple-500/15 flex items-center justify-center text-purple-400">
                <Box className="w-5 h-5" />
              </div>
              <div>
                <p className="text-2xl font-bold text-foreground">{fleetHealth.summary.total_batteries}</p>
                <p className="text-xs text-muted-foreground">Batteries in Service</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${fleetHealth.summary.total_overdue_maintenance > 0 ? 'bg-red-500/15 text-red-400' : 'bg-emerald-500/15 text-emerald-400'}`}>
                <Wrench className="w-5 h-5" />
              </div>
              <div>
                <p className="text-2xl font-bold text-foreground">{fleetHealth.summary.total_overdue_maintenance}</p>
                <p className="text-xs text-muted-foreground">Overdue Maintenance</p>
              </div>
            </div>
          </div>
        </div>
      )}

    </div>
  )
}

function FlightStatusBadge({ status }) {
  const styles = {
    approved: 'bg-emerald-500/15 text-emerald-400',
    reviewed: 'bg-emerald-500/15 text-emerald-400',
    needs_review: 'bg-amber-500/15 text-amber-400',
    pending: 'bg-amber-500/15 text-amber-400',
    rejected: 'bg-red-500/15 text-red-400',
    completed: 'bg-blue-500/15 text-blue-400',
  }

  const label = status ? status.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) : 'Unknown'
  const style = styles[status] || 'bg-muted text-muted-foreground'

  return (
    <span className={`text-xs font-medium px-2 py-1 rounded-full ${style}`}>
      {label}
    </span>
  )
}
