import { describe, it, expect, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import DocumentUpload from './DocumentUpload'

// Default auth/me handler returns an admin, so the upload affordance shows.
beforeEach(() => {
  server.use(http.get('/api/documents', () => HttpResponse.json([])))
})

function openUploadAndPick(user) {
  return (async () => {
    await user.click(screen.getByRole('button', { name: /Upload/ }))
    const input = document.querySelector('input[type="file"]')
    const file = new File(['hello'], 'cert.pdf', { type: 'application/pdf' })
    await user.upload(input, file)
  })()
}

describe('DocumentUpload', () => {
  it('lists documents from /api/documents for the entity', async () => {
    server.use(http.get('/api/documents', () =>
      HttpResponse.json([
        { id: 1, title: 'Part 107', document_type: 'part_107', mime_type: 'application/pdf' },
      ])))

    renderWithProviders(<DocumentUpload entityType="pilot" entityId={3} />, { role: 'admin' })
    expect(await screen.findByText('Part 107')).toBeInTheDocument()
    expect(screen.getByText('(1)')).toBeInTheDocument()
  })

  it('selecting a file and saving fires POST /api/documents/upload', async () => {
    let uploadHit = false
    server.use(http.post('/api/documents/upload', () => {
      uploadHit = true
      return HttpResponse.json({ id: 99 })
    }))

    const { user } = renderWithProviders(
      <DocumentUpload entityType="pilot" entityId={3} />, { role: 'admin' })
    await screen.findByText('No documents uploaded')

    await openUploadAndPick(user)
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(uploadHit).toBe(true))
  })

  it('surfaces an error toast when the upload fails', async () => {
    server.use(http.post('/api/documents/upload', () =>
      HttpResponse.json({ detail: 'File too large' }, { status: 400 })))

    const { user } = renderWithProviders(
      <DocumentUpload entityType="pilot" entityId={3} />, { role: 'admin' })
    await screen.findByText('No documents uploaded')

    await openUploadAndPick(user)
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByText('File too large')).toBeInTheDocument()
  })

  it('shows the upload affordance for a pilot (matches the pilot-gated API)', async () => {
    server.use(http.get('/api/auth/me', () =>
      HttpResponse.json({ id: 1, username: 'p', display_name: 'p', role: 'pilot' })))

    renderWithProviders(<DocumentUpload entityType="pilot" entityId={3} />, { role: 'pilot' })
    await screen.findByText('No documents uploaded')
    expect(await screen.findByRole('button', { name: /Upload/ })).toBeInTheDocument()
  })

  it('hides the upload affordance for a viewer', async () => {
    server.use(http.get('/api/auth/me', () =>
      HttpResponse.json({ id: 1, username: 'v', display_name: 'v', role: 'viewer' })))

    renderWithProviders(<DocumentUpload entityType="pilot" entityId={3} />, { role: 'viewer' })
    await screen.findByText('No documents uploaded')
    expect(screen.queryByRole('button', { name: /Upload/ })).not.toBeInTheDocument()
  })
})
