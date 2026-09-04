import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '@/test/render'
import NotFoundPage from './NotFoundPage'

// NotFoundPage is STATIC: no API calls, no async state. Baseline b/c/d
// (loading/empty/error) do not apply; assert the static 404 content instead.

describe('NotFoundPage', () => {
  it('renders the 404 message and a link back to the dashboard', () => {
    renderWithProviders(<NotFoundPage />, { route: '/nope' })
    expect(screen.getByText('404')).toBeInTheDocument()
    expect(screen.getByText("That page doesn't exist.")).toBeInTheDocument()
    const link = screen.getByRole('link', { name: 'Back to dashboard' })
    expect(link).toHaveAttribute('href', '/')
  })
})
