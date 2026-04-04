/**
 * Live ADS-B aircraft map page showing nearby aircraft positions.
 * Click anywhere on the map to set your location and search radius.
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { MapContainer, TileLayer, Marker, Popup, Circle, useMap, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import { api } from '@/api/client'
import { useToast } from '@/contexts/ToastContext'
import { Radar, RefreshCw, Plane, MapPin } from 'lucide-react'

/** Default center (center of US) used when no settings available. */
const DEFAULT_CENTER = [39.8, -98.5]

/** Radius options in miles — converted to nautical miles for the API. */
const RADIUS_OPTIONS = [25, 50, 100, 150, 200]
const MILES_TO_NM = 0.868976
const MILES_TO_METERS = 1609.34

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

function getAltColor(altBaro) {
  if (altBaro == null || altBaro === 'ground') return '#6b7280'
  const alt = typeof altBaro === 'string' ? Number.parseInt(altBaro, 10) : altBaro
  if (Number.isNaN(alt)) return '#6b7280'
  for (const band of ALT_BANDS) {
    if (alt < band.max) return band.color
  }
  return '#6b7280'
}

function aircraftIcon(track, color) {
  const rotation = track == null ? 0 : track
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

function fmtAlt(alt) {
  if (alt == null) return '--'
  if (alt === 'ground') return 'Ground'
  return typeof alt === 'number' ? alt.toLocaleString() + ' ft' : alt + ' ft'
}

/** Click handler component — captures map clicks to set the search center. */
function MapClickHandler({ onMapClick }) {
  useMapEvents({
    click(e) {
      onMapClick(e.latlng.lat, e.latlng.lng)
    },
  })
  return null
}

/** Recenter the map when the center prop changes. */
function RecenterMap({ center, zoom }) {
  const map = useMap()
  useEffect(() => {
    if (center?.[0] && center?.[1]) {
      map.setView(center, zoom || map.getZoom())
    }
  }, [center[0], center[1]])
  return null
}

export default function AirspacePage() {
  const toast = useToast()

  const saved = (() => {
    try { return JSON.parse(localStorage.getItem('airspace-settings') || '{}') } catch { return {} }
  })()

  const [selectedPoint, setSelectedPoint] = useState(
    saved.lat && saved.lon ? [saved.lat, saved.lon] : null
  )
  const [radius, setRadius] = useState(saved.radius || 100)
  const [refreshInterval, setRefreshInterval] = useState(saved.refreshInterval ?? 10000)
  const [aircraft, setAircraft] = useState([])
  const [loading, setLoading] = useState(false)
  const [cached, setCached] = useState(false)
  const [lastFetch, setLastFetch] = useState(null)
  const [mapCenter, setMapCenter] = useState(
    saved.lat && saved.lon ? [saved.lat, saved.lon] : DEFAULT_CENTER
  )
  const intervalRef = useRef(null)

  // Save settings to localStorage
  useEffect(() => {
    if (selectedPoint) {
      localStorage.setItem('airspace-settings', JSON.stringify({
        lat: selectedPoint[0], lon: selectedPoint[1], radius, refreshInterval
      }))
    }
  }, [selectedPoint, radius, refreshInterval])

  // Load default location from app settings on mount (only if no saved point)
  const applyDefaultLocation = useCallback((settings) => {
    const find = (key) => settings.find(s => s.key === key)?.value ?? null
    const lat = find('adsb_default_lat') || find('weather_location_lat')
    const lon = find('adsb_default_lon') || find('weather_location_lon')
    if (lat && lon) setMapCenter([Number.parseFloat(lat), Number.parseFloat(lon)])
  }, [])

  useEffect(() => {
    if (selectedPoint) return
    api.get('/settings').then(applyDefaultLocation).catch(() => {})
  }, [])

  const fetchAircraft = useCallback(async (point, manual = false) => {
    const p = point || selectedPoint
    if (!p) return
    const radiusNm = Math.round(radius * MILES_TO_NM)

    setLoading(true)
    try {
      const data = await api.get(`/adsb/nearby?lat=${p[0]}&lon=${p[1]}&radius_nm=${radiusNm}`)
      setAircraft(data.aircraft || [])
      setCached(data.cached || false)
      setLastFetch(new Date())
    } catch (err) {
      // Only show error toast on manual refresh — silent retry on auto-refresh
      if (manual) toast.error('Failed to fetch aircraft: ' + err.message)
      else console.warn('ADS-B auto-refresh failed:', err.message)
    } finally {
      setLoading(false)
    }
  }, [selectedPoint, radius, toast])

  // Auto-refresh interval
  useEffect(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
    if (refreshInterval > 0 && selectedPoint) {
      intervalRef.current = setInterval(() => fetchAircraft(), refreshInterval)
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [refreshInterval, fetchAircraft, selectedPoint])

  const handleMapClick = (lat, lng) => {
    const point = [lat, lng]
    setSelectedPoint(point)
    setMapCenter(point)
    fetchAircraft(point, true)
  }

  return (
    <div className="space-y-4">
      {/* Control Bar */}
      <div className="bg-card border border-border rounded-xl p-4">
        <div className="flex flex-wrap items-center gap-4">
          {/* Instructions or selected location */}
          <div className="flex items-center gap-2 text-sm min-w-0">
            <MapPin className="w-4 h-4 text-primary shrink-0" />
            {selectedPoint ? (
              <span className="text-foreground">
                {selectedPoint[0].toFixed(4)}, {selectedPoint[1].toFixed(4)}
              </span>
            ) : (
              <span className="text-muted-foreground">Click anywhere on the map to set your location</span>
            )}
          </div>

          {/* Radius */}
          <div className="flex items-center gap-2">
            <label htmlFor="radius" className="text-xs font-medium text-muted-foreground">Radius</label>
            <select id="radius"
              value={radius}
              onChange={e => setRadius(Number(e.target.value))}
              className="px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            >
              {RADIUS_OPTIONS.map(r => (
                <option key={r} value={r}>{r} miles</option>
              ))}
            </select>
          </div>

          {/* Refresh Interval */}
          <div className="flex items-center gap-2">
            <label htmlFor="refresh" className="text-xs font-medium text-muted-foreground">Refresh</label>
            <select id="refresh"
              value={refreshInterval}
              onChange={e => setRefreshInterval(Number(e.target.value))}
              className="px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            >
              {INTERVAL_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          {/* Refresh Button */}
          <button
            onClick={() => fetchAircraft(null, true)}
            disabled={loading || !selectedPoint}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50"
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
            {lastFetch && <span className="text-xs">@ {lastFetch.toLocaleTimeString()}</span>}
          </div>
        </div>
      </div>

      {/* Map */}
      <div className="relative" style={{ height: 'calc(100vh - 230px)', minHeight: '400px' }}>
        <div className="rounded-xl overflow-hidden border border-border h-full relative z-0">
          <MapContainer
            center={mapCenter}
            zoom={8}
            style={{ height: '100%', width: '100%' }}
            scrollWheelZoom={true}
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            <RecenterMap center={mapCenter} />
            <MapClickHandler onMapClick={handleMapClick} />

            {/* Search radius circle */}
            {selectedPoint && (
              <Circle
                center={selectedPoint}
                radius={radius * MILES_TO_METERS}
                pathOptions={{
                  color: '#3b82f6',
                  fillColor: '#3b82f6',
                  fillOpacity: 0.05,
                  weight: 1.5,
                  dashArray: '6 4',
                }}
              />
            )}

            {/* Center marker */}
            {selectedPoint && (
              <Marker
                position={selectedPoint}
                icon={L.divIcon({
                  className: '',
                  iconSize: [16, 16],
                  iconAnchor: [8, 8],
                  html: '<div style="width:16px;height:16px;background:#3b82f6;border:2px solid white;border-radius:50%;box-shadow:0 1px 3px rgba(0,0,0,0.3)"></div>',
                })}
              />
            )}

            {/* Aircraft markers */}
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
                      <span className="text-gray-500">ICAO:</span><span>{ac.icao || '--'}</span>
                      <span className="text-gray-500">Type:</span><span>{ac.aircraft_type || '--'}</span>
                      <span className="text-gray-500">Reg:</span><span>{ac.registration || '--'}</span>
                      <span className="text-gray-500">Altitude:</span><span>{fmtAlt(ac.alt_baro)}</span>
                      <span className="text-gray-500">Speed:</span><span>{ac.gs == null ? '--' : ac.gs + ' kts'}</span>
                      <span className="text-gray-500">Heading:</span><span>{ac.track == null ? '--' : ac.track + '\u00B0'}</span>
                      <span className="text-gray-500">Vert Rate:</span><span>{ac.baro_rate == null ? '--' : ac.baro_rate + ' ft/m'}</span>
                      <span className="text-gray-500">Squawk:</span><span>{ac.squawk || '--'}</span>
                    </div>
                    {ac.emergency && ac.emergency !== 'none' && (
                      <div className="text-red-600 font-bold mt-1">EMERGENCY: {ac.emergency}</div>
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
              <span className="w-3 h-3 rounded-sm shrink-0" style={{ backgroundColor: band.color }} />
              <span>{band.label}</span>
            </div>
          ))}
        </div>

        {/* Initial prompt overlay */}
        {!selectedPoint && aircraft.length === 0 && !loading && (
          <div className="absolute inset-0 flex items-center justify-center z-[1000] pointer-events-none">
            <div className="bg-card/95 border border-border rounded-xl p-8 text-center shadow-lg">
              <Radar className="w-10 h-10 text-primary mx-auto mb-3" />
              <p className="text-foreground font-medium mb-1">Click anywhere on the map</p>
              <p className="text-sm text-muted-foreground">to scan for nearby aircraft</p>
            </div>
          </div>
        )}

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
