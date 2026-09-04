import { describe, it, expect } from 'vitest'
import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import ApiTokensSection from './ApiTokensSection'

// Mount endpoint: GET /api/api-tokens. Create: POST /api/api-tokens.
const TOKENS = [
  { id: 1, name: 'Home Assistant', token_prefix: 'dum_abc12345', read_only: true, scopes: ['fleet'], created_at: '2026-07-16T00:00:00', last_used_at: null, revoked_at: null },
  { id: 2, name: 'Old integration', token_prefix: 'dum_zzz99999', read_only: false, scopes: null, created_at: '2026-06-01T00:00:00', last_used_at: '2026-06-30T12:00:00', revoked_at: '2026-07-01T00:00:00' },
]

function mockMount(rows = TOKENS) {
  server.use(http.get('/api/api-tokens', () => HttpResponse.json(rows)))
}

describe('ApiTokensSection', () => {
  it('lists tokens with prefix, access, areas, and status', async () => {
    mockMount()
    renderWithProviders(<ApiTokensSection />, { role: 'admin' })

    expect(await screen.findByText('Home Assistant')).toBeInTheDocument()
    expect(screen.getByText('dum_abc12345...')).toBeInTheDocument()
    expect(screen.getByText('Read only')).toBeInTheDocument()
    expect(screen.getByText('Fleet')).toBeInTheDocument()
    expect(screen.getByText('All areas')).toBeInTheDocument()
    expect(screen.getByText('revoked')).toBeInTheDocument()
    // Revoked tokens have no revoke action
    expect(screen.getAllByRole('button', { name: 'Revoke' })).toHaveLength(1)
  })

  it('creates a token with selected options and shows it once', async () => {
    let captured = null
    mockMount([])
    server.use(
      http.post('/api/api-tokens', async ({ request }) => {
        captured = await request.json()
        return HttpResponse.json({ token: 'dum_brand-new-secret', id: 9, name: captured.name, token_prefix: 'dum_brand-ne', read_only: captured.read_only, scopes: captured.scopes })
      }),
    )
    const { user } = renderWithProviders(<ApiTokensSection />, { role: 'admin' })
    await screen.findByText('No API tokens yet')

    await user.click(screen.getByRole('button', { name: /Create Token/ }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('Name'), 'Home Assistant')
    await user.selectOptions(within(dialog).getByLabelText('Access'), 'read')
    await user.click(within(dialog).getByLabelText('All areas'))  // uncheck -> pick areas
    await user.click(within(dialog).getByLabelText('Fleet'))
    await user.click(within(dialog).getByRole('button', { name: 'Create Token' }))

    expect(await screen.findByDisplayValue('dum_brand-new-secret')).toBeInTheDocument()
    expect(captured).toMatchObject({ name: 'Home Assistant', read_only: true, scopes: ['fleet'] })
  })
})
