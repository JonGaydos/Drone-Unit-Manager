import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import { TopBar } from './TopBar'

// Changing the theme PATCHes /api/auth/me; mock it so the click does not hit
// an unhandled request.
beforeEach(() => {
  server.use(http.patch('/api/auth/me', () => HttpResponse.json({ ok: true })))
})

describe('TopBar', () => {
  it('renders the page title', () => {
    renderWithProviders(<TopBar title="Fleet Management" />)
    expect(screen.getByRole('heading', { name: 'Fleet Management' })).toBeInTheDocument()
  })

  it('the search button dispatches the open-command-palette event', async () => {
    const onOpen = vi.fn()
    globalThis.addEventListener('open-command-palette', onOpen)
    try {
      const { user } = renderWithProviders(<TopBar title="Dashboard" />)
      await user.click(screen.getByRole('button', { name: 'Open search' }))
      expect(onOpen).toHaveBeenCalledTimes(1)
    } finally {
      globalThis.removeEventListener('open-command-palette', onOpen)
    }
  })

  it('opens the theme menu and switches the active theme', async () => {
    const { user } = renderWithProviders(<TopBar title="Dashboard" />)

    // Default theme is "Sandstone"; its name shows on the trigger.
    const trigger = screen.getByRole('button', { name: /Sandstone/ })
    await user.click(trigger)

    // Theme options appear in the dropdown.
    const lightOption = screen.getByRole('button', { name: 'Light' })
    await user.click(lightOption)

    // Selecting a theme persists it and updates the document attribute.
    expect(localStorage.getItem('theme')).toBe('light')
    expect(document.documentElement.dataset.theme).toBe('light')
  })
})
