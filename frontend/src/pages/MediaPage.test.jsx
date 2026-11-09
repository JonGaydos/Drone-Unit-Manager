import { describe, it, expect, vi } from 'vitest'
import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { withPermissions } from '@/test/permissions'
import { pilotOption } from '@/test/options'
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
    pilots: () => HttpResponse.json([pilotOption(1, 'Jane Doe')]),
    ...overrides,
  }
  server.use(
    http.get('/api/photos', base.photos),
    http.get('/api/pilots/options', base.pilots),
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

  it('hides Delete on a photo under legal hold and lets a supervisor release it', async () => {
    let body = null
    mockMount({ photos: () => HttpResponse.json([{ ...PHOTOS[0], legal_hold: true }, PHOTOS[1]]) })
    server.use(
      http.get('/api/auth/me', () => HttpResponse.json(withPermissions({ id: 1, username: 's', display_name: 's', role: 'supervisor' }))),
      http.put('/api/photos/1/hold', async ({ request }) => { body = await request.json(); return HttpResponse.json({ ok: true }) }),
    )
    const { user } = renderWithProviders(<MediaPage />, { role: 'supervisor' })

    const held = (await screen.findByText('Tower inspection')).closest('.group')
    const free = screen.getByText('Crash site').closest('.group')
    expect(within(held).queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
    expect(within(held).queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
    expect(within(free).getByRole('button', { name: 'Edit' })).toBeInTheDocument()
    expect(within(free).getByRole('button', { name: 'Delete' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Recently deleted/ })).toBeInTheDocument()

    await user.click(within(held).getByRole('button', { name: 'Release legal hold' }))
    await vi.waitFor(() => expect(body).toEqual({ legal_hold: false }))
  })

  it('shows neither hold controls nor the deleted list to a pilot', async () => {
    mockMount()
    server.use(http.get('/api/auth/me', () => HttpResponse.json(withPermissions({ id: 1, username: 'p', display_name: 'p', role: 'pilot' }))))
    renderWithProviders(<MediaPage />, { role: 'pilot' })
    await screen.findByText('Tower inspection')
    expect(screen.queryByRole('button', { name: /legal hold/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Recently deleted/ })).not.toBeInTheDocument()
  })

  it('sends cleared fields and an empty pilot list when every pilot is untagged', async () => {
    let sent = null
    mockMount({ photos: () => HttpResponse.json([{ ...PHOTOS[0], description: 'North face', pilot_ids: [1] }]) })
    server.use(http.patch('/api/photos/1', async ({ request }) => {
      sent = Object.fromEntries(await request.formData())
      return HttpResponse.json({ message: 'Photo updated' })
    }))
    const { user } = renderWithProviders(<MediaPage />, { role: 'admin' })

    const card = (await screen.findByText('Tower inspection')).closest('.group')
    await user.click(within(card).getByRole('button', { name: 'Edit' }))
    await user.clear(await screen.findByLabelText('Description'))
    await user.clear(screen.getByLabelText('Date Taken'))
    await user.click(screen.getByRole('button', { name: 'Jane Doe' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await vi.waitFor(() => expect(sent).toEqual({
      title: 'Tower inspection', description: '', date_taken: '', pilot_ids: '',
    }))
  })
})
