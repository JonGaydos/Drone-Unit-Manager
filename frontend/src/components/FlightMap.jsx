/**
 * Leaflet map components for flight path visualization, location picking, and flight location overview.
 * Uses OpenStreetMap tiles and react-leaflet for rendering.
 */
import { MapContainer, TileLayer, Polyline, Marker, Popup, Circle, Polygon, useMap } from 'react-leaflet'
import L from 'leaflet'
import { useEffect } from 'react'

// Fix default marker icon paths for bundled Leaflet builds
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

/**
 * Helper component that adjusts the map viewport to fit the given bounds.
 * @param {Object} props
 * @param {Array<[number, number]>} props.bounds - Array of [lat, lng] coordinates to fit.
 */
function FitBounds({ bounds }) {
  const map = useMap()
  useEffect(() => {
    if (bounds && bounds.length > 1) {
      map.fitBounds(bounds, { padding: [30, 30] })
    } else if (bounds && bounds.length === 1) {
      map.setView(bounds[0], 15)
    }
  }, [map, bounds])
  return null
}

/**
 * Invisible component that registers a click handler on the map for location selection.
 * @param {Object} props
 * @param {Function} props.onSelect - Callback invoked with (lat, lng) on map click.
 */
function ClickHandler({ onSelect }) {
  const map = useMap()
  useEffect(() => {
    if (!onSelect) return
    const handler = (e) => onSelect(e.latlng.lat, e.latlng.lng)
    map.on('click', handler)
    return () => map.off('click', handler)
  }, [map, onSelect])
  return null
}

/** @type {[number, number]} Default map center coordinates (lat, lng). */
const DEFAULT_CENTER = [30.32, -86.14]

/** @type {Record<string, string>} Geofence zone type to color mapping. */
const ZONE_COLORS = {
  no_fly: '#ef4444',
  restricted: '#f59e0b',
  caution: '#eab308',
  authorized: '#22c55e',
}

/**
 * Displays a flight path polyline with takeoff and landing markers.
 * Auto-fits the map to the telemetry bounds.
 * @param {Object} props
 * @param {Array<{lat: number, lon: number}>} [props.telemetry=[]] - Telemetry data points.
 * @param {number} [props.takeoffLat] - Takeoff latitude.
 * @param {number} [props.takeoffLon] - Takeoff longitude.
 * @param {number} [props.landingLat] - Landing latitude.
 * @param {number} [props.landingLon] - Landing longitude.
 * @param {string} [props.height='400px'] - Map container height.
 */
export function FlightPathMap({ telemetry = [], takeoffLat, takeoffLon, landingLat, landingLon, height = '400px' }) {
  const path = telemetry.filter(p => p.lat && p.lon).map(p => [p.lat, p.lon])
  const center = takeoffLat && takeoffLon
    ? [takeoffLat, takeoffLon]
    : path.length > 0 ? path[0] : DEFAULT_CENTER
  const bounds = path.length > 1 ? path : takeoffLat ? [[takeoffLat, takeoffLon]] : null

  return (
    <div style={{ height }} className="rounded-xl overflow-hidden border border-border relative z-0">
      <MapContainer center={center} zoom={15} style={{ height: '100%', width: '100%' }} scrollWheelZoom={true}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {path.length > 1 && (
          <Polyline positions={path} pathOptions={{ color: '#818cf8', weight: 3, opacity: 0.8 }} />
        )}
        {takeoffLat && takeoffLon && (
          <Marker position={[takeoffLat, takeoffLon]}>
            <Popup>Takeoff</Popup>
          </Marker>
        )}
        {landingLat && landingLon && (
          <Marker position={[landingLat, landingLon]}>
            <Popup>Landing</Popup>
          </Marker>
        )}
        {bounds && <FitBounds bounds={bounds} />}
      </MapContainer>
    </div>
  )
}

/**
 * Interactive map for selecting a geographic location by clicking.
 * Renders geofence zones as circles or polygons with color-coded overlays.
 * @param {Object} props
 * @param {number} [props.lat] - Currently selected latitude.
 * @param {number} [props.lon] - Currently selected longitude.
 * @param {Function} [props.onSelect] - Callback invoked with (lat, lng) on map click.
 * @param {Array<Object>} [props.geofences=[]] - Geofence zone objects to display.
 * @param {string} [props.height='400px'] - Map container height.
 */
export function LocationPickerMap({ lat, lon, onSelect, geofences = [], height = '400px' }) {
  const center = lat && lon ? [lat, lon] : DEFAULT_CENTER

  return (
    <div style={{ height }} className="rounded-xl overflow-hidden border border-border relative z-0">
      <MapContainer center={center} zoom={12} style={{ height: '100%', width: '100%' }} scrollWheelZoom={true}>
        <TileLayer
          attribution='&copy; OpenStreetMap'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {lat && lon && (
          <Marker position={[lat, lon]}>
            <Popup>Selected: {lat.toFixed(5)}, {lon.toFixed(5)}</Popup>
          </Marker>
        )}
        {geofences.map(g => {
          const color = ZONE_COLORS[g.zone_type] || '#6b7280'
          if (g.geometry_type === 'circle' && g.center_lat && g.center_lon) {
            return (
              <Circle key={g.id} center={[g.center_lat, g.center_lon]} radius={g.radius_m || 100}
                pathOptions={{ color, fillOpacity: 0.15, weight: 2 }}>
                <Popup>{g.name} ({g.zone_type})</Popup>
              </Circle>
            )
          }
          if (g.geometry_type === 'polygon' && g.polygon_points?.length > 2) {
            return (
              <Polygon key={g.id} positions={g.polygon_points}
                pathOptions={{ color, fillOpacity: 0.15, weight: 2 }}>
                <Popup>{g.name} ({g.zone_type})</Popup>
              </Polygon>
            )
          }
          return null
        })}
        <ClickHandler onSelect={onSelect} />
      </MapContainer>
    </div>
  )
}

/**
 * Overview map showing takeoff locations for multiple flights as markers.
 * Each marker popup links to the flight detail page.
 * @param {Object} props
 * @param {Array<Object>} [props.flights=[]] - Flight objects with takeoff_lat/takeoff_lon.
 * @param {string} [props.height='400px'] - Map container height.
 */
export function FlightLocationsMap({ flights = [], height = '400px' }) {
  const markers = flights.filter(f => f.takeoff_lat && f.takeoff_lon)
  const center = markers.length > 0 ? [markers[0].takeoff_lat, markers[0].takeoff_lon] : DEFAULT_CENTER
  const bounds = markers.length > 1 ? markers.map(m => [m.takeoff_lat, m.takeoff_lon]) : null

  return (
    <div style={{ height }} className="rounded-xl overflow-hidden border border-border relative z-0">
      <MapContainer center={center} zoom={10} style={{ height: '100%', width: '100%' }} scrollWheelZoom={true}>
        <TileLayer
          attribution='&copy; OpenStreetMap'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {markers.map(f => (
          <Marker key={f.id} position={[f.takeoff_lat, f.takeoff_lon]}>
            <Popup>
              <a href={`/flights/${f.id}`} style={{ color: '#818cf8' }}>{f.date || 'No date'}</a>
              <br />{f.pilot_name || 'Unknown pilot'}
              <br />Purpose: {f.purpose || 'None'}
            </Popup>
          </Marker>
        ))}
        {bounds && <FitBounds bounds={bounds} />}
      </MapContainer>
    </div>
  )
}
