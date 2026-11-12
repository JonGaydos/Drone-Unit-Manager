import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import TopicsLayout from './TopicsLayout'

const sections = [
  {
    id: 'a',
    title: 'Alpha',
    topics: [
      { id: 'one', title: 'One', summary: 'First summary.', steps: ['Open the page'], notes: ['Remember this'] },
      { id: 'two', title: 'Two', summary: 'Second summary.' },
    ],
  },
  {
    id: 'b',
    title: 'Beta',
    topics: [
      {
        id: 'three',
        title: 'Three',
        summary: 'Third summary.',
        image: { src: '/manual-pictures/three.png', alt: 'Three screen', caption: 'The three screen' },
      },
    ],
  },
]

function setup(props = {}) {
  const onSelect = vi.fn()
  const utils = render(
    <TopicsLayout sections={sections} currentKey="a.one" onSelect={onSelect} {...props} />
  )
  return { onSelect, ...utils }
}

describe('TopicsLayout', () => {
  it('shows only the current topic', () => {
    setup()
    expect(screen.getByRole('heading', { level: 2, name: 'One' })).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(1)
    expect(screen.getByText(/First summary/)).toBeInTheDocument()
    expect(screen.queryByText(/Second summary/)).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 3, name: 'Steps' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 3, name: 'Good to know' })).toBeInTheDocument()
  })

  it('selects a topic from the side menu', async () => {
    const { onSelect } = setup()
    const menu = screen.getByRole('navigation', { name: 'Manual topics' })
    expect(within(menu).getByRole('button', { name: 'One' })).toHaveAttribute('aria-current', 'page')
    await userEvent.click(within(menu).getByRole('button', { name: 'Beta' }))
    await userEvent.click(within(menu).getByRole('button', { name: 'Three' }))
    expect(onSelect).toHaveBeenCalledWith('b.three')
  })

  it('offers Next but no Previous on the first topic', async () => {
    const { onSelect } = setup()
    expect(screen.queryByRole('button', { name: /^←/ })).not.toBeInTheDocument()
    const next = screen.getByRole('button', { name: 'Next: Two' })
    await userEvent.click(next)
    expect(onSelect).toHaveBeenCalledWith('a.two')
  })

  it('offers Previous on a later topic', async () => {
    const { onSelect } = setup({ currentKey: 'b.three' })
    await userEvent.click(screen.getByRole('button', { name: 'Previous: Two' }))
    expect(onSelect).toHaveBeenCalledWith('a.two')
    expect(screen.queryByRole('button', { name: /→$/ })).not.toBeInTheDocument()
  })

  describe('topic picker', () => {
    const picker = () => screen.getByRole('button', { name: /Alpha › One/ })

    it('opens, selects a topic and closes', async () => {
      const { onSelect } = setup()
      expect(picker()).toHaveAttribute('aria-expanded', 'false')
      await userEvent.click(picker())
      expect(picker()).toHaveAttribute('aria-expanded', 'true')
      const panel = screen.getByRole('region', { name: 'Choose a topic' })
      await userEvent.click(within(panel).getByRole('button', { name: 'Two' }))
      expect(onSelect).toHaveBeenCalledWith('a.two')
      expect(picker()).toHaveAttribute('aria-expanded', 'false')
      expect(screen.queryByRole('region', { name: 'Choose a topic' })).not.toBeInTheDocument()
    })

    it('closes on Escape', async () => {
      setup()
      await userEvent.click(picker())
      await userEvent.keyboard('{Escape}')
      expect(picker()).toHaveAttribute('aria-expanded', 'false')
    })

    it('returns focus to the picker button on Escape', async () => {
      setup()
      await userEvent.click(picker())
      await userEvent.keyboard('{Escape}')
      expect(picker()).toHaveFocus()
    })

    it('closes on a click outside', async () => {
      setup()
      await userEvent.click(picker())
      await userEvent.click(document.body)
      expect(picker()).toHaveAttribute('aria-expanded', 'false')
    })
  })

  it('opens every section in the menu while searching', () => {
    setup({ searching: true })
    const menu = screen.getByRole('navigation', { name: 'Manual topics' })
    expect(within(menu).getByRole('button', { name: 'Two' })).toBeInTheDocument()
    expect(within(menu).getByRole('button', { name: 'Three' })).toBeInTheDocument()
  })

  it('shows an empty message with no sections', () => {
    setup({ sections: [], currentKey: null })
    expect(screen.getByText('No topics match your search.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Previous|Next|←|→/ })).not.toBeInTheDocument()
  })

  it('renders a topic picture', () => {
    setup({ currentKey: 'b.three' })
    const img = screen.getByRole('img', { name: 'Three screen' })
    expect(img).toHaveAttribute('loading', 'lazy')
    expect(screen.getByText('The three screen')).toBeInTheDocument()
  })
})
