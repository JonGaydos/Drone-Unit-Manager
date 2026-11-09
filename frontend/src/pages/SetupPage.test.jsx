import { describe, it, expect, vi, afterEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import SetupPage from './SetupPage'

// SetupPage makes NO API calls on mount; it is a multi-step wizard whose only
// network calls are user-triggered (setup POST, optional uploads). So the
// b/c/d data-loading baseline does not apply; we assert static content plus
// the interactive submit flow instead.

describe('SetupPage', () => {
  afterEach(() => { vi.unstubAllGlobals() })

  it('renders step 1 (organization) without crashing', () => {
    renderWithProviders(<SetupPage />, { route: '/setup' })
    expect(screen.getByRole('heading', { name: 'Drone Unit Manager' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Organization' })).toBeInTheDocument()
    expect(screen.getByLabelText('Organization Name')).toBeInTheDocument()
    expect(screen.getByLabelText('Your Name')).toBeInTheDocument()
  })

  it('advances to the admin-account step', async () => {
    const { user } = renderWithProviders(<SetupPage />, { route: '/setup' })
    await user.type(screen.getByLabelText('Your Name'), 'John Doe')
    await user.click(screen.getByRole('button', { name: /Continue/ }))
    expect(screen.getByRole('heading', { name: 'Create Admin Account' })).toBeInTheDocument()
  })

  it('blocks a weak password with an inline validation error', async () => {
    const { user } = renderWithProviders(<SetupPage />, { route: '/setup' })
    await user.type(screen.getByLabelText('Your Name'), 'John Doe')
    await user.click(screen.getByRole('button', { name: /Continue/ }))

    await user.type(screen.getByLabelText('Username'), 'admin')
    await user.type(screen.getByLabelText('Password'), 'short')
    await user.type(screen.getByLabelText('Confirm Password'), 'short')
    await user.type(screen.getByLabelText('Install Token'), 'the-install-token')
    await user.click(screen.getByRole('button', { name: 'Create Account & Start' }))

    expect(await screen.findByText('Password must be at least 12 characters')).toBeInTheDocument()
  })

  it('keeps Create Account disabled on a fresh install until the install token is entered', async () => {
    const { user } = renderWithProviders(<SetupPage />, { route: '/setup' })
    await user.type(screen.getByLabelText('Your Name'), 'John Doe')
    await user.click(screen.getByRole('button', { name: /Continue/ }))
    await user.type(screen.getByLabelText('Username'), 'admin')
    await user.type(screen.getByLabelText('Password'), 'Password1234')
    await user.type(screen.getByLabelText('Confirm Password'), 'Password1234')

    expect(screen.getByRole('button', { name: 'Create Account & Start' })).toBeDisabled()
    await user.type(screen.getByLabelText('Install Token'), 'the-install-token')
    expect(screen.getByRole('button', { name: 'Create Account & Start' })).toBeEnabled()
  })

  it('POSTs /auth/setup with valid input and the install token, and advances to optional setup', async () => {
    let body = null
    let sentToken = null
    server.use(http.post('/api/auth/setup', async ({ request }) => {
      body = await request.json()
      sentToken = request.headers.get('X-Install-Token')
      return HttpResponse.json({ token: 'setup-token' })
    }))

    const { user } = renderWithProviders(<SetupPage />, { route: '/setup' })
    await user.type(screen.getByLabelText('Your Name'), 'John Doe')
    await user.click(screen.getByRole('button', { name: /Continue/ }))

    await user.type(screen.getByLabelText('Username'), 'admin')
    await user.type(screen.getByLabelText('Password'), 'Password1234')
    await user.type(screen.getByLabelText('Confirm Password'), 'Password1234')
    await user.type(screen.getByLabelText('Install Token'), 'the-install-token')
    await user.click(screen.getByRole('button', { name: 'Create Account & Start' }))

    expect(await screen.findByText('Account created')).toBeInTheDocument()
    expect(body.username).toBe('admin')
    expect(sentToken).toBe('the-install-token')
    expect(localStorage.getItem('token')).toBe('setup-token')
  })

  it('shows the recovery banner and lands on the admin-fields step in recovery mode', () => {
    renderWithProviders(<SetupPage recovery />, { route: '/setup' })
    expect(screen.getByText('Restored backup detected')).toBeInTheDocument()
    expect(screen.getByText(/Reactivate an administrator/)).toBeInTheDocument()
    // Skips the (ignored) Organization step and shows username/password directly.
    expect(screen.getByRole('heading', { name: 'Reactivate Administrator' })).toBeInTheDocument()
    expect(screen.getByLabelText('Username')).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
    expect(screen.getByLabelText('Install Token')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Organization' })).not.toBeInTheDocument()
  })

  it('sends the install token header when reactivating in recovery mode', async () => {
    let sentToken = null
    server.use(http.post('/api/auth/setup', async ({ request }) => {
      sentToken = request.headers.get('X-Install-Token')
      return HttpResponse.json({ token: 't', user: { id: 1, username: 'chief', role: 'admin' } })
    }))
    const { user } = renderWithProviders(<SetupPage recovery />, { route: '/setup' })
    await user.type(screen.getByLabelText('Username'), 'chief')
    await user.type(screen.getByLabelText('Password'), 'Recovered1234')
    await user.type(screen.getByLabelText('Confirm Password'), 'Recovered1234')
    await user.type(screen.getByLabelText('Install Token'), 'the-install-token')
    await user.click(screen.getByRole('button', { name: /Reactivate & Sign In/ }))

    await waitFor(() => expect(sentToken).toBe('the-install-token'))
  })

  it('goes straight into the app after reactivating an admin, skipping fresh-install setup', async () => {
    // Writable location so the redirect does not navigate the jsdom window.
    vi.stubGlobal('location', { href: 'http://localhost/setup', origin: 'http://localhost' })
    server.use(http.post('/api/auth/setup', () =>
      HttpResponse.json({ token: 'reclaimed', user: { id: 1, username: 'chief', role: 'admin' } })))
    const { user } = renderWithProviders(<SetupPage recovery />, { route: '/setup' })
    await user.type(screen.getByLabelText('Username'), 'chief')
    await user.type(screen.getByLabelText('Password'), 'Recovered1234')
    await user.type(screen.getByLabelText('Confirm Password'), 'Recovered1234')
    await user.type(screen.getByLabelText('Install Token'), 'the-install-token')
    await user.click(screen.getByRole('button', { name: /Reactivate & Sign In/ }))

    await waitFor(() => expect(globalThis.location.href).toBe('/'))
    expect(localStorage.getItem('token')).toBe('reclaimed')
    expect(screen.queryByText('Account created')).not.toBeInTheDocument()
  })

  it('tells the operator what an older backup could not bring back', () => {
    renderWithProviders(<SetupPage recovery />, { route: '/setup' })
    expect(screen.getByText(/reset the other users' passwords/)).toBeInTheDocument()
  })

  it('omits the recovery banner on a normal fresh install', () => {
    renderWithProviders(<SetupPage />, { route: '/setup' })
    expect(screen.queryByText('Restored backup detected')).not.toBeInTheDocument()
  })

  it('reveals the restore-from-backup panel on demand', async () => {
    const { user } = renderWithProviders(<SetupPage />, { route: '/setup' })
    await user.click(screen.getByRole('button', { name: /Restore from a backup instead/ }))
    expect(screen.getByRole('heading', { name: 'Restore from Backup' })).toBeInTheDocument()
  })

  it('includes the selected timezone in the setup payload', async () => {
    let setupBody = null
    server.use(http.post('/api/auth/setup', async ({ request }) => {
      setupBody = await request.json()
      return HttpResponse.json({ token: 't', user: { id: 1, username: 'admin', role: 'admin' } })
    }))
    const { user } = renderWithProviders(<SetupPage />)

    await user.type(screen.getByLabelText('Your Name'), 'Admin User')
    await user.selectOptions(await screen.findByLabelText('Time Zone'), 'America/New_York')
    await user.click(screen.getByRole('button', { name: /Continue/ }))
    await user.type(screen.getByLabelText('Username'), 'admin')
    await user.type(screen.getByLabelText('Password'), 'AdminPassw0rd!!')
    await user.type(screen.getByLabelText('Confirm Password'), 'AdminPassw0rd!!')
    await user.type(screen.getByLabelText('Install Token'), 'the-install-token')
    await user.click(screen.getByRole('button', { name: /Create Account/ }))

    await waitFor(() => expect(setupBody).not.toBeNull())
    expect(setupBody.timezone).toBe('America/New_York')
  })

  it('asks for the typed confirmation when a restore would remove held items', async () => {
    const seen = []
    server.use(http.post('/api/backup/import', async ({ request }) => {
      const body = await request.text()
      const confirmed = body.includes('name="confirm_holds"') && body.includes('RESTORE HELD ITEMS')
      seen.push(confirmed)
      if (!confirmed) {
        return HttpResponse.json({
          held_items: [{ type: 'photo', id: 4, title: 'Scene photo' }],
          confirm_text: 'RESTORE HELD ITEMS',
        }, { status: 409 })
      }
      return HttpResponse.json({ ok: true, rows_imported: 3, tables_imported: 1, files_restored: 0 })
    }))
    const { user } = renderWithProviders(<SetupPage />, { route: '/setup' })
    await user.click(screen.getByRole('button', { name: /Restore from a backup instead/ }))
    const file = new File(['PK'], 'backup.zip', { type: 'application/zip' })
    await user.upload(document.querySelector('input[type="file"][accept=".zip"]'), file)
    await user.type(screen.getByLabelText('Install Token'), 'tok')
    await user.click(screen.getByRole('button', { name: 'Restore Backup' }))

    expect(await screen.findByText(/Scene photo/)).toBeInTheDocument()
    const restore = screen.getByRole('button', { name: 'Restore Backup' })
    expect(restore).toBeDisabled()
    await user.type(screen.getByLabelText(/Type/), 'RESTORE HELD ITEMS')
    await user.click(restore)

    expect(await screen.findByText('Restore complete!')).toBeInTheDocument()
    expect(seen).toEqual([false, true])
  })

  it('clears the held-item list and typed confirmation when another file is chosen', async () => {
    server.use(http.post('/api/backup/import', () => HttpResponse.json({
      held_items: [{ type: 'photo', id: 4, title: 'Scene photo' }],
      confirm_text: 'RESTORE HELD ITEMS',
    }, { status: 409 })))
    const { user } = renderWithProviders(<SetupPage />, { route: '/setup' })
    await user.click(screen.getByRole('button', { name: /Restore from a backup instead/ }))
    const input = document.querySelector('input[type="file"][accept=".zip"]')
    await user.upload(input, new File(['PK'], 'one.zip', { type: 'application/zip' }))
    await user.type(screen.getByLabelText('Install Token'), 'tok')
    await user.click(screen.getByRole('button', { name: 'Restore Backup' }))
    await user.type(await screen.findByLabelText(/Type/), 'RESTORE HELD ITEMS')

    await user.upload(input, new File(['PK2'], 'two.zip', { type: 'application/zip' }))

    expect(screen.queryByText(/Scene photo/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/Type/)).not.toBeInTheDocument()
  })
})
