import { useState, useEffect, useMemo, useCallback } from 'react'
import { api } from '@/api/client'
import { X, Filter } from 'lucide-react'
import { FlightLocationsMap } from '@/components/FlightMap'
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'

// Last token of a name ("Mary Jane Smith" -> "Smith"); single-word names ("Unknown") unchanged.
function lastName(fullName) {
  if (!fullName) return fullName
  const parts = String(fullName).trim().split(/\s+/)
  return parts.at(-1)
}

// Extract the flight array from either a paginated envelope or a raw array.
function pageFlights(res) {
  return Array.isArray(res) ? res : (res?.flights || res?.items || res?.data || [])
}

// Fetch every flight across all pages. The analytics endpoints aggregate
// server-side over the full dataset, so the client-side cross-filter must see
// every flight too. A single capped request (per_page=1000) silently dropped
// rows past 1000, drifting the filtered counts away from the server totals.
async function fetchAllFlights() {
  const perPage = 1000
  const first = await api.get(`/flights?per_page=${perPage}&page=1`)
  const all = pageFlights(first)
  const totalPages = first?.total_pages || 1
  if (totalPages <= 1) return all
  const rest = await Promise.all(
    Array.from({ length: totalPages - 1 }, (_, i) =>
      api.get(`/flights?per_page=${perPage}&page=${i + 2}`).then(pageFlights)
    )
  )
  return rest.reduce((acc, chunk) => acc.concat(chunk), all)
}

const COLORS = [
  '#6366f1', '#3b82f6', '#10b981', '#f59e0b', '#ef4444',
  '#8b5cf6', '#ec4899', '#14b8a6', '#f97316', '#06b6d4',
  '#84cc16', '#a855f7',
]

const DIM_OPACITY = 0.2

const tooltipStyle = {
  contentStyle: {
    background: 'var(--card)',
    border: '1px solid var(--border-color)',
    borderRadius: '8px',
    color: 'var(--fg)',
  },
  labelStyle: { color: 'var(--fg)' },
  // Bars use a custom shape with no fill, so Recharts has no series color and
  // falls back to #000 per item — unreadable on every theme except Light.
  itemStyle: { color: 'var(--fg)' },
}

function ChartCard({ title, children }) {
  return (
    <div className="bg-card border border-border rounded-xl p-5">
      <h3 className="text-sm font-semibold text-foreground mb-4">{title}</h3>
      {children}
    </div>
  )
}

// Returns a color with the given opacity as an rgba string
function withOpacity(hex, opacity) {
  const r = Number.parseInt(hex.slice(1, 3), 16)
  const g = Number.parseInt(hex.slice(3, 5), 16)
  const b = Number.parseInt(hex.slice(5, 7), 16)
  return `rgba(${r}, ${g}, ${b}, ${opacity})`
}

function createTotalBarRenderer(color, isFiltered) {
  return (props) => {
    const { x, y, width, height } = props
    if (!height || height <= 0) return null
    return (
      <rect
        x={x} y={y} width={width} height={height}
        fill={isFiltered ? withOpacity(color, DIM_OPACITY) : color}
        rx={4} ry={4}
      />
    )
  }
}

function createFilteredBarRenderer(color) {
  return (props) => {
    const { x, y, width, height } = props
    if (!height || height <= 0) return null
    return (
      <rect x={x} y={y} width={width} height={height} fill={color} rx={4} ry={4} />
    )
  }
}

function createTotalBarHRenderer(color, isFiltered) {
  return (props) => {
    const { x, y, width, height } = props
    if (!width || width <= 0) return null
    return (
      <rect
        x={x} y={y} width={width} height={height}
        fill={isFiltered ? withOpacity(color, DIM_OPACITY) : color}
        rx={4} ry={4}
      />
    )
  }
}

function createFilteredBarHRenderer(color) {
  return (props) => {
    const { x, y, width, height } = props
    if (!width || width <= 0) return null
    return (
      <rect x={x} y={y} width={width} height={height} fill={color} rx={4} ry={4} />
    )
  }
}

export default function AnalyticsPage() {
  // Raw data from API
  const [byPurpose, setByPurpose] = useState([])
  const [byYear, setByYear] = useState([])
  const [byPilot, setByPilot] = useState([])
  const [avgDuration, setAvgDuration] = useState([])
  const [monthly, setMonthly] = useState([])
  const [vehicleHours, setVehicleHours] = useState([])
  const [pilotHours, setPilotHours] = useState([])
  const [allFlights, setAllFlights] = useState([])
  const [loading, setLoading] = useState(true)

  // Cross-filter state
  const [filters, setFilters] = useState({ pilot: null, year: null, purpose: null })

  const hasActiveFilter = filters.pilot || filters.year || filters.purpose

  const clearFilters = useCallback(() => {
    setFilters({ pilot: null, year: null, purpose: null })
  }, [])

  const toggleFilter = useCallback((key, value) => {
    setFilters(prev => ({
      ...prev,
      [key]: prev[key] === value ? null : value,
    }))
  }, [])

  // Fetch all data on mount
  useEffect(() => {
    Promise.all([
      api.get('/dashboard/analytics/flights-by-purpose'),
      api.get('/dashboard/analytics/flights-by-year'),
      api.get('/dashboard/analytics/flights-by-pilot'),
      api.get('/dashboard/analytics/avg-duration-by-year'),
      api.get('/dashboard/analytics/monthly-flights'),
      api.get('/dashboard/analytics/vehicle-hours'),
      api.get('/dashboard/analytics/pilot-hours'),
      fetchAllFlights(),
    ]).then(([purpose, year, pilot, dur, mon, veh, pil, flights]) => {
      setByPurpose(purpose)
      setByYear(year)
      setByPilot(pilot)
      setAvgDuration(dur)
      setMonthly(mon.map(m => ({ ...m, label: `${m.year}-${String(m.month).padStart(2, '0')}` })))
      setVehicleHours(veh)
      setPilotHours(pil)
      setAllFlights(flights)
    }).catch(() => {}).finally(() => setLoading(false))
  }, [])

  // Compute filtered subsets from allFlights when filters change
  const filteredFlights = useMemo(() => {
    if (!hasActiveFilter) return allFlights
    return allFlights.filter(f => {
      if (filters.pilot != null && f.pilot_id !== filters.pilot) return false
      if (filters.year) {
        const flightDate = f.date || f.takeoff_time
        if (!flightDate) return false
        const yr = new Date(flightDate).getFullYear()
        if (yr !== filters.year) return false
      }
      if (filters.purpose && f.purpose !== filters.purpose) return false
      return true
    })
  }, [allFlights, filters, hasActiveFilter])

  // Derive filtered counts for each chart dimension
  const filteredByPurpose = useMemo(() => {
    if (!hasActiveFilter) return null
    const counts = {}
    filteredFlights.forEach(f => {
      counts[f.purpose] = (counts[f.purpose] || 0) + 1
    })
    return counts
  }, [filteredFlights, hasActiveFilter])

  const filteredByYear = useMemo(() => {
    if (!hasActiveFilter) return null
    const counts = {}
    filteredFlights.forEach(f => {
      const flightDate = f.date || f.takeoff_time
      if (!flightDate) return
      const yr = new Date(flightDate).getFullYear()
      counts[yr] = (counts[yr] || 0) + 1
    })
    return counts
  }, [filteredFlights, hasActiveFilter])

  const filteredByPilot = useMemo(() => {
    if (!hasActiveFilter) return null
    const counts = {}
    filteredFlights.forEach(f => {
      counts[f.pilot_id] = (counts[f.pilot_id] || 0) + 1
    })
    return counts
  }, [filteredFlights, hasActiveFilter])

  const filteredAvgDuration = useMemo(() => {
    if (!hasActiveFilter) return null
    const groups = {}
    filteredFlights.forEach(f => {
      const flightDate = f.date || f.takeoff_time
      if (!flightDate) return
      const yr = new Date(flightDate).getFullYear()
      if (!groups[yr]) groups[yr] = []
      const dur = f.duration_seconds || f.duration || 0
      groups[yr].push(dur)
    })
    const result = {}
    Object.entries(groups).forEach(([yr, durations]) => {
      result[yr] = durations.reduce((a, b) => a + b, 0) / durations.length
    })
    return result
  }, [filteredFlights, hasActiveFilter])

  const filteredMonthly = useMemo(() => {
    if (!hasActiveFilter) return null
    const counts = {}
    filteredFlights.forEach(f => {
      const flightDate = f.date || f.takeoff_time
      if (!flightDate) return
      const d = new Date(flightDate)
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
      counts[key] = (counts[key] || 0) + 1
    })
    return counts
  }, [filteredFlights, hasActiveFilter])

  const filteredVehicleHours = useMemo(() => {
    if (!hasActiveFilter) return null
    const groups = {}
    filteredFlights.forEach(f => {
      const name = f.vehicle_name || f.drone_name || 'Unknown'
      const hrs = (f.duration_seconds || f.duration || 0) / 3600
      groups[name] = (groups[name] || 0) + hrs
    })
    return groups
  }, [filteredFlights, hasActiveFilter])

  const filteredPilotHours = useMemo(() => {
    if (!hasActiveFilter) return null
    const groups = {}
    filteredFlights.forEach(f => {
      if (!groups[f.pilot_name]) groups[f.pilot_name] = { hours: 0, count: 0 }
      groups[f.pilot_name].hours += (f.duration_seconds || f.duration || 0) / 3600
      groups[f.pilot_name].count += 1
    })
    return groups
  }, [filteredFlights, hasActiveFilter])

  // Build merged data for each chart (total + filtered columns)
  const purposeData = useMemo(() => {
    return byPurpose.map(d => ({
      ...d,
      total: d.count,
      filtered: filteredByPurpose ? (filteredByPurpose[d.purpose] || 0) : d.count,
    }))
  }, [byPurpose, filteredByPurpose])

  const yearData = useMemo(() => {
    return byYear.map(d => ({
      ...d,
      total: d.count,
      filtered: filteredByYear ? (filteredByYear[d.year] || 0) : d.count,
    }))
  }, [byYear, filteredByYear])

  const durationData = useMemo(() => {
    return avgDuration.map(d => ({
      ...d,
      total: d.avg_seconds,
      filtered: filteredAvgDuration ? (filteredAvgDuration[d.year] || 0) : d.avg_seconds,
    }))
  }, [avgDuration, filteredAvgDuration])

  const monthlyData = useMemo(() => {
    return monthly.map(d => ({
      ...d,
      total: d.count,
      filtered: filteredMonthly ? (filteredMonthly[d.label] || 0) : d.count,
    }))
  }, [monthly, filteredMonthly])

  const vehicleData = useMemo(() => {
    return vehicleHours.map(d => ({
      ...d,
      total: d.hours,
      filtered: filteredVehicleHours ? (filteredVehicleHours[d.vehicle_name] || 0) : d.hours,
    }))
  }, [vehicleHours, filteredVehicleHours])

  // Slice color for a pilot, dimmed when a filter excludes them. Shared by the
  // pie Cells and the custom legend so colors stay in sync. Keyed by pilot_id
  // so pilots sharing a display name don't collide.
  const pilotFill = (pilotId, i) => {
    const baseColor = COLORS[i % COLORS.length]
    if (hasActiveFilter && filteredByPilot && (filteredByPilot[pilotId] || 0) <= 0) {
      return withOpacity(baseColor, DIM_OPACITY)
    }
    return baseColor
  }

  // Resolve a pilot_id to its display name for the active-filter chip.
  const pilotNameById = (pilotId) =>
    byPilot.find(p => p.pilot_id === pilotId)?.pilot_name ?? pilotId

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  // Custom bar shape for overlapping bars (filtered on top of dimmed total)
  const renderTotalBar = (color) => createTotalBarRenderer(color, hasActiveFilter)
  const renderFilteredBar = (color) => createFilteredBarRenderer(color)
  const renderTotalBarH = (color) => createTotalBarHRenderer(color, hasActiveFilter)
  const renderFilteredBarH = (color) => createFilteredBarHRenderer(color)

  return (
    <div className="space-y-6">
      {/* Active Filters Bar */}
      {hasActiveFilter && (
        <div className="flex items-center gap-2 flex-wrap bg-card border border-border rounded-xl px-4 py-3">
          <Filter size={14} className="text-muted-foreground" />
          <span className="text-sm text-muted-foreground mr-1">Active filters:</span>
          {filters.pilot && (
            <button
              onClick={() => toggleFilter('pilot', filters.pilot)}
              className="inline-flex items-center gap-1 px-2.5 py-1 bg-indigo-500/15 text-indigo-400 rounded-full text-xs font-medium hover:bg-indigo-500/25 transition-colors"
            >
              Pilot: {pilotNameById(filters.pilot)}
              <X size={12} />
            </button>
          )}
          {filters.year && (
            <button
              onClick={() => toggleFilter('year', filters.year)}
              className="inline-flex items-center gap-1 px-2.5 py-1 bg-blue-500/15 text-blue-400 rounded-full text-xs font-medium hover:bg-blue-500/25 transition-colors"
            >
              Year: {filters.year}
              <X size={12} />
            </button>
          )}
          {filters.purpose && (
            <button
              onClick={() => toggleFilter('purpose', filters.purpose)}
              className="inline-flex items-center gap-1 px-2.5 py-1 bg-emerald-500/15 text-emerald-400 rounded-full text-xs font-medium hover:bg-emerald-500/25 transition-colors"
            >
              Purpose: {filters.purpose}
              <X size={12} />
            </button>
          )}
          <button
            onClick={clearFilters}
            className="ml-auto px-3 py-1.5 bg-red-500/15 text-red-400 rounded-lg text-sm font-medium hover:bg-red-500/25 transition-colors"
          >
            Clear Filters
          </button>
        </div>
      )}

      {/* Row 1: Purpose + Year + Pilot Pie */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Flights by Purpose - Horizontal Bar */}
        <ChartCard title="All Time Flights by Purpose">
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={purposeData} layout="vertical" margin={{ left: 80 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
              <XAxis type="number" stroke="var(--muted-fg)" fontSize={12} />
              <YAxis type="category" dataKey="purpose" stroke="var(--muted-fg)" fontSize={11} width={80} interval={0} />
              <Tooltip
                {...tooltipStyle}
                formatter={(val, name) => [val, name === 'total' ? 'Total' : 'Filtered']}
              />
              <Bar
                dataKey="total"
                shape={renderTotalBarH('#6366f1')}
                onClick={(data) => toggleFilter('purpose', data.purpose)}
                cursor="pointer"
              />
              {hasActiveFilter && (
                <Bar
                  dataKey="filtered"
                  shape={renderFilteredBarH('#6366f1')}
                />
              )}
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Flights Per Year - Vertical Bar */}
        <ChartCard title="Flights Per Year">
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={yearData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
              <XAxis dataKey="year" stroke="var(--muted-fg)" fontSize={12} />
              <YAxis stroke="var(--muted-fg)" fontSize={12} />
              <Tooltip
                {...tooltipStyle}
                formatter={(val, name) => [val, name === 'total' ? 'Total' : 'Filtered']}
              />
              <Bar
                dataKey="total"
                shape={renderTotalBar('#3b82f6')}
                onClick={(data) => toggleFilter('year', data.year)}
                cursor="pointer"
              />
              {hasActiveFilter && (
                <Bar
                  dataKey="filtered"
                  shape={renderFilteredBar('#3b82f6')}
                />
              )}
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Flights by Pilot - Pie/Donut with custom side legend (last names) */}
        <ChartCard title="Flights by Pilot">
          <div className="flex items-center gap-3">
            <div className="flex-1 min-w-0">
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={byPilot}
                    dataKey="count"
                    nameKey="pilot_name"
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={100}
                    labelLine={false}
                    onClick={(_, index) => toggleFilter('pilot', byPilot[index].pilot_id)}
                    cursor="pointer"
                  >
                    {byPilot.map((entry, i) => {
                      const isSelected = filters.pilot === entry.pilot_id
                      return (
                        <Cell
                          key={entry.pilot_id}
                          fill={pilotFill(entry.pilot_id, i)}
                          stroke={isSelected ? COLORS[i % COLORS.length] : 'none'}
                          strokeWidth={isSelected ? 3 : 0}
                        />
                      )
                    })}
                  </Pie>
                  <Tooltip
                    {...tooltipStyle}
                    formatter={(val, _name, item) => {
                      const pct = item?.payload?.percentage
                      const suffix = pct == null ? '' : ` (${pct}%)`
                      return [`${val}${suffix}`, item?.payload?.pilot_name ?? 'Flights']
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <ul className="shrink-0 w-28 max-h-[280px] overflow-y-auto pr-1 space-y-0.5 self-center">
              {byPilot.map((entry, i) => {
                const isSelected = filters.pilot === entry.pilot_id
                return (
                  <li key={entry.pilot_id}>
                    <button
                      type="button"
                      onClick={() => toggleFilter('pilot', entry.pilot_id)}
                      title={`${entry.pilot_name} - ${entry.percentage}%`}
                      className={`flex items-center gap-1.5 w-full text-left px-1 py-0.5 rounded text-[11px] transition-colors hover:bg-accent/50 ${
                        isSelected ? 'bg-accent/60 font-medium' : ''
                      }`}
                    >
                      <span
                        className="inline-block w-2 h-2 rounded-full shrink-0"
                        style={{ background: pilotFill(entry.pilot_id, i) }}
                      />
                      <span className="truncate text-foreground">{lastName(entry.pilot_name)}</span>
                    </button>
                  </li>
                )
              })}
            </ul>
          </div>
        </ChartCard>
      </div>

      {/* Row 2: Avg Duration + Monthly Trends */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Average Flight Duration by Year */}
        <ChartCard title="Average Flight Duration by Year">
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={durationData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
              <XAxis dataKey="year" stroke="var(--muted-fg)" fontSize={12} />
              <YAxis stroke="var(--muted-fg)" fontSize={12} />
              <Tooltip
                {...tooltipStyle}
                formatter={(val, name) => [
                  `${Math.round(val)}s`,
                  name === 'total' ? 'Total Avg' : 'Filtered Avg',
                ]}
              />
              <Bar
                dataKey="total"
                shape={renderTotalBar('#10b981')}
                onClick={(data) => toggleFilter('year', data.year)}
                cursor="pointer"
              />
              {hasActiveFilter && (
                <Bar
                  dataKey="filtered"
                  shape={renderFilteredBar('#10b981')}
                />
              )}
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Monthly Flight Trends - Line */}
        <ChartCard title="Monthly Flight Trends">
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={monthlyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
              <XAxis dataKey="label" stroke="var(--muted-fg)" fontSize={11} angle={-45} textAnchor="end" height={60} />
              <YAxis stroke="var(--muted-fg)" fontSize={12} />
              <Tooltip {...tooltipStyle} />
              <Line
                type="monotone"
                dataKey="total"
                stroke={hasActiveFilter ? withOpacity('#6366f1', DIM_OPACITY + 0.15) : '#6366f1'}
                strokeWidth={2}
                dot={{ r: 3 }}
                name="Total"
              />
              {hasActiveFilter && (
                <Line
                  type="monotone"
                  dataKey="filtered"
                  stroke="#6366f1"
                  strokeWidth={2.5}
                  dot={{ r: 4, fill: '#6366f1' }}
                  name="Filtered"
                />
              )}
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Row 3: Vehicle Hours + Pilot Leaderboard */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Top Vehicles by Hours - Horizontal Bar */}
        <ChartCard title="Top Vehicles by Flight Hours">
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={vehicleData} layout="vertical" margin={{ left: 100 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
              <XAxis type="number" stroke="var(--muted-fg)" fontSize={12} />
              <YAxis type="category" dataKey="vehicle_name" stroke="var(--muted-fg)" fontSize={11} width={100} />
              <Tooltip
                {...tooltipStyle}
                formatter={(val, name) => [
                  `${Number(val).toFixed(1)}h`,
                  name === 'total' ? 'Total' : 'Filtered',
                ]}
              />
              <Bar
                dataKey="total"
                shape={renderTotalBarH('#f59e0b')}
              />
              {hasActiveFilter && (
                <Bar
                  dataKey="filtered"
                  shape={renderFilteredBarH('#f59e0b')}
                />
              )}
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Pilot Hours Leaderboard - Table */}
        <ChartCard title="Pilot Hours Leaderboard">
          <div className="overflow-auto max-h-[300px]">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-2 text-muted-foreground font-medium">#</th>
                  <th className="text-left py-2 text-muted-foreground font-medium">Pilot</th>
                  <th className="text-right py-2 text-muted-foreground font-medium">Hours</th>
                  <th className="text-right py-2 text-muted-foreground font-medium">Flights</th>
                </tr>
              </thead>
              <tbody>
                {pilotHours.map((p, i) => {
                  const isSelected = filters.pilot === p.pilot_id
                  const hasFilteredData = filteredPilotHours?.[p.pilot_name]
                  const isDimmed = hasActiveFilter && !isSelected && !hasFilteredData
                  return (
                    <tr
                      key={p.pilot_id ?? p.pilot_name}
                      className={`border-b border-border/50 cursor-pointer transition-colors ${
                        isSelected
                          ? 'bg-indigo-500/15'
                          : 'hover:bg-accent/50'
                      }`}
                      style={{ opacity: isDimmed ? DIM_OPACITY + 0.15 : 1 }}
                      onClick={() => toggleFilter('pilot', p.pilot_id)}
                    >
                      <td className="py-2 text-muted-foreground">{i + 1}</td>
                      <td className="py-2 text-foreground font-medium">
                        {p.pilot_name}
                        {isSelected && (
                          <span className="ml-2 inline-block w-2 h-2 bg-indigo-500 rounded-full" />
                        )}
                      </td>
                      <td className="py-2 text-right text-foreground">
                        {p.hours.toFixed(1)}
                        {hasActiveFilter && filteredPilotHours?.[p.pilot_name] && (
                          <span className="text-indigo-400 ml-1 text-xs">
                            ({filteredPilotHours[p.pilot_name].hours.toFixed(1)})
                          </span>
                        )}
                      </td>
                      <td className="py-2 text-right text-muted-foreground">
                        {p.flight_count}
                        {hasActiveFilter && filteredPilotHours?.[p.pilot_name] && (
                          <span className="text-indigo-400 ml-1 text-xs">
                            ({filteredPilotHours[p.pilot_name].count})
                          </span>
                        )}
                      </td>
                    </tr>
                  )
                })}
                {pilotHours.length === 0 && (
                  <tr>
                    <td colSpan={4} className="py-8 text-center text-muted-foreground">
                      No flight data yet
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </ChartCard>
      </div>

      {allFlights.some(f => f.takeoff_lat) && (
        <div className="bg-card border border-border rounded-xl p-4">
          <h3 className="text-lg font-semibold text-foreground mb-3">Flight Locations</h3>
          <FlightLocationsMap flights={hasActiveFilter ? filteredFlights : allFlights} height="400px" />
        </div>
      )}
    </div>
  )
}
