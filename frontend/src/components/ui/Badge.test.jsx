import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Badge, badgeVariants } from './Badge'

describe('Badge', () => {
  it('renders its label', () => {
    render(<Badge>Active</Badge>)
    expect(screen.getByText('Active')).toBeInTheDocument()
  })

  it('applies the default variant styling', () => {
    render(<Badge>Def</Badge>)
    expect(screen.getByText('Def').className).toContain('bg-primary')
  })

  it('applies a distinct class per variant', () => {
    expect(Object.keys(badgeVariants)).toEqual([
      'default', 'secondary', 'destructive', 'outline', 'success', 'warning',
    ])
    const classes = {}
    for (const v of Object.keys(badgeVariants)) {
      const { unmount } = render(<Badge variant={v}>{v}</Badge>)
      classes[v] = screen.getByText(v).className
      unmount()
    }
    expect(classes.success).toContain('text-green-600')
    expect(classes.warning).toContain('text-yellow-600')
    expect(classes.destructive).toContain('bg-destructive')
    expect(classes.outline).toContain('border')
  })
})
