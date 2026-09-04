import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PageErrorBoundary } from './PageErrorBoundary'

function Boom({ message = 'kaboom' }) {
  throw new Error(message)
}

describe('PageErrorBoundary', () => {
  let errorSpy
  beforeEach(() => {
    // React logs the caught error to console.error; silence the expected noise.
    errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
  })
  afterEach(() => {
    errorSpy.mockRestore()
  })

  it('renders children when nothing throws', () => {
    render(
      <PageErrorBoundary>
        <p>Healthy content</p>
      </PageErrorBoundary>,
    )
    expect(screen.getByText('Healthy content')).toBeInTheDocument()
  })

  it('renders the fallback UI with the error message when a child throws', () => {
    render(
      <PageErrorBoundary>
        <Boom message="render failed" />
      </PageErrorBoundary>,
    )
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    expect(screen.getByText('render failed')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try Again' })).toBeInTheDocument()
  })

  it('resets error state when "Try Again" is clicked', async () => {
    const user = userEvent.setup()
    // After reset the boundary re-renders children; swap to a healthy child so
    // it does not immediately re-throw.
    let shouldThrow = true
    function Child() {
      if (shouldThrow) throw new Error('first render')
      return <p>Recovered</p>
    }
    render(
      <PageErrorBoundary>
        <Child />
      </PageErrorBoundary>,
    )
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    shouldThrow = false
    await user.click(screen.getByRole('button', { name: 'Try Again' }))
    expect(screen.getByText('Recovered')).toBeInTheDocument()
    expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument()
  })
})
