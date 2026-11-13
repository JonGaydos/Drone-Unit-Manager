import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import TopicView from './TopicView'

const section = { id: 'a', title: 'Alpha' }
const topicWith = (id, src) => ({
  id,
  title: `Topic ${id}`,
  summary: 'Summary.',
  image: { src, alt: `Picture ${id}`, caption: `Caption ${id}` },
})

describe('TopicView', () => {
  it('replaces the picture element when the topic changes, so the old picture never shows under the new topic', () => {
    const { rerender } = render(<TopicView section={section} topic={topicWith('one', '/manual-pictures/one.png')} />)
    const first = screen.getByRole('img', { name: 'Picture one' })

    rerender(<TopicView section={section} topic={topicWith('two', '/manual-pictures/two.png')} />)
    const second = screen.getByRole('img', { name: 'Picture two' })

    expect(second).not.toBe(first)
    expect(first.isConnected).toBe(false)
  })
})
