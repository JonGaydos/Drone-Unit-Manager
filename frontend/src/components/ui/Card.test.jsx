import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from './Card'

describe('Card', () => {
  it('renders its children', () => {
    render(<Card>Body content</Card>)
    expect(screen.getByText('Body content')).toBeInTheDocument()
  })

  it('renders header, title, description, content, and footer', () => {
    render(
      <Card>
        <CardHeader>
          <CardTitle>Pilot details</CardTitle>
          <CardDescription>Subtitle text</CardDescription>
        </CardHeader>
        <CardContent>Main body</CardContent>
        <CardFooter>Footer</CardFooter>
      </Card>,
    )
    expect(screen.getByRole('heading', { name: 'Pilot details' })).toBeInTheDocument()
    expect(screen.getByText('Subtitle text')).toBeInTheDocument()
    expect(screen.getByText('Main body')).toBeInTheDocument()
    expect(screen.getByText('Footer')).toBeInTheDocument()
  })

  it('forwards a ref and passes through props', () => {
    const ref = { current: null }
    render(<Card ref={ref} data-testid="card">x</Card>)
    expect(ref.current).toBeInstanceOf(HTMLDivElement)
    expect(screen.getByTestId('card')).toBeInTheDocument()
  })
})
