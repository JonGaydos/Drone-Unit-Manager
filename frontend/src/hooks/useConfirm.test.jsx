import { describe, it, expect, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useConfirm } from '@/hooks/useConfirm'

describe('useConfirm initial state', () => {
  it('starts closed with default ConfirmDialog props', () => {
    const { result } = renderHook(() => useConfirm())
    const [props] = result.current
    expect(props.open).toBe(false)
    // Initial state title/message are empty strings; the 'Confirm' /
    // 'Are you sure?' defaults only fill in via requestConfirm.
    expect(props.title).toBe('')
    expect(props.message).toBe('')
    expect(props.confirmLabel).toBe('Confirm')
    expect(props.confirmVariant).toBe('danger')
    // onConfirm/onClose are always callable (onConfirm defaults to a no-op).
    expect(typeof props.onConfirm).toBe('function')
    expect(typeof props.onClose).toBe('function')
  })
})

describe('requestConfirm', () => {
  it('opens the dialog and applies the supplied fields', () => {
    const onConfirm = vi.fn()
    const { result } = renderHook(() => useConfirm())

    act(() => {
      const [, requestConfirm] = result.current
      requestConfirm({
        title: 'Delete pilot',
        message: 'This cannot be undone.',
        confirmLabel: 'Delete',
        confirmVariant: 'warning',
        onConfirm,
      })
    })

    const [props] = result.current
    expect(props.open).toBe(true)
    expect(props.title).toBe('Delete pilot')
    expect(props.message).toBe('This cannot be undone.')
    expect(props.confirmLabel).toBe('Delete')
    expect(props.confirmVariant).toBe('warning')
    expect(props.onConfirm).toBe(onConfirm)
  })

  it('falls back to defaults for omitted fields', () => {
    const { result } = renderHook(() => useConfirm())

    act(() => {
      const [, requestConfirm] = result.current
      requestConfirm({ onConfirm: () => {} })
    })

    const [props] = result.current
    expect(props.open).toBe(true)
    expect(props.title).toBe('Confirm')
    expect(props.message).toBe('Are you sure?')
    expect(props.confirmLabel).toBe('Confirm')
    expect(props.confirmVariant).toBe('danger')
  })
})

describe('confirm and cancel', () => {
  it('invoking props.onConfirm runs the requested callback', () => {
    const onConfirm = vi.fn()
    const { result } = renderHook(() => useConfirm())

    act(() => {
      const [, requestConfirm] = result.current
      requestConfirm({ title: 't', message: 'm', onConfirm })
    })
    act(() => {
      result.current[0].onConfirm()
    })
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('onClose closes the dialog without invoking onConfirm', () => {
    const onConfirm = vi.fn()
    const { result } = renderHook(() => useConfirm())

    act(() => {
      const [, requestConfirm] = result.current
      requestConfirm({ title: 't', message: 'm', onConfirm })
    })
    expect(result.current[0].open).toBe(true)

    act(() => {
      result.current[0].onClose()
    })
    expect(result.current[0].open).toBe(false)
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('onConfirm is a safe no-op when no callback was supplied', () => {
    const { result } = renderHook(() => useConfirm())
    // Default state has onConfirm: null, surfaced as a no-op function.
    expect(() => act(() => result.current[0].onConfirm())).not.toThrow()
  })
})
