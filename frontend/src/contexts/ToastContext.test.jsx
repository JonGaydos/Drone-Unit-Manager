import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, renderHook, act, screen, fireEvent } from '@testing-library/react'
import { ToastProvider, useToast } from '@/contexts/ToastContext'

afterEach(() => {
  vi.useRealTimers()
})

describe('useToast API', () => {
  it('returns success, error, warning, and info functions', () => {
    const { result } = renderHook(() => useToast(), { wrapper: ToastProvider })
    expect(typeof result.current.success).toBe('function')
    expect(typeof result.current.error).toBe('function')
    expect(typeof result.current.warning).toBe('function')
    expect(typeof result.current.info).toBe('function')
  })
})

/** Render a consumer that fires a toast of the given type on demand. */
function Harness({ method = 'success', message = 'Saved' }) {
  const toast = useToast()
  return <button onClick={() => toast[method](message)}>fire</button>
}

function renderHarness(props) {
  return render(
    <ToastProvider>
      <Harness {...props} />
    </ToastProvider>,
  )
}

describe('showing toasts', () => {
  it.each(['success', 'error', 'warning', 'info'])(
    'renders the message text for a %s toast',
    (method) => {
      renderHarness({ method, message: `${method} message` })
      fireEvent.click(screen.getByText('fire'))
      expect(screen.getByText(`${method} message`)).toBeInTheDocument()
    },
  )
})

describe('auto-dismiss', () => {
  it('removes the toast after the 5000ms default duration', () => {
    vi.useFakeTimers()
    renderHarness({ message: 'Auto gone' })

    fireEvent.click(screen.getByText('fire'))
    expect(screen.getByText('Auto gone')).toBeInTheDocument()

    // Just before the timeout it is still present.
    act(() => {
      vi.advanceTimersByTime(4999)
    })
    expect(screen.getByText('Auto gone')).toBeInTheDocument()

    // At 5000ms total it auto-dismisses.
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.queryByText('Auto gone')).not.toBeInTheDocument()
  })
})

describe('manual dismiss', () => {
  it('removes the toast when its close button is clicked', () => {
    renderHarness({ message: 'Close me' })

    fireEvent.click(screen.getByText('fire'))
    expect(screen.getByText('Close me')).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('Close'))
    expect(screen.queryByText('Close me')).not.toBeInTheDocument()
  })
})
