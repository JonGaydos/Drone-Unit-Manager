import { describe, it, expect, vi } from 'vitest'
import { interactiveProps } from '@/lib/a11y'

describe('interactiveProps', () => {
  it('returns button role, tabIndex 0, the onClick, and an onKeyDown handler', () => {
    const onClick = vi.fn()
    const props = interactiveProps(onClick)
    expect(props.role).toBe('button')
    expect(props.tabIndex).toBe(0)
    expect(props.onClick).toBe(onClick)
    expect(typeof props.onKeyDown).toBe('function')
  })

  it('fires the handler and prevents default on Enter', () => {
    const onClick = vi.fn()
    const preventDefault = vi.fn()
    interactiveProps(onClick).onKeyDown({ key: 'Enter', preventDefault })
    expect(onClick).toHaveBeenCalledTimes(1)
    expect(preventDefault).toHaveBeenCalledTimes(1)
  })

  it('fires the handler and prevents default on Space', () => {
    const onClick = vi.fn()
    const preventDefault = vi.fn()
    interactiveProps(onClick).onKeyDown({ key: ' ', preventDefault })
    expect(onClick).toHaveBeenCalledTimes(1)
    expect(preventDefault).toHaveBeenCalledTimes(1)
  })

  it('passes the event object to the handler', () => {
    const onClick = vi.fn()
    const event = { key: 'Enter', preventDefault: vi.fn() }
    interactiveProps(onClick).onKeyDown(event)
    expect(onClick).toHaveBeenCalledWith(event)
  })

  it('does not fire the handler for other keys', () => {
    const onClick = vi.fn()
    const preventDefault = vi.fn()
    interactiveProps(onClick).onKeyDown({ key: 'a', preventDefault })
    expect(onClick).not.toHaveBeenCalled()
    expect(preventDefault).not.toHaveBeenCalled()
  })
})
