import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '@/test/render'
import UserManualPage from './UserManualPage'

// UserManualPage is STATIC: all content is hard-coded; no API calls. Baseline
// b/c/d (loading/empty/error) do not apply. Assert static content plus the
// client-side search filter behavior.

describe('UserManualPage', () => {
  it('renders the manual heading and section content', () => {
    renderWithProviders(<UserManualPage />, { route: '/manual' })
    expect(screen.getByRole('heading', { name: 'User Manual' })).toBeInTheDocument()
    // Sections start expanded, so nested section headings are visible.
    expect(screen.getByRole('heading', { name: 'Getting Started' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Dashboard' })).toBeInTheDocument()
  })

  it('filters sections by the search box', async () => {
    const { user } = renderWithProviders(<UserManualPage />, { route: '/manual' })
    await user.type(screen.getByPlaceholderText('Search manual...'), 'airspace')

    expect(screen.getByRole('heading', { name: 'Airspace (ADS-B)' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Getting Started' })).toBeNull()
  })

  it('shows the no-match message when search matches nothing', async () => {
    const { user } = renderWithProviders(<UserManualPage />, { route: '/manual' })
    await user.type(screen.getByPlaceholderText('Search manual...'), 'zzzznotathing')
    expect(screen.getByText('No sections match your search.')).toBeInTheDocument()
  })
})
