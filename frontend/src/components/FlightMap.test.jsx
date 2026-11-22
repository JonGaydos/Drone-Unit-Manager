import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { FlightPathMap, LocationPickerMap, FlightLocationsMap } from './FlightMap'

// These assert the maps mount without throwing for valid and for
// empty/invalid inputs.
function renderMap(ui) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

describe('FlightPathMap', () => {
  it('renders a flight path with valid telemetry and takeoff/landing coords', () => {
    renderMap(
      <FlightPathMap
        telemetry={[{ lat: 30.3, lon: -86.1 }, { lat: 30.4, lon: -86.2 }]}
        takeoffLat={30.3} takeoffLon={-86.1}
        landingLat={30.4} landingLon={-86.2}
      />,
    )
    expect(screen.getAllByTestId('leaflet-stub').length).toBeGreaterThan(0)
  })

  it('renders gracefully with no telemetry (falls back to default center)', () => {
    renderMap(<FlightPathMap />)
    expect(screen.getByTestId('leaflet-stub')).toBeInTheDocument()
  })

  it('renders gracefully when telemetry points have null coords', () => {
    renderMap(<FlightPathMap telemetry={[{ lat: null, lon: null }, {}]} />)
    expect(screen.getByTestId('leaflet-stub')).toBeInTheDocument()
  })
})

describe('LocationPickerMap', () => {
  it('renders with a selected location', () => {
    renderMap(
      <LocationPickerMap
        lat={30.32} lon={-86.14}
        onSelect={() => {}}
      />,
    )
    expect(screen.getAllByTestId('leaflet-stub').length).toBeGreaterThan(0)
  })

  it('renders gracefully with no coords', () => {
    renderMap(<LocationPickerMap />)
    expect(screen.getByTestId('leaflet-stub')).toBeInTheDocument()
  })
})

describe('FlightLocationsMap', () => {
  it('renders markers for flights with takeoff coords', () => {
    renderMap(
      <FlightLocationsMap
        flights={[
          { id: 1, takeoff_lat: 30.3, takeoff_lon: -86.1, date: '2026-01-01', pilot_name: 'Jane' },
          { id: 2, takeoff_lat: 30.5, takeoff_lon: -86.3 },
        ]}
      />,
    )
    expect(screen.getAllByTestId('leaflet-stub').length).toBeGreaterThan(0)
  })

  it('renders gracefully with an empty flights list', () => {
    renderMap(<FlightLocationsMap flights={[]} />)
    expect(screen.getByTestId('leaflet-stub')).toBeInTheDocument()
  })

  it('renders gracefully with no flights prop', () => {
    renderMap(<FlightLocationsMap />)
    expect(screen.getByTestId('leaflet-stub')).toBeInTheDocument()
  })
})

describe('FlightLocationsMap fitting', () => {
  afterEach(() => {
    delete globalThis.__leafletMap
    vi.unstubAllGlobals()
  })

  it('invalidates the map size before fitting, and refits when the container gains a size', () => {
    const calls = []
    const container = document.createElement('div')
    globalThis.__leafletMap = {
      invalidateSize: vi.fn(() => calls.push('invalidateSize')),
      fitBounds: vi.fn(() => calls.push('fitBounds')),
      setView: vi.fn(),
      getContainer: () => container,
      getZoom: () => 12, on() {}, off() {},
    }
    let resizeCallback
    const observe = vi.fn()
    const disconnect = vi.fn()
    vi.stubGlobal('ResizeObserver', class {
      constructor(cb) { resizeCallback = cb }
      observe(el) { observe(el) }
      disconnect() { disconnect() }
    })

    const { unmount } = renderMap(
      <FlightLocationsMap
        flights={[
          { id: 1, takeoff_lat: 45.1, takeoff_lon: -100.1 },
          { id: 2, takeoff_lat: 45.2, takeoff_lon: -100.2 },
        ]}
      />,
    )
    expect(calls).toEqual(['invalidateSize', 'fitBounds'])
    expect(observe).toHaveBeenCalledWith(container)

    // Still zero sized: no refit.
    resizeCallback([{ contentRect: { width: 0, height: 0 } }])
    expect(globalThis.__leafletMap.fitBounds).toHaveBeenCalledTimes(1)

    resizeCallback([{ contentRect: { width: 600, height: 400 } }])
    expect(calls).toEqual(['invalidateSize', 'fitBounds', 'invalidateSize', 'fitBounds'])

    unmount()
    expect(disconnect).toHaveBeenCalled()
  })
})
