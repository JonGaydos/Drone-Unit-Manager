import { describe, it, expect } from 'vitest'
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
  it('renders with a selected location and geofences', () => {
    renderMap(
      <LocationPickerMap
        lat={30.32} lon={-86.14}
        geofences={[
          { id: 1, zone_type: 'no_fly', geometry_type: 'circle', center_lat: 30.3, center_lon: -86.1, radius_m: 200, name: 'NFZ' },
        ]}
        onSelect={() => {}}
      />,
    )
    expect(screen.getAllByTestId('leaflet-stub').length).toBeGreaterThan(0)
  })

  it('renders gracefully with no coords and no geofences', () => {
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
