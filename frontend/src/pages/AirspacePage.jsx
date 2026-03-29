/**
 * Live ADS-B aircraft map page showing nearby aircraft positions
 * fetched from the airplanes.live API via the backend proxy.
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet'
import L from 'leaflet'
import { api } from '@/api/client'
import { useToast } from '@/contexts/ToastContext'
import { Radar, MapPin, RefreshCw, Locate, Plane } from 'lucide-react'

/** Default center (center of US) used when no settings or geolocation available. */
const DEFAULT_CENTER = [39.8, -98.5]

const RADIUS_OPTIONS = [5, 10, 20, 30, 50, 100]
const INTERVAL_OPTIONS = [
  { label: '5s', value: 5000 },
  { label: '10s', value: 10000 },
  { label: '15s', value: 15000 },
  { label: '30s', value: 30000 },
  { label: 'Off', value: 0 },
]

/** Altitude color bands for aircraft markers. */
const ALT_BANDS = [
  { max: 400, color: '#ef4444', label: 'Below 400 ft (Drone Zone)' },
  { max: 1000, color: '#f97316', label: '400 - 1,000 ft' },
  { max: 5000, color: '#eab308', label: '1,000 - 5,000 ft' },
  { max: 15000, color: '#3b82f6', label: '5,000 - 15,000 ft' },
  { max: Infinity, color: '#6b7280', label: 'Above 15,000 ft / Unknown' },
]

/**
 * Get the color for an aircraft based on its barometric altitude.
 * @param {number|string|null} altBaro - Altitude in feet, or "ground", or null.
 * @returns {string} Hex color string.
 */
function getAltColor(altBaro) {
  if (altBaro == null || altBaro === 'ground') return '#6b7280'
  const alt = typeof altBaro === 'string' ? parseInt(altBaro, 10) : altBaro
  if (isNaN(alt)) return '#6b7280'
  for (const band of ALT_BANDS) {
    if (alt < band.max) return band.color
  }
  return '#6b7280'
}

/**
 * Create a Leaflet divIcon with a rotated airplane SVG.
 * @param {number} track - Heading in degrees.
 * @param {string} color - Fill color hex.
 * @returns {L.DivIcon}
 */
function aircraftIcon(track, color) {
  const rotation = track != null ? track : 0
  return L.divIcon({
    className: '',
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    popupAnchor: [0, -14],
    html: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" style="transform:rotate(${rotation}deg)">
      <path d="M12 2L8 9h-5l1 2 5 1 1 8 2 2 2-2 1-8 5-1 1-2h-5z" fill="${color}" stroke="#000" stroke-width="0.5"/>
    </svg>`,
  })
}

/**
 * Helper component to recenter the map when center coordinates change.
 */
function RecenterMap({ center }) {
  const map = useMap()
  useEffect(() => {
    if (center && center[0] && center[1]) {
      map.setView(center, map.getZoom())
    }
  }, [center[0], center[1]])
  return null
}

/**
 * Format altitude for display.
 * @param {number|string|null} alt
 * @returns {string}
 */
function fmtAlt(alt) {
  if (alt == null) return '--'
  if (alt === 'ground') return 'Ground'
  return typeof alt === 'number' ? alt.toLocaleString() + ' ft' : alt + ' ft'
}

export default function AirspacePage() {
  const toast = useToast()

  // Load saved settings from localStorage
  const saved = (() => {
    try { return JSON.parse(localStorage.getItem('airspace-settings') || '{}') } catch { return {} }
  })()

  const [lat, setLat] = useState(saved.lat || '')
  const [lon, setLon] = useState(saved.lon || '')
  const [radius, setRadius] = useState(saved.radius || 30)
  const [interval, setInterval_] = useState(saved.interval ?? 10000)
  const [aircraft, setAircraft] = useState([])
  const [loading, setLoading] = useState(false)
  const [cached, setCached] = useState(false)
  const [lastFetch, setLastFetch] = useState(null)
  const [mapCenter, setMapCenter] = useState(DEFAULT_CENTER)
  const intervalRef = useRef(null)
  const initialLoadDone = useRef(false)

  // Save settings to localStorage whenever they change
  useEffect(() => {
    if (lat && lon) {
      localStorage.setItem('airspace-settings', JSON.stringify({ lat, lon, radius, interval }))
    }
  }, [lat, lon, radius, interval])

  // Load default location from app settings on mount
  useEffect(() => {
    api.get('/settings').then(settings => {
      const get = (key) => {
        const s = settings.find(s => s.key === key)
        return s ? s.value : null
      }
      // Use saved lat/lon first, then settings, then default
      if (!lat && !lon) {
        const wLat = get('weather_location_lat') || get('adsb_default_lat')
        const wLon = get('weather_location_lon') || get('adsb_default_lon')
        if (wLat && wLon) {
          setLat(wLat)
          setLon(wLon)
          setMapCenter([parseFloat(wLat), parseFloat(wLon)])
        }
      } else if (lat && lon) {
        setMapCenter([parseFloat(lat), parseFloat(lon)])
      }
    }).catch(() => {})
  }, [])

  const fetchAircraft = useCallback(async (fetchLat, fetchLon) => {
    const useLat = fetchLat || lat
    const useLon = fetchLon || lon
    if (!useLat || !useLon) return

    setLoading(true)
    try {
      const data = await api.get(`/adsb/nearby?lat=${useLat}&lon=${useLon}&radius_nm=${radius}`)
      setAircraft(data.aircraft || [])
      setCached(data.cached || false)
      setLastFetch(new Date())
    } catch (err) {
      toast.error('Failed to fetch aircraft: ' + err.message)
    } finally {
      setLoading(false)
    }
  }, [lat, lon, radius, toast])

  // Auto-refresh interval
  useEffect(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
    if (interval > 0 && lat && lon) {
      // Do initial fetch if not done yet
      if (!initialLoadDone.current) {
        initialLoadDone.current = true
        fetchAircraft()
      }
      intervalRef.current = setInterval(() => fetchAircraft(), interval)
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [interval, fetchAircraft])

  // Initial fetch when lat/lon first become available
  useEffect(() => {
    if (lat && lon && !initialLoadDone.current) {
      initialLoadDone.current = true
      fetchAircraft()
    }
  }, [lat, lon])

  const useMyLocation = () => {
    if (!navigator.geolocation) { toast.error('Geolocation not supported'); return }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const newLat = pos.coords.latitude.toFixed(6)
        const newLon = pos.coords.longitude.toFixed(6)
        setLat(newLat)
        setLon(newLon)
        setMapCenter([parseFloat(newLat), parseFloat(newLon)])
        initialLoadDone.current = true
        fetchAircraft(newLat, newLon)
      },
      (err) => toast.error('Location access denied: ' + err.message),
      { enableHighAccuracy: true }
    )
  }

  const handleManualRefresh = () => {
    if (lat && lon) {
      setMapCenter([parseFloat(lat), parseFloat(lon)])
      fetchAircraft()
    } else {
      toast.error('Enter coordinates or use your location first')
    }
  }

  return (
    <div className="space-y-4">
      {/* Control Bar */}
      <div className="bg-card border border-border rounded-xl p-4">
        <div className="flex flex-wrap items-end gap-3">
          {/* Lat */}
          <div className="min-w-[120px]">
            <label className="block text-xs font-medium text-muted-foreground mb-1">Latitude</label>
            <input
              type="number"
              step="any"
              value={lat}
              onChange={e => setLat(e.target.value)}
              placeholder="39.8"
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          {/* Lon */}
          <div className="min-w-[120px]">
            <label className="block text-xs font-medium text-muted-foreground mb-1">Longitude</label>
            <input
              type="number"
              step="any"
              value={lon}
              onChange={e => setLon(e.target.value)}
              placeholder="-98.5"
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          {/* Radius */}
          <div className="min-w-[100px]">
            <label className="block text-xs font-medium text-muted-foreground mb-1">Radius (NM)</label>
            <select
              value={radius}
              onChange={e => setRadius(Number(e.target.value))}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            >
              {RADIUS_OPTIONS.map(r => (
                <option key={r} value={r}>{r} NM</option>
              ))}
            </select>
          </div>
          {/* Refresh Interval */}
          <div className="min-w-[100px]">
            <label className="block text-xs font-medium text-muted-foreground mb-1">Refresh</label>
            <select
              value={interval}
              onChange={e => setInterval_(Number(e.target.value))}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            >
              {INTERVAL_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          {/* Buttons */}
          <button
            onClick={useMyLocation}
            className="flex items-center gap-1.5 px-3 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90"
            title="Use my GPS location"
          >
            <Locate className="w-4 h-4" /> My Location
          </button>
          <button
            onClick={handleManualRefresh}
            disabled={loading}
            className="flex items-center gap-1.5 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50"
          >
            {loading ? (
              <div className="w-4 h-4 border-2 border-primary-foreground border-t-transparent rounded-full animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
            Refresh
          </button>
          {/* Aircraft Count */}
          <div className="flex items-center gap-2 ml-auto text-sm text-muted-foreground">
            <Plane className="w-4 h-4" />
            <span className="font-medium text-foreground">{aircraft.length}</span> aircraft
            {cached && <span className="text-xs">(cached)</span>}
            {lastFetch && (
              <span className="text-xs">
                @ {lastFetch.toLocaleTimeString()}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Map */}
      <div className="relative" style={{ height: 'calc(100vh - 250px)', minHeight: '400px' }}>
        <div className="rounded-xl overflow-hidden border border-border h-full relative z-0">
          <MapContainer
            center={mapCenter}
            zoom={10}
            style={{ height: '100%', width: '100%' }}
            scrollWheelZoom={true}
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            <RecenterMap center={mapCenter} />
            {aircraft.map(ac => (
              <Marker
                key={ac.icao}
                position={[ac.lat, ac.lon]}
                icon={aircraftIcon(ac.track, getAltColor(ac.alt_baro))}
              >
                <Popup>
                  <div className="text-xs space-y-1 min-w-[180px]">
                    <div className="font-bold text-sm">
                      {ac.callsign || ac.icao || 'Unknown'}
                    </div>
                    <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
                      <span className="text-gray-500">ICAO:</span>
                      <span>{ac.icao || '--'}</span>
                      <span className="text-gray-500">Type:</span>
                      <span>{ac.aircraft_type || '--'}</span>
                      <span className="text-gray-500">Reg:</span>
                      <span>{ac.registration || '--'}</span>
                      <span className="text-gray-500">Altitude:</span>
                      <span>{fmtAlt(ac.alt_baro)}</span>
                      <span className="text-gray-500">Speed:</span>
                      <span>{ac.gs != null ? ac.gs + ' kts' : '--'}</span>
                      <span className="text-gray-500">Heading:</span>
                      <span>{ac.track != null ? ac.track + '\u00B0' : '--'}</span>
                      <span className="text-gray-500">Vert Rate:</span>
                      <span>{ac.baro_rate != null ? ac.baro_rate + ' ft/m' : '--'}</span>
                      <span className="text-gray-500">Squawk:</span>
                      <span>{ac.squawk || '--'}</span>
                    </div>
                    {ac.emergency && ac.emergency !== 'none' && (
                      <div className="text-red-600 font-bold mt-1">
                        EMERGENCY: {ac.emergency}
                      </div>
                    )}
                  </div>
                </Popup>
              </Marker>
            ))}
          </MapContainer>
        </div>

        {/* Legend */}
        <div className="absolute bottom-4 right-4 bg-card/90 backdrop-blur border border-border rounded-lg p-3 z-[1000]">
          <p className="text-xs font-medium text-foreground mb-2">Altitude</p>
          {ALT_BANDS.map(band => (
            <div key={band.label} className="flex items-center gap-2 text-xs text-muted-foreground">
              <span
                className="w-3 h-3 rounded-sm shrink-0"
                style={{ backgroundColor: band.color }}
              />
              <span>{band.label}</span>
            </div>
          ))}
        </div>

        {/* Loading overlay */}
        {loading && aircraft.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/50 rounded-xl z-[1000]">
            <div className="bg-card border border-border rounded-xl p-8 text-center">
              <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-3" />
              <p className="text-sm text-muted-foreground">Fetching aircraft data...</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
