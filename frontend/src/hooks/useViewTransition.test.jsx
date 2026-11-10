import { describe, it, expect, afterEach, vi } from 'vitest'
import { renderHook, render, act } from '@testing-library/react'
import { MemoryRouter, useNavigate } from 'react-router-dom'
import { useViewTransition } from '@/hooks/useViewTransition'

// document.startViewTransition is not implemented in jsdom, so the property is
// absent by default. We add/remove it per test and restore in afterEach.
afterEach(() => {
  delete document.startViewTransition
})

function wrapper({ children }) {
  return <MemoryRouter initialEntries={['/start']}>{children}</MemoryRouter>
}

describe('useViewTransition', () => {
  it('calls document.startViewTransition when it exists', () => {
    const startViewTransition = vi.fn((cb) => {
      cb()
      return { finished: Promise.resolve() }
    })
    document.startViewTransition = startViewTransition

    renderHook(() => useViewTransition(), { wrapper })

    expect(startViewTransition).toHaveBeenCalledTimes(1)
    expect(typeof startViewTransition.mock.calls[0][0]).toBe('function')
  })

  it('does not throw and runs no transition when startViewTransition is absent', () => {
    // Ensure the API is undefined (fallback path).
    delete document.startViewTransition
    expect(() =>
      renderHook(() => useViewTransition(), { wrapper }),
    ).not.toThrow()
    expect(document.startViewTransition).toBeUndefined()
  })

  it('fires again on a pathname change', () => {
    const startViewTransition = vi.fn(() => ({ finished: Promise.resolve() }))
    document.startViewTransition = startViewTransition

    // Navigate within the same router so location.pathname changes and the
    // effect's dependency re-fires.
    let navigate
    function Consumer() {
      useViewTransition()
      navigate = useNavigate()
      return null
    }
    render(
      <MemoryRouter initialEntries={['/a']}>
        <Consumer />
      </MemoryRouter>,
    )
    expect(startViewTransition).toHaveBeenCalledTimes(1)

    act(() => {
      navigate('/b')
    })
    expect(startViewTransition).toHaveBeenCalledTimes(2)
  })

  // C-F23, D-16, E-15: a navigation during a running transition skips it, and
  // its promises reject (AbortError, InvalidStateError). Nobody awaited them,
  // so each rejection was logged as uncaught.
  it('handles the rejections of a skipped transition', async () => {
    const unhandled = []
    const onUnhandled = (reason) => unhandled.push(reason)
    process.on('unhandledRejection', onUnhandled)
    const skipped = () => Promise.reject(new DOMException('Transition was skipped', 'AbortError'))
    document.startViewTransition = vi.fn(() => ({
      ready: skipped(), finished: skipped(), updateCallbackDone: skipped(),
    }))
    try {
      renderHook(() => useViewTransition(), { wrapper })
      await new Promise(resolve => setTimeout(resolve, 10))
    } finally {
      process.off('unhandledRejection', onUnhandled)
    }
    expect(unhandled).toEqual([])
  })
})
