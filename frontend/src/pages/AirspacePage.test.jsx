import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import AirspacePage from './AirspacePage'

// react-leaflet is globally stubbed (MapContainer -> data-testid="leaflet-stub",
// useMapEvents -> {}). Mount endpoint:
//   GET /settings  (resolveOrgLocation; .catch swallowed)
// /adsb/nearby only fires after a map click or manual Refresh once a point is
// selected. With no selected point the initial overlay prompt shows. Radius and
// refresh-interval selects are local-state interactions.

function mockSettings(impl) {
  server.use(http.get('/api/settings', impl || (() => HttpResponse.json([]))))
}

describe('AirspacePage', () => {
  it('renders without crashing under the leaflet stub', async () => {
    mockSettings()
    renderWithProviders(<AirspacePage />, { role: 'admin' })
    expect(await screen.findByTestId('leaflet-stub')).toBeInTheDocument()
  })

  it('shows the initial "click the map" prompt and control bar', async () => {
    mockSettings(() => HttpResponse.json([
      { key: 'org_default_lat', value: '38.9' },
      { key: 'org_default_lon', value: '-77.0' },
    ]))
    renderWithProviders(<AirspacePage />, { role: 'admin' })
    expect(await screen.findByText('Click anywhere on the map')).toBeInTheDocument()
    // Control bar with the altitude legend and the radius selector.
    expect(screen.getByText('Altitude')).toBeInTheDocument()
    expect(screen.getByLabelText('Radius')).toBeInTheDocument()
  })

  it('renders when /settings 500s (error swallowed, defaults to US center)', async () => {
    mockSettings(() => HttpResponse.json({ detail: 'boom' }, { status: 500 }))
    renderWithProviders(<AirspacePage />, { role: 'admin' })
    expect(await screen.findByTestId('leaflet-stub')).toBeInTheDocument()
    expect(screen.getByText('Click anywhere on the map')).toBeInTheDocument()
  })

  it('changes the search radius via the radius select (local state)', async () => {
    mockSettings()
    const { user } = renderWithProviders(<AirspacePage />, { role: 'admin' })
    await screen.findByTestId('leaflet-stub')

    const radius = screen.getByLabelText('Radius')
    await user.selectOptions(radius, '200')
    expect(radius).toHaveValue('200')
  })
})
