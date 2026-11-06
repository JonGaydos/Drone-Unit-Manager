import { describe, it, expect, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { useLocation } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import { CommandPalette } from './CommandPalette'

// Probe that surfaces the current router location so we can assert navigation.
function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location">{location.pathname + location.search}</div>
}

function renderPalette(opts = { role: 'admin' }) {
  return renderWithProviders(
    <>
      <CommandPalette />
      <LocationProbe />
    </>,
    opts,
  )
}

beforeEach(() => {
  // Entity search endpoint hit when the query is >= 2 chars.
  server.use(http.get('/api/search', () =>
    HttpResponse.json({
      results: [
        { type: 'pilot', title: 'Jane Pilot', subtitle: 'PIC', url: '/pilots/7' },
      ],
    })))
})

describe('CommandPalette', () => {
  it('opens on Ctrl+K', async () => {
    const { user } = renderPalette()
    // Closed initially: returns null, so the search input is absent.
    expect(screen.queryByPlaceholderText(/Search pilots/)).not.toBeInTheDocument()

    await user.keyboard('{Control>}k{/Control}')
    expect(await screen.findByPlaceholderText(/Search pilots/)).toBeInTheDocument()
  })

  it('opens on the open-command-palette event', async () => {
    renderPalette()
    await screen.findByTestId('location')
    // The listener is attached in an effect that can run after the first paint,
    // so send the event until the palette has heard it. Opening is idempotent.
    await waitFor(() => {
      globalThis.dispatchEvent(new CustomEvent('open-command-palette'))
      expect(screen.getByPlaceholderText(/Search pilots/)).toBeInTheDocument()
    })
  })

  it('filters static page targets as you type', async () => {
    const { user } = renderPalette()
    await user.keyboard('{Control>}k{/Control}')
    const input = await screen.findByPlaceholderText(/Search pilots/)

    await user.type(input, 'analytics')
    expect(await screen.findByText('Analytics')).toBeInTheDocument()
    // Unrelated page is filtered out.
    expect(screen.queryByText('Maintenance')).not.toBeInTheDocument()
  })

  it('shows entity results from GET /api/search and navigates on selection', async () => {
    const { user } = renderPalette()
    await user.keyboard('{Control>}k{/Control}')
    const input = await screen.findByPlaceholderText(/Search pilots/)

    await user.type(input, 'jane')
    const result = await screen.findByText('Jane Pilot')

    await user.click(result)
    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent('/pilots/7'))
    // Selecting closes the palette.
    expect(screen.queryByPlaceholderText(/Search pilots/)).not.toBeInTheDocument()
  })

  it('leaves out a page whose view is off', async () => {
    const { user } = renderPalette({ role: 'pilot', permissions: { 'pilots.view': 'no' } })
    await user.keyboard('{Control>}k{/Control}')
    await screen.findByPlaceholderText(/Search pilots/)
    expect(screen.queryByRole('button', { name: /Pilots/ })).toBeNull()
    expect(screen.getByRole('button', { name: /Fleet Health/ })).toBeInTheDocument()
  })
})
