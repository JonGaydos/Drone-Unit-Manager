import { useState, useEffect, useMemo, useCallback } from 'react'
import { api } from '@/api/client'
import { X, Filter } from 'lucide-react'
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'

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
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r}, ${g}, ${b}, ${opacity})`
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
      api.get('/flights?per_page=1000'),
    ]).then(([purpose, year, pilot, dur, mon, veh, pil, flights]) => {
      setByPurpose(purpose)
      setByYear(year)
      setByPilot(pilot)
      setAvgDuration(dur)
      setMonthly(mon.map(m => ({ ...m, label: `${m.year}-${String(m.month).padStart(2, '0')}` })))
      setVehicleHours(veh)
      setPilotHours(pil)
      // Handle paginated or raw array response
      setAllFlights(Array.isArray(flights) ? flights : flights.flights || flights.items || flights.data || [])
    }).catch(console.error).finally(() => setLoading(false))
  }, [])

  // Compute filtered subsets from allFlights when filters change
  const filteredFlights = useMemo(() => {
    if (!hasActiveFilter) return allFlights
    return allFlights.filter(f => {
      if (filters.pilot && f.pilot_name !== filters.pilot) return false
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
      counts[f.pilot_name] = (counts[f.pilot_name] || 0) + 1
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

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  // Custom bar shape for overlapping bars (filtered on top of dimmed total)
  const renderTotalBar = (color) => (props) => {
    const { x, y, width, height } = props
    if (!height || height <= 0) return null
    return (
      <rect
        x={x} y={y} width={width} height={height}
        fill={hasActiveFilter ? withOpacity(color, DIM_OPACITY) : color}
        rx={4} ry={4}
      />
    )
  }

  const renderFilteredBar = (color) => (props) => {
    const { x, y, width, height } = props
    if (!height || height <= 0) return null
    return (
      <rect x={x} y={y} width={width} height={height} fill={color} rx={4} ry={4} />
    )
  }

  // Horizontal bar shape variants
  const renderTotalBarH = (color) => (props) => {
    const { x, y, width, height } = props
    if (!width || width <= 0) return null
    return (
      <rect
        x={x} y={y} width={width} height={height}
        fill={hasActiveFilter ? withOpacity(color, DIM_OPACITY) : color}
        rx={4} ry={4}
      />
    )
  }

  const renderFilteredBarH = (color) => (props) => {
    const { x, y, width, height } = props
    if (!width || width <= 0) return null
    return (
      <rect x={x} y={y} width={width} height={height} fill={color} rx={4} ry={4} />
    )
  }

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
              Pilot: {filters.pilot}
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
            className="ml-auto text-xs text-muted-foreground hover:text-foreground transition-colors underline"
          >
            Clear all
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
              <YAxis type="category" dataKey="purpose" stroke="var(--muted-fg)" fontSize={11} width={80} />
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

        {/* Flights by Pilot - Pie/Donut */}
        <ChartCard title="Flights by Pilot">
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
                label={({ pilot_name, percentage }) => `${pilot_name.split(' ')[0]} ${percentage}%`}
                labelLine={false}
                fontSize={11}
                onClick={(_, index) => toggleFilter('pilot', byPilot[index].pilot_name)}
                cursor="pointer"
              >
                {byPilot.map((entry, i) => {
                  const isSelected = filters.pilot === entry.pilot_name
                  const baseColor = COLORS[i % COLORS.length]
                  let fillColor = baseColor
                  if (hasActiveFilter) {
                    const hasFilteredFlights = filteredByPilot && (filteredByPilot[entry.pilot_name] || 0) > 0
                    if (!hasFilteredFlights) {
                      fillColor = withOpacity(baseColor, DIM_OPACITY)
                    }
                  }
                  return (
                    <Cell
                      key={i}
                      fill={fillColor}
                      stroke={isSelected ? baseColor : 'none'}
                      strokeWidth={isSelected ? 3 : 0}
                    />
                  )
                })}
              </Pie>
              <Tooltip {...tooltipStyle} />
            </PieChart>
          </ResponsiveContainer>
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
                  const isSelected = filters.pilot === p.pilot_name
                  const hasFilteredData = filteredPilotHours && filteredPilotHours[p.pilot_name]
                  const isDimmed = hasActiveFilter && !isSelected && !hasFilteredData
                  return (
                    <tr
                      key={i}
                      className={`border-b border-border/50 cursor-pointer transition-colors ${
                        isSelected
                          ? 'bg-indigo-500/15'
                          : 'hover:bg-accent/50'
                      }`}
                      style={{ opacity: isDimmed ? DIM_OPACITY + 0.15 : 1 }}
                      onClick={() => toggleFilter('pilot', p.pilot_name)}
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
    </div>
  )
}
