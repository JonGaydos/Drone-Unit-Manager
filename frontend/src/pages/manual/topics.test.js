import { describe, it, expect } from 'vitest'
import { topicKey, flattenTopics, findTopic, neighbors, topicText, filterSections } from './topics'

const fixture = [
  {
    id: 'a',
    title: 'Alpha',
    topics: [
      { id: 'one', title: 'One', summary: 'First topic.' },
      { id: 'two', title: 'Two', summary: 'Second topic.', steps: ['Do a Step here'], notes: ['A note'] },
    ],
  },
  {
    id: 'b',
    title: 'Beta',
    topics: [{ id: 'three', title: 'Three', summary: 'Third topic.' }],
  },
]

describe('topics helpers', () => {
  it('builds a topic key', () => {
    expect(topicKey('flights', 'adding-a-flight')).toBe('flights.adding-a-flight')
  })

  it('flattens topics in manual order', () => {
    expect(flattenTopics(fixture).map(e => e.key)).toEqual(['a.one', 'a.two', 'b.three'])
  })

  it('finds a topic by key', () => {
    expect(findTopic(fixture, 'b.three').topic.title).toBe('Three')
    expect(findTopic(fixture, 'x.y')).toBeNull()
  })

  it('returns neighbors', () => {
    const first = neighbors(fixture, 'a.one')
    expect(first.prev).toBeNull()
    expect(first.next.key).toBe('a.two')
    expect(neighbors(fixture, 'b.three').next).toBeNull()
  })

  it('joins topic text in lower case', () => {
    const text = topicText(fixture[0].topics[1])
    expect(text).toContain('two')
    expect(text).toContain('do a step here')
    expect(text).toContain('a note')
  })

  it('filters sections by trimmed, lower-cased query', () => {
    const result = filterSections(fixture, '  STEP  ')
    expect(result).toHaveLength(1)
    expect(result[0].topics.map(t => t.id)).toEqual(['two'])
  })

  it('returns the fixture for an empty query', () => {
    expect(filterSections(fixture, '')).toBe(fixture)
  })
})
