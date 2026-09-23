import { describe, it, expect, vi } from 'vitest'
import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import { RecentlyDeletedModal } from './RecentlyDeletedModal'

const DELETED = [
  { id: 4, name: 'Scene A', deleted_at: '2026-09-20T14:00:00', deleted_by: 'Pat Pilot', legal_hold: false },
  { id: 5, name: 'Scene B', deleted_at: '2026-09-21T09:30:00', deleted_by: null, legal_hold: true },
]

function mockList(rows = DELETED) {
  server.use(http.get('/api/photos/deleted', () => HttpResponse.json(rows)))
}

// The provider takes the role from GET /api/auth/me, not the stored user.
function asRole(role) {
  server.use(http.get('/api/auth/me', () => HttpResponse.json({ id: 1, username: role, display_name: role, role })))
}

describe('RecentlyDeletedModal', () => {
  it('lists deleted items with who deleted them and any hold', async () => {
    mockList()
    renderWithProviders(<RecentlyDeletedModal kind="photos" open onClose={() => {}} />, { role: 'supervisor' })

    expect(await screen.findByText('Scene A')).toBeInTheDocument()
    expect(screen.getByText(/by Pat Pilot/)).toBeInTheDocument()
    expect(screen.getByText('Legal hold')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /Restore/ })).toHaveLength(2)
  })

  it('offers purge only to admins and never for a held item', async () => {
    mockList()
    asRole('supervisor')
    const { unmount } = renderWithProviders(<RecentlyDeletedModal kind="photos" open onClose={() => {}} />, { role: 'supervisor' })
    await screen.findByText('Scene A')
    expect(screen.queryByRole('button', { name: /permanently/ })).not.toBeInTheDocument()
    unmount()

    asRole('admin')
    renderWithProviders(<RecentlyDeletedModal kind="photos" open onClose={() => {}} />, { role: 'admin' })
    await screen.findByText('Scene A')
    expect(screen.getByRole('button', { name: 'Delete Scene A permanently' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete Scene B permanently' })).not.toBeInTheDocument()
  })

  it('restores an item and tells the page to reload', async () => {
    let restored = null
    mockList()
    server.use(http.post('/api/photos/:id/restore', ({ params }) => {
      restored = params.id
      return HttpResponse.json({ ok: true })
    }))
    const onChanged = vi.fn()
    const { user } = renderWithProviders(
      <RecentlyDeletedModal kind="photos" open onClose={() => {}} onChanged={onChanged} />, { role: 'supervisor' })

    const row = (await screen.findByText('Scene A')).closest('li')
    await user.click(within(row).getByRole('button', { name: /Restore/ }))
    await vi.waitFor(() => expect(onChanged).toHaveBeenCalled())
    expect(restored).toBe('4')
  })

  it('purges after confirmation', async () => {
    let purged = null
    mockList()
    server.use(http.delete('/api/photos/:id/purge', ({ params }) => {
      purged = params.id
      return HttpResponse.json({ ok: true })
    }))
    const { user } = renderWithProviders(<RecentlyDeletedModal kind="photos" open onClose={() => {}} />, { role: 'admin' })

    await user.click(await screen.findByRole('button', { name: 'Delete Scene A permanently' }))
    await user.click(screen.getByRole('button', { name: 'Delete permanently' }))
    await vi.waitFor(() => expect(purged).toBe('4'))
  })
})
