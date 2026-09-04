import '@testing-library/jest-dom/vitest'
import { afterAll, afterEach, beforeAll, vi } from 'vitest'
import { cleanup } from '@testing-library/react'
import { server } from './server'

// --- jsdom gaps ---
globalThis.matchMedia ||= (query) => ({
  matches: false, media: query, onchange: null,
  addListener() {}, removeListener() {},
  addEventListener() {}, removeEventListener() {}, dispatchEvent() { return false },
})
class _Observer { observe() {} unobserve() {} disconnect() {} takeRecords() { return [] } }
globalThis.ResizeObserver ||= _Observer
globalThis.IntersectionObserver ||= _Observer
globalThis.URL.createObjectURL ||= () => 'blob:mock'
globalThis.URL.revokeObjectURL ||= () => {}
Element.prototype.scrollTo ||= () => {}

// --- module stubs for jsdom-incompatible libs ---
// react-leaflet: FlightMap imports MapContainer, TileLayer, Polyline, Marker,
// Popup, Circle, Polygon, useMap; AirspacePage also uses useMapEvents.
vi.mock('react-leaflet', () => {
  const Stub = ({ children }) => <div data-testid="leaflet-stub">{children}</div>
  return {
    MapContainer: Stub, TileLayer: () => null, Marker: Stub, Popup: Stub,
    Circle: () => null, Polyline: () => null, Polygon: () => null,
    useMap: () => ({ fitBounds() {}, setView() {}, getZoom: () => 12, setZoom() {}, on() {}, off() {}, remove() {}, invalidateSize() {} }),
    useMapEvents: () => ({}),
  }
})
// leaflet: FlightMap uses L.Icon.Default.{prototype,mergeOptions}; pages use L.divIcon.
vi.mock('leaflet', () => ({
  default: {
    icon: () => ({}),
    divIcon: () => ({}),
    Icon: { Default: { mergeOptions() {}, prototype: {} } },
  },
}))
vi.mock('@fullcalendar/react', () => ({ default: () => <div data-testid="fullcalendar-stub" /> }))
vi.mock('@fullcalendar/daygrid', () => ({ default: {} }))
vi.mock('@fullcalendar/timegrid', () => ({ default: {} }))
vi.mock('@fullcalendar/list', () => ({ default: {} }))
vi.mock('@fullcalendar/interaction', () => ({ default: {} }))
vi.mock('recharts', async (orig) => {
  // Keep real chart primitives (BarChart, Bar, XAxis, etc.); only replace
  // ResponsiveContainer so charts mount in jsdom with a non-zero size.
  const actual = await orig()
  return {
    ...actual,
    ResponsiveContainer: ({ children }) => (
      <div data-testid="recharts-stub" style={{ width: 800, height: 400 }}>{children}</div>
    ),
  }
})

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => { server.resetHandlers(); cleanup(); localStorage.clear() })
afterAll(() => server.close())
