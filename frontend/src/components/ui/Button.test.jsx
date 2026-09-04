import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Button, buttonVariants } from './Button'

describe('Button', () => {
  it('renders its children as a button element', () => {
    render(<Button>Launch</Button>)
    const btn = screen.getByRole('button', { name: 'Launch' })
    expect(btn).toBeInTheDocument()
    expect(btn.tagName).toBe('BUTTON')
  })

  it('fires onClick on click', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Go</Button>)
    await user.click(screen.getByRole('button', { name: 'Go' }))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('disabled prevents onClick and applies disabled state', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    render(<Button disabled onClick={onClick}>Nope</Button>)
    const btn = screen.getByRole('button', { name: 'Nope' })
    expect(btn).toBeDisabled()
    await user.click(btn)
    expect(onClick).not.toHaveBeenCalled()
  })

  it('applies a distinct class per variant', () => {
    const variants = Object.keys(buttonVariants)
    expect(variants).toEqual(['default', 'secondary', 'destructive', 'outline', 'ghost'])
    const classByVariant = {}
    for (const v of variants) {
      const { unmount } = render(<Button variant={v}>{v}</Button>)
      classByVariant[v] = screen.getByRole('button', { name: v }).className
      unmount()
    }
    // destructive vs default vs outline differ
    expect(classByVariant.destructive).toContain('bg-destructive')
    expect(classByVariant.secondary).toContain('bg-secondary')
    expect(classByVariant.outline).toContain('border')
    expect(classByVariant.default).toContain('bg-primary')
    expect(classByVariant.ghost).not.toEqual(classByVariant.default)
  })

  it('forwards a ref to the underlying button', () => {
    const ref = { current: null }
    render(<Button ref={ref}>R</Button>)
    expect(ref.current).toBeInstanceOf(HTMLButtonElement)
  })
})
