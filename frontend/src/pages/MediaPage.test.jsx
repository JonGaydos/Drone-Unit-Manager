import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import MediaPage from './MediaPage'

// Mount endpoints (Promise.all; .catch -> swallowed):
//   GET /photos   (array)
//   GET /pilots   (array)
// Empty/errored -> "No Photos Yet". Filter is client-side search over
// title/filename/pilot_names.

const PHOTOS = [
  { id: 1, title: 'Tower inspection', filename: 'tower.jpg', file_size: 204800, date_taken: '2026-06-01', pilot_names: ['Jane Doe'] },
  { id: 2, title: 'Crash site', filename: 'scene.jpg', file_size: 102400, date_taken: '2026-06-02', pilot_names: [] },
]

function mockMount(overrides = {}) {
  const base = {
    photos: () => HttpResponse.json(PHOTOS),
    pilots: () => HttpResponse.json([{ id: 1, first_name: 'Jane', last_name: 'Doe', is_active: true }]),
    ...overrides,
  }
  server.use(
    http.get('/api/photos', base.photos),
    http.get('/api/pilots', base.pilots),
  )
}

describe('MediaPage', () => {
  it('renders without crashing', async () => {
    mockMount()
    renderWithProviders(<MediaPage />, { role: 'admin' })
    expect(await screen.findByText('Photo Gallery')).toBeInTheDocument()
  })

  it('renders photo cards from a populated payload', async () => {
    mockMount()
    renderWithProviders(<MediaPage />, { role: 'admin' })
    expect(await screen.findByText('Tower inspection')).toBeInTheDocument()
    expect(screen.getByText('Crash site')).toBeInTheDocument()
    expect(screen.getByText('(2 photos)')).toBeInTheDocument()
  })

  it('shows the empty state when there are no photos', async () => {
    mockMount({ photos: () => HttpResponse.json([]) })
    renderWithProviders(<MediaPage />, { role: 'admin' })
    expect(await screen.findByText('No Photos Yet')).toBeInTheDocument()
  })

  it('falls back to the empty state when /photos 500s (error swallowed)', async () => {
    mockMount({ photos: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }) })
    renderWithProviders(<MediaPage />, { role: 'admin' })
    expect(await screen.findByText('No Photos Yet')).toBeInTheDocument()
  })

  it('filters photos client-side via the search box', async () => {
    mockMount()
    const { user } = renderWithProviders(<MediaPage />, { role: 'admin' })
    await screen.findByText('Tower inspection')

    await user.type(screen.getByPlaceholderText('Search photos...'), 'tower')
    expect(screen.getByText('Tower inspection')).toBeInTheDocument()
    expect(screen.queryByText('Crash site')).toBeNull()
  })

  // The upload and edit modals share one pilot-chip toggle. It is the only
  // thing standing between "assign this pilot" and "assign this pilot twice",
  // and a chip that cannot be un-picked leaves the wrong pilot on the photo.
  it('picks a pilot chip and un-picks it on a second click', async () => {
    mockMount()
    const { user } = renderWithProviders(<MediaPage />, { role: 'admin' })

    await screen.findByText('Photo Gallery')
    await user.click(screen.getByRole('button', { name: 'Upload' }))

    const chip = await screen.findByRole('button', { name: 'Jane Doe' })
    expect(chip.className).toContain('bg-muted')

    await user.click(chip)
    expect(chip.className).toContain('bg-primary')

    await user.click(chip)
    expect(chip.className).toContain('bg-muted')
  })
})
