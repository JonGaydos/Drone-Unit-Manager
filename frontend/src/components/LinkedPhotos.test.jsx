import { describe, it, expect, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import LinkedPhotos from './LinkedPhotos'

const PHOTOS = [
  { id: 11, title: 'North field', filename: 'a.jpg', thumbnail_url: '/photos/11/thumbnail' },
  { id: 12, title: 'South field', filename: 'b.jpg', thumbnail_url: '/photos/12/thumbnail' },
]

describe('LinkedPhotos', () => {
  beforeEach(() => {
    // Linked photos for this entity. Both the filtered query (flight_id=5)
    // and the picker's unfiltered /photos call return the same set here.
    server.use(http.get('/api/photos', () => HttpResponse.json(PHOTOS)))
  })

  it('lists linked photos from /api/photos for the entity', async () => {
    renderWithProviders(<LinkedPhotos entityType="flight" entityId={5} />, { role: 'admin' })

    expect(await screen.findByAltText('North field')).toBeInTheDocument()
    expect(screen.getByAltText('South field')).toBeInTheDocument()
    expect(screen.getByText('(2)')).toBeInTheDocument()
  })

  it('shows an empty state when nothing is linked', async () => {
    server.use(http.get('/api/photos', () => HttpResponse.json([])))
    renderWithProviders(<LinkedPhotos entityType="flight" entityId={5} />, { role: 'admin' })
    expect(await screen.findByText('No photos linked.')).toBeInTheDocument()
  })

  it('unlink fires DELETE /api/photos/:id/:entityType/:entityId', async () => {
    let deletedPath = null
    server.use(http.delete('/api/photos/:photoId/:entityType/:entityId', ({ params }) => {
      deletedPath = `${params.photoId}/${params.entityType}/${params.entityId}`
      return new HttpResponse(null, { status: 204 })
    }))

    const { user } = renderWithProviders(
      <LinkedPhotos entityType="flight" entityId={5} />, { role: 'admin' })

    await screen.findByAltText('North field')
    const unlinkButtons = screen.getAllByRole('button', { name: 'Unlink photo' })
    await user.click(unlinkButtons[0])

    await waitFor(() => expect(deletedPath).toBe('11/flight/5'))
  })

  it('hides attach/unlink controls for a viewer (not a supervisor)', async () => {
    server.use(http.get('/api/auth/me', () =>
      HttpResponse.json({ id: 1, username: 'v', display_name: 'v', role: 'viewer' })))

    renderWithProviders(<LinkedPhotos entityType="flight" entityId={5} />, { role: 'viewer' })

    await screen.findByAltText('North field')
    expect(screen.queryByRole('button', { name: 'Attach photos' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Unlink photo' })).not.toBeInTheDocument()
  })

  // The button counts what is about to be attached, so a mis-click is visible
  // before it commits rather than after.
  it('counts the selection on the attach button', async () => {
    // The picker offers photos NOT already linked, so seed the linked set empty
    // and let the picker's own fetch return both.
    let call = 0
    server.use(http.get('/api/photos', ({ request }) => {
      call += 1
      // First call is the entity-filtered one; the picker's is unfiltered.
      return HttpResponse.json(new URL(request.url).searchParams.size > 0 && call === 1 ? [] : PHOTOS)
    }))
    const { user } = renderWithProviders(<LinkedPhotos entityType="flight" entityId={5} />, { role: 'admin' })

    await user.click(await screen.findByRole('button', { name: /Attach photos/ }))
    const attach = await screen.findByRole('button', { name: 'Attach' })

    await user.click(await screen.findByAltText('North field'))
    expect(attach).toHaveTextContent('Attach 1')

    await user.click(screen.getByAltText('South field'))
    expect(attach).toHaveTextContent('Attach 2')
  })
})
