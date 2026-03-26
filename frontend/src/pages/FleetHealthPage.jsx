import { useState, useEffect } from 'react'
import { api } from '@/api/client'
import { Link } from 'react-router-dom'
import { Activity, Battery, AlertTriangle, Clock, ChevronUp, ChevronDown } from 'lucide-react'
import { QuadcopterIcon } from '@/components/icons/QuadcopterIcon'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'

function getHealthColor(pct) {
  if (pct == null) return '#71717a'
  if (pct > 80) return '#10b981'
  if (pct >= 50) return '#f59e0b'
  return '#ef4444'
}

function getHealthBadge(pct) {
  if (pct == null) return 'bg-zinc-500/15 text-zinc-400'
  if (pct > 80) return 'bg-emerald-500/15 text-emerald-400'
  if (pct >= 50) return 'bg-amber-500/15 text-amber-400'
  return 'bg-red-500/15 text-red-400'
}

export default function FleetHealthPage() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [sortKey, setSortKey] = useState('name')
  const [sortDir, setSortDir] = useState('asc')

  useEffect(() => {
    api.get('/dashboard/analytics/fleet-health')
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleSort = (key) => {
    if (sortKey === key) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  const SortIcon = ({ col }) => {
    if (sortKey !== col) return null
    return sortDir === 'asc' ? <ChevronUp className="w-3.5 h-3.5 inline ml-0.5" /> : <ChevronDown className="w-3.5 h-3.5 inline ml-0.5" />
  }

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
  if (!data) return <div className="text-center text-muted-foreground py-12">Failed to load fleet health data</div>

  const sortedVehicles = [...(data.vehicles || [])].sort((a, b) => {
    let av = a[sortKey], bv = b[sortKey]
    if (typeof av === 'string') av = av.toLowerCase()
    if (typeof bv === 'string') bv = bv.toLowerCase()
    if (av == null) return 1
    if (bv == null) return -1
    if (av < bv) return sortDir === 'asc' ? -1 : 1
    if (av > bv) return sortDir === 'asc' ? 1 : -1
    return 0
  })

  const batteryChartData = (data.batteries || []).map(b => ({
    name: b.nickname || b.serial || `Battery ${b.id}`,
    health: b.health_pct ?? 0,
    fill: getHealthColor(b.health_pct),
  }))

  const { summary } = data

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Fleet Health</h1>
        <p className="text-sm text-muted-foreground mt-1">Vehicle utilization and battery health overview</p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary/15 flex items-center justify-center text-primary"><QuadcopterIcon className="w-5 h-5" /></div>
          <div><p className="text-2xl font-bold text-foreground">{summary.total_vehicles}</p><p className="text-xs text-muted-foreground">Active Vehicles</p></div>
        </div>
        <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-500/15 flex items-center justify-center text-blue-400"><Battery className="w-5 h-5" /></div>
          <div><p className="text-2xl font-bold text-foreground">{summary.total_batteries}</p><p className="text-xs text-muted-foreground">Total Batteries</p></div>
        </div>
        <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-500/15 flex items-center justify-center text-emerald-400"><Activity className="w-5 h-5" /></div>
          <div><p className="text-2xl font-bold text-foreground">{summary.avg_battery_health}%</p><p className="text-xs text-muted-foreground">Avg Battery Health</p></div>
        </div>
        <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${summary.total_overdue_maintenance > 0 ? 'bg-red-500/15 text-red-400' : 'bg-emerald-500/15 text-emerald-400'}`}>
            <AlertTriangle className="w-5 h-5" />
          </div>
          <div><p className="text-2xl font-bold text-foreground">{summary.total_overdue_maintenance}</p><p className="text-xs text-muted-foreground">Overdue Maintenance</p></div>
        </div>
        <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-amber-500/15 flex items-center justify-center text-amber-400"><Clock className="w-5 h-5" /></div>
          <div><p className="text-2xl font-bold text-foreground">{summary.total_flight_hours}h</p><p className="text-xs text-muted-foreground">Total Flight Hours</p></div>
        </div>
      </div>

      {/* Vehicle Utilization Table */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-border">
          <h3 className="font-semibold text-foreground">Vehicle Utilization</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/30">
                <th className="text-left px-4 py-2 text-muted-foreground font-medium cursor-pointer select-none" onClick={() => handleSort('name')}>
                  Vehicle <SortIcon col="name" />
                </th>
                <th className="text-left px-4 py-2 text-muted-foreground font-medium cursor-pointer select-none" onClick={() => handleSort('flights')}>
                  Flights <SortIcon col="flights" />
                </th>
                <th className="text-left px-4 py-2 text-muted-foreground font-medium cursor-pointer select-none" onClick={() => handleSort('hours')}>
                  Hours <SortIcon col="hours" />
                </th>
                <th className="text-left px-4 py-2 text-muted-foreground font-medium cursor-pointer select-none hidden md:table-cell" onClick={() => handleSort('last_flight')}>
                  Last Flight <SortIcon col="last_flight" />
                </th>
                <th className="text-left px-4 py-2 text-muted-foreground font-medium cursor-pointer select-none" onClick={() => handleSort('overdue_maintenance')}>
                  Overdue <SortIcon col="overdue_maintenance" />
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedVehicles.map(v => (
                <tr key={v.id} className="border-b border-border/50 hover:bg-accent/30">
                  <td className="px-4 py-2 text-foreground font-medium">
                    <Link to={`/fleet/vehicles/${v.id}`} className="hover:text-primary">{v.name}</Link>
                    {v.serial && <span className="text-xs text-muted-foreground ml-2">{v.serial}</span>}
                  </td>
                  <td className="px-4 py-2 text-muted-foreground">{v.flights}</td>
                  <td className="px-4 py-2 text-muted-foreground">{v.hours}h</td>
                  <td className="px-4 py-2 text-muted-foreground hidden md:table-cell">{v.last_flight || 'Never'}</td>
                  <td className="px-4 py-2">
                    {v.overdue_maintenance > 0 ? (
                      <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-red-500/15 text-red-400">
                        {v.overdue_maintenance} overdue
                      </span>
                    ) : (
                      <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/15 text-emerald-400">
                        OK
                      </span>
                    )}
                  </td>
                </tr>
              ))}
              {sortedVehicles.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">No active vehicles</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Battery Health Chart */}
      {batteryChartData.length > 0 && (
        <div className="bg-card border border-border rounded-xl p-5">
          <h3 className="text-sm font-semibold text-foreground mb-4">Battery Health</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={batteryChartData} layout="vertical" margin={{ left: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
              <XAxis type="number" domain={[0, 100]} tick={{ fill: 'var(--muted-fg)', fontSize: 11 }} unit="%" />
              <YAxis type="category" dataKey="name" tick={{ fill: 'var(--muted-fg)', fontSize: 11 }} width={120} />
              <Tooltip
                contentStyle={{ background: 'var(--card)', border: '1px solid var(--border-color)', borderRadius: '8px', color: 'var(--fg)' }}
                formatter={(val) => [`${val}%`, 'Health']}
              />
              <Bar dataKey="health" radius={[0, 4, 4, 0]} name="Health %">
                {batteryChartData.map((entry, i) => (
                  <Cell key={i} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div className="flex items-center gap-4 mt-3 text-xs text-muted-foreground justify-center">
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm bg-emerald-500 inline-block" /> &gt;80% Good</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm bg-amber-500 inline-block" /> 50-80% Fair</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm bg-red-500 inline-block" /> &lt;50% Poor</span>
          </div>
        </div>
      )}
    </div>
  )
}
