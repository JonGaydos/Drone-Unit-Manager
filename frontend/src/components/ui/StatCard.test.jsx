import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Plane } from 'lucide-react'
import { StatCard } from './StatCard'

describe('StatCard', () => {
  it('renders the title and value', () => {
    render(<StatCard title="Active Drones" value={12} />)
    expect(screen.getByText('Active Drones')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
  })

  it('renders the subtitle when provided', () => {
    render(<StatCard title="T" value={5} subtitle="+3 this week" />)
    expect(screen.getByText('+3 this week')).toBeInTheDocument()
  })

  it('renders a zero value', () => {
    render(<StatCard title="Idle" value={0} />)
    expect(screen.getByText('0')).toBeInTheDocument()
  })

  it('renders the icon when supplied', () => {
    const { container } = render(<StatCard title="T" value={1} icon={Plane} />)
    // lucide icons render as <svg>; with an icon present there is at least one.
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  it('renders no svg when no icon or trend is supplied', () => {
    const { container } = render(<StatCard title="T" value={1} />)
    expect(container.querySelector('svg')).not.toBeInTheDocument()
  })

  it('renders the trend icon for a trend value', () => {
    const { container } = render(<StatCard title="T" value={1} trend="up" subtitle="up" />)
    expect(container.querySelector('svg')).toBeInTheDocument()
  })
})
