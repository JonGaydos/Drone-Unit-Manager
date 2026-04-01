import { useState } from 'react'
import { api } from '@/api/client'
import { useToast } from '@/contexts/ToastContext'
import {
  CloudSun, MapPin, Wind, Thermometer, Droplets, Eye, Cloud,
  CheckCircle, AlertTriangle, XCircle, ChevronDown, ChevronUp,
  Navigation, Clock, Gauge
} from 'lucide-react'
import { LocationPickerMap } from '@/components/FlightMap'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts'

const WEATHER_CODES = {
  0: 'Clear sky', 1: 'Mainly clear', 2: 'Partly cloudy', 3: 'Overcast',
  45: 'Foggy', 48: 'Rime fog', 51: 'Light drizzle', 53: 'Moderate drizzle',
  55: 'Dense drizzle', 61: 'Slight rain', 63: 'Moderate rain', 65: 'Heavy rain',
  71: 'Slight snow', 73: 'Moderate snow', 75: 'Heavy snow', 77: 'Snow grains',
  80: 'Slight showers', 81: 'Moderate showers', 82: 'Violent showers',
  85: 'Slight snow showers', 86: 'Heavy snow showers',
  95: 'Thunderstorm', 96: 'Thunderstorm w/ slight hail', 99: 'Thunderstorm w/ heavy hail',
}

const STATUS_CONFIG = {
  go: { label: 'GO', color: 'bg-emerald-500', textColor: 'text-emerald-400', bgColor: 'bg-emerald-500/15', icon: CheckCircle },
  caution: { label: 'CAUTION', color: 'bg-amber-500', textColor: 'text-amber-400', bgColor: 'bg-amber-500/15', icon: AlertTriangle },
  no_go: { label: 'NO-GO', color: 'bg-red-500', textColor: 'text-red-400', bgColor: 'bg-red-500/15', icon: XCircle },
  unknown: { label: 'UNKNOWN', color: 'bg-zinc-500', textColor: 'text-zinc-400', bgColor: 'bg-zinc-500/15', icon: Cloud },
}

function windDirection(deg) {
  if (deg == null) return '--'
  const dirs = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
  return dirs[Math.round(deg / 22.5) % 16]
}

export default function WeatherPage() {
  const toast = useToast()
  const [coords, setCoords] = useState({ lat: '', lon: '' })
  const [addressInput, setAddressInput] = useState('')
  const [briefing, setBriefing] = useState(null)
  const [loading, setLoading] = useState(false)
  const [showMetar, setShowMetar] = useState(false)
  const [showTaf, setShowTaf] = useState(false)
  const [recentLocations, setRecentLocations] = useState(() => {
    try { return JSON.parse(localStorage.getItem('weather-recent-locations') || '[]') } catch { return [] }
  })

  const saveRecentLocation = (lat, lon, label) => {
    const entry = { lat, lon, label: label || `${lat.toFixed(4)}, ${lon.toFixed(4)}`, time: Date.now() }
    const updated = [entry, ...recentLocations.filter(r => !(Math.abs(r.lat - lat) < 0.001 && Math.abs(r.lon - lon) < 0.001))].slice(0, 8)
    setRecentLocations(updated)
    localStorage.setItem('weather-recent-locations', JSON.stringify(updated))
  }

  const fetchBriefing = async (lat, lon) => {
    if (!lat || !lon) { toast.error('Please enter coordinates or use your location'); return }
    setLoading(true)
    try {
      const data = await api.get(`/weather/briefing?lat=${lat}&lon=${lon}`)
      setBriefing(data)
      saveRecentLocation(Number.parseFloat(lat), Number.parseFloat(lon), addressInput || null)
    } catch (err) {
      toast.error(err.message)
    } finally {
      setLoading(false)
    }
  }

  const useMyLocation = () => {
    if (!navigator.geolocation) { toast.error('Geolocation not supported'); return }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const lat = pos.coords.latitude.toFixed(6)
        const lon = pos.coords.longitude.toFixed(6)
        setCoords({ lat, lon })
        setAddressInput('Current Location')
        fetchBriefing(lat, lon)
      },
      (err) => toast.error('Location access denied: ' + err.message),
      { enableHighAccuracy: true }
    )
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    // Try to parse address input as coordinates
    const parts = addressInput.trim().split(/[,\s]+/)
    if (parts.length >= 2) {
      const lat = Number.parseFloat(parts[0])
      const lon = Number.parseFloat(parts[1])
      if (!Number.isNaN(lat) && !Number.isNaN(lon) && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180) {
        setCoords({ lat: lat.toString(), lon: lon.toString() })
        fetchBriefing(lat, lon)
        return
      }
    }
    // Fall back to explicit coords
    if (coords.lat && coords.lon) {
      fetchBriefing(coords.lat, coords.lon)
    } else {
      toast.error('Enter coordinates as "lat, lon" (e.g. 40.7128, -74.0060)')
    }
  }

  const advisory = briefing?.advisory || { status: 'unknown', reasons: [] }
  const statusCfg = STATUS_CONFIG[advisory.status] || STATUS_CONFIG.unknown
  const StatusIcon = statusCfg.icon

  // Format forecast data for charts
  const forecastData = (briefing?.forecast || []).map(f => ({
    time: new Date(f.time).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }),
    'Wind (mph)': f.wind_mph,
    'Gusts (mph)': f.gusts_mph,
    'Temp (F)': f.temp_f,
    'Precip %': f.precip_prob,
    'Cloud %': f.cloud_cover,
  }))

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <CloudSun className="w-7 h-7 text-primary" />
        <h1 className="text-2xl font-bold text-foreground">Pre-Flight Weather Briefing</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Panel: Location Selector */}
        <div className="space-y-4">
          <div className="bg-card border border-border rounded-xl p-4 space-y-4">
            <h3 className="font-semibold text-foreground flex items-center gap-2">
              <MapPin className="w-4 h-4 text-primary" /> Location
            </h3>

            <form onSubmit={handleSubmit} className="space-y-3">
              <div>
                <label htmlFor="coordinates-or-address" className="block text-xs font-medium text-muted-foreground mb-1">Coordinates or Address</label>
                <input id="coordinates-or-address"
                  type="text"
                  value={addressInput}
                  onChange={e => setAddressInput(e.target.value)}
                  placeholder="40.7128, -74.0060"
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>

              <LocationPickerMap
                lat={coords.lat ? Number.parseFloat(coords.lat) : null}
                lon={coords.lon ? Number.parseFloat(coords.lon) : null}
                onSelect={(newLat, newLon) => setCoords({ lat: newLat.toFixed(6), lon: newLon.toFixed(6) })}
                height="250px"
              />

              <div className="grid grid-cols-2 gap-2 mt-2">
                <div>
                  <label htmlFor="latitude" className="block text-xs font-medium text-muted-foreground mb-1">Latitude</label>
                  <input id="latitude"
                    type="number" step="any" value={coords.lat}
                    onChange={e => setCoords({ ...coords, lat: e.target.value })}
                    placeholder="40.7128"
                    className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                </div>
                <div>
                  <label htmlFor="longitude" className="block text-xs font-medium text-muted-foreground mb-1">Longitude</label>
                  <input id="longitude"
                    type="number" step="any" value={coords.lon}
                    onChange={e => setCoords({ ...coords, lon: e.target.value })}
                    placeholder="-74.0060"
                    className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                </div>
              </div>

              <div className="flex gap-2">
                <button
                  type="submit"
                  disabled={loading}
                  className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50"
                >
                  {loading ? (
                    <div className="w-4 h-4 border-2 border-primary-foreground border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <CloudSun className="w-4 h-4" />
                  )}
                  Check Weather
                </button>
                <button
                  type="button"
                  onClick={useMyLocation}
                  className="flex items-center gap-1.5 px-3 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90"
                >
                  <Navigation className="w-4 h-4" /> GPS
                </button>
              </div>
            </form>
          </div>

          {/* Recent Locations */}
          {recentLocations.length > 0 && (
            <div className="bg-card border border-border rounded-xl p-4 space-y-2">
              <h4 className="text-sm font-medium text-muted-foreground">Recent Locations</h4>
              {recentLocations.map((loc) => (
                <button
                  key={`${loc.lat}-${loc.lon}`}
                  onClick={() => {
                    setCoords({ lat: loc.lat.toString(), lon: loc.lon.toString() })
                    setAddressInput(loc.label || '')
                    fetchBriefing(loc.lat, loc.lon)
                  }}
                  className="w-full text-left px-3 py-2 bg-secondary/50 hover:bg-secondary rounded-lg text-sm text-foreground transition-colors flex items-center gap-2"
                >
                  <MapPin className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                  <span className="truncate flex-1">{loc.label}</span>
                  <span className="text-xs text-muted-foreground shrink-0">{loc.lat.toFixed(2)}, {loc.lon.toFixed(2)}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Right Panel: Weather Briefing Results */}
        <div className="lg:col-span-2 space-y-4">
          {!briefing && !loading && (
            <div className="bg-card border border-border rounded-xl p-12 text-center">
              <CloudSun className="w-12 h-12 text-muted-foreground mx-auto mb-4 opacity-50" />
              <p className="text-muted-foreground">Enter coordinates or use your GPS to get a weather briefing</p>
            </div>
          )}

          {loading && (
            <div className="bg-card border border-border rounded-xl p-12 text-center">
              <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-4" />
              <p className="text-muted-foreground">Fetching weather data...</p>
            </div>
          )}

          {briefing && !loading && (
            <>
              {/* Advisory Badge */}
              <div className={`${statusCfg.bgColor} border border-border rounded-xl p-6`}>
                <div className="flex items-center gap-4">
                  <div className={`w-16 h-16 ${statusCfg.color} rounded-2xl flex items-center justify-center`}>
                    <StatusIcon className="w-8 h-8 text-white" />
                  </div>
                  <div className="flex-1">
                    <h2 className={`text-3xl font-bold ${statusCfg.textColor}`}>{statusCfg.label}</h2>
                    <p className="text-sm text-muted-foreground mt-1">Flight Operations Advisory</p>
                  </div>
                </div>
                <div className="mt-4 space-y-1.5">
                  {advisory.reasons.map((r) => (
                    <div key={r} className="flex items-start gap-2 text-sm">
                      <span className={`mt-0.5 w-1.5 h-1.5 rounded-full shrink-0 ${statusCfg.color}`} />
                      <span className="text-foreground">{r}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Current Conditions */}
              <div className="bg-card border border-border rounded-xl overflow-hidden">
                <div className="px-4 py-3 border-b border-border">
                  <h3 className="font-semibold text-foreground">Current Conditions</h3>
                </div>
                <div className="p-4 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
                  {/* Wind */}
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-blue-500/15 flex items-center justify-center text-blue-400">
                      <Wind className="w-5 h-5" />
                    </div>
                    <div>
                      <p className="text-lg font-bold text-foreground">
                        {briefing.local_weather?.wind_speed_mph?.toFixed(0) ?? briefing.metar?.wind_speed_kt ?? '--'} {briefing.local_weather?.wind_speed_mph == null ? 'kt' : 'mph'}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Wind {windDirection(briefing.local_weather?.wind_direction_deg ?? briefing.metar?.wind_dir_deg)}
                      </p>
                    </div>
                  </div>

                  {/* Gusts */}
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-orange-500/15 flex items-center justify-center text-orange-400">
                      <Gauge className="w-5 h-5" />
                    </div>
                    <div>
                      <p className="text-lg font-bold text-foreground">
                        {briefing.local_weather?.wind_gusts_mph?.toFixed(0) ?? briefing.metar?.wind_gust_kt ?? '--'} {briefing.local_weather?.wind_gusts_mph == null ? 'kt' : 'mph'}
                      </p>
                      <p className="text-xs text-muted-foreground">Gusts</p>
                    </div>
                  </div>

                  {/* Temperature */}
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-red-500/15 flex items-center justify-center text-red-400">
                      <Thermometer className="w-5 h-5" />
                    </div>
                    <div>
                      <p className="text-lg font-bold text-foreground">
                        {briefing.local_weather?.temperature_f?.toFixed(0) ?? '--'}°F
                      </p>
                      <p className="text-xs text-muted-foreground">Temperature</p>
                    </div>
                  </div>

                  {/* Humidity */}
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-cyan-500/15 flex items-center justify-center text-cyan-400">
                      <Droplets className="w-5 h-5" />
                    </div>
                    <div>
                      <p className="text-lg font-bold text-foreground">
                        {briefing.local_weather?.humidity_pct ?? '--'}%
                      </p>
                      <p className="text-xs text-muted-foreground">Humidity</p>
                    </div>
                  </div>

                  {/* Visibility */}
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-purple-500/15 flex items-center justify-center text-purple-400">
                      <Eye className="w-5 h-5" />
                    </div>
                    <div>
                      <p className="text-lg font-bold text-foreground">
                        {briefing.metar?.visibility_miles ?? '--'} mi
                      </p>
                      <p className="text-xs text-muted-foreground">Visibility</p>
                    </div>
                  </div>

                  {/* Ceiling */}
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-indigo-500/15 flex items-center justify-center text-indigo-400">
                      <Cloud className="w-5 h-5" />
                    </div>
                    <div>
                      <p className="text-lg font-bold text-foreground">
                        {briefing.metar?.ceiling_ft ?? '--'} ft
                      </p>
                      <p className="text-xs text-muted-foreground">Ceiling AGL</p>
                    </div>
                  </div>

                  {/* Flight Category */}
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-emerald-500/15 flex items-center justify-center text-emerald-400">
                      <CheckCircle className="w-5 h-5" />
                    </div>
                    <div>
                      <p className={`text-lg font-bold ${
                        { VFR: 'text-emerald-400', MVFR: 'text-blue-400', IFR: 'text-red-400', LIFR: 'text-fuchsia-400' }[briefing.metar?.flight_category] || 'text-foreground'
                      }`}>
                        {briefing.metar?.flight_category ?? '--'}
                      </p>
                      <p className="text-xs text-muted-foreground">Flight Category</p>
                    </div>
                  </div>

                  {/* Precipitation */}
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-sky-500/15 flex items-center justify-center text-sky-400">
                      <Droplets className="w-5 h-5" />
                    </div>
                    <div>
                      <p className="text-lg font-bold text-foreground">
                        {briefing.local_weather?.precipitation_in?.toFixed(2) ?? '--'} in
                      </p>
                      <p className="text-xs text-muted-foreground">Precipitation</p>
                    </div>
                  </div>
                </div>

                {/* Weather description */}
                {briefing.local_weather?.weather_code != null && (
                  <div className="px-4 pb-3 text-sm text-muted-foreground">
                    Conditions: {WEATHER_CODES[briefing.local_weather.weather_code] || `Code ${briefing.local_weather.weather_code}`}
                    {briefing.metar?.wx_string && ` | METAR Wx: ${briefing.metar.wx_string}`}
                  </div>
                )}
              </div>

              {/* Station Info */}
              {briefing.station && (
                <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
                  <MapPin className="w-5 h-5 text-primary shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-foreground">
                      Nearest METAR Station: {briefing.station.id} - {briefing.station.name}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {briefing.station.distance_miles} miles away | {briefing.station.lat?.toFixed(4)}, {briefing.station.lon?.toFixed(4)}
                    </p>
                  </div>
                </div>
              )}

              {/* Forecast Charts */}
              {forecastData.length > 0 && (
                <div className="bg-card border border-border rounded-xl overflow-hidden">
                  <div className="px-4 py-3 border-b border-border">
                    <h3 className="font-semibold text-foreground flex items-center gap-2">
                      <Clock className="w-4 h-4 text-primary" /> 12-Hour Forecast
                    </h3>
                  </div>
                  <div className="p-4 space-y-6">
                    {/* Wind Chart */}
                    <div>
                      <p className="text-xs font-medium text-muted-foreground mb-2">Wind Speed & Gusts (mph)</p>
                      <div className="h-48">
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={forecastData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border, #333)" />
                            <XAxis dataKey="time" tick={{ fontSize: 11, fill: 'var(--color-muted-foreground, #888)' }} />
                            <YAxis tick={{ fontSize: 11, fill: 'var(--color-muted-foreground, #888)' }} />
                            <Tooltip
                              contentStyle={{
                                backgroundColor: 'var(--color-card, #1a1a2e)',
                                border: '1px solid var(--color-border, #333)',
                                borderRadius: '8px',
                                fontSize: '12px',
                              }}
                            />
                            <Legend wrapperStyle={{ fontSize: '12px' }} />
                            <Line type="monotone" dataKey="Wind (mph)" stroke="#3b82f6" strokeWidth={2} dot={false} />
                            <Line type="monotone" dataKey="Gusts (mph)" stroke="#f97316" strokeWidth={2} dot={false} strokeDasharray="5 5" />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>

                    {/* Temperature & Precipitation */}
                    <div>
                      <p className="text-xs font-medium text-muted-foreground mb-2">Temperature & Precipitation Probability</p>
                      <div className="h-48">
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={forecastData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border, #333)" />
                            <XAxis dataKey="time" tick={{ fontSize: 11, fill: 'var(--color-muted-foreground, #888)' }} />
                            <YAxis yAxisId="left" tick={{ fontSize: 11, fill: 'var(--color-muted-foreground, #888)' }} />
                            <YAxis yAxisId="right" orientation="right" domain={[0, 100]} tick={{ fontSize: 11, fill: 'var(--color-muted-foreground, #888)' }} />
                            <Tooltip
                              contentStyle={{
                                backgroundColor: 'var(--color-card, #1a1a2e)',
                                border: '1px solid var(--color-border, #333)',
                                borderRadius: '8px',
                                fontSize: '12px',
                              }}
                            />
                            <Legend wrapperStyle={{ fontSize: '12px' }} />
                            <Line yAxisId="left" type="monotone" dataKey="Temp (F)" stroke="#ef4444" strokeWidth={2} dot={false} />
                            <Line yAxisId="right" type="monotone" dataKey="Precip %" stroke="#06b6d4" strokeWidth={2} dot={false} />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  </div>

                  {/* Forecast Timeline Cards */}
                  <div className="px-4 pb-4">
                    <p className="text-xs font-medium text-muted-foreground mb-2">Hourly Detail</p>
                    <div className="flex gap-2 overflow-x-auto pb-2">
                      {(briefing.forecast || []).map((f) => (
                        <div key={f.time} className="shrink-0 w-28 bg-secondary/50 rounded-lg p-3 text-center">
                          <p className="text-xs font-medium text-foreground">
                            {new Date(f.time).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}
                          </p>
                          <p className="text-lg font-bold text-foreground mt-1">{f.temp_f?.toFixed(0) ?? '--'}°</p>
                          <div className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                            <p>Wind {f.wind_mph?.toFixed(0) ?? '--'}</p>
                            {f.gusts_mph > 0 && <p>Gust {f.gusts_mph?.toFixed(0)}</p>}
                            <p>Precip {f.precip_prob ?? 0}%</p>
                            <p>Cloud {f.cloud_cover ?? 0}%</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* Raw METAR / TAF */}
              {briefing.metar?.raw && (
                <div className="bg-card border border-border rounded-xl overflow-hidden">
                  <button
                    onClick={() => setShowMetar(!showMetar)}
                    className="w-full px-4 py-3 flex items-center justify-between hover:bg-accent/30 transition-colors"
                  >
                    <span className="font-semibold text-foreground text-sm">Raw METAR</span>
                    {showMetar ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
                  </button>
                  {showMetar && (
                    <div className="px-4 pb-4">
                      <pre className="bg-secondary/50 p-3 rounded-lg text-xs text-foreground font-mono whitespace-pre-wrap break-all">
                        {briefing.metar.raw}
                      </pre>
                      {briefing.metar.observation_time && (
                        <p className="text-xs text-muted-foreground mt-2">Observed: {briefing.metar.observation_time}</p>
                      )}
                    </div>
                  )}
                </div>
              )}

              {briefing.taf?.raw && (
                <div className="bg-card border border-border rounded-xl overflow-hidden">
                  <button
                    onClick={() => setShowTaf(!showTaf)}
                    className="w-full px-4 py-3 flex items-center justify-between hover:bg-accent/30 transition-colors"
                  >
                    <span className="font-semibold text-foreground text-sm">Raw TAF (Terminal Forecast)</span>
                    {showTaf ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
                  </button>
                  {showTaf && (
                    <div className="px-4 pb-4">
                      <pre className="bg-secondary/50 p-3 rounded-lg text-xs text-foreground font-mono whitespace-pre-wrap break-all">
                        {briefing.taf.raw}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
