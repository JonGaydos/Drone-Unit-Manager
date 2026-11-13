import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { screen, within } from '@testing-library/react'
import { renderWithProviders } from '@/test/render'
import UserManualPage from './UserManualPage'
import { sections } from './manual/content'
import { flattenTopics, topicText } from './manual/topics'

// UserManualPage is STATIC: no API calls. Titles and keys come from the real
// content so a later content rewrite does not break these tests.

const all = flattenTopics(sections)
const first = all[0]
const wordsOf = text => text.match(/[a-z]{6,}/g) || []
const sectionText = s => [s.title, ...s.topics.map(t => topicText(t))].join('\n').toLowerCase()

// A word found in the text of exactly one topic and in no section title.
function wordOnlyInOneTopic() {
  const titles = sections.map(s => s.title.toLowerCase()).join('\n')
  for (const entry of all.slice(1)) {
    for (const word of wordsOf(topicText(entry.topic))) {
      const hits = all.filter(e => topicText(e.topic).includes(word))
      if (hits.length === 1 && !titles.includes(word)) return { word, entry }
    }
  }
  throw new Error('no topic-specific word found')
}

// A word found in the text of exactly one section.
function wordOnlyInOneSection() {
  for (const section of sections) {
    for (const word of wordsOf(sectionText(section))) {
      const hits = sections.filter(s => sectionText(s).includes(word))
      if (hits.length === 1) return { word, section }
    }
  }
  throw new Error('no section-specific word found')
}

const searchBox = () => screen.getByPlaceholderText('Search the manual...')

describe('UserManualPage', () => {
  beforeEach(() => {
    window.scrollTo = vi.fn()
  })

  afterEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('renders the manual heading, subtitle and layout switch', () => {
    renderWithProviders(<UserManualPage />, { route: '/manual' })
    expect(screen.getByRole('heading', { name: 'User Manual' })).toBeInTheDocument()
    expect(screen.getByText('How to use Drone Unit Manager')).toBeInTheDocument()
    const group = screen.getByRole('group', { name: 'Manual layout' })
    expect(within(group).getByRole('button', { name: 'Topics' })).toHaveAttribute('aria-pressed', 'true')
    expect(within(group).getByRole('button', { name: 'One page' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('starts in Topics view showing only the first topic', () => {
    renderWithProviders(<UserManualPage />, { route: '/manual' })
    const h2s = screen.getAllByRole('heading', { level: 2 })
    expect(h2s).toHaveLength(1)
    expect(h2s[0]).toHaveTextContent(first.topic.title)
  })

  it('switches to One page, stores the choice and starts there next time', async () => {
    const { user, unmount } = renderWithProviders(<UserManualPage />, { route: '/manual' })
    await user.click(screen.getByRole('button', { name: 'One page' }))

    for (const s of sections.slice(0, 3)) {
      expect(screen.getByRole('button', { name: s.title })).toBeInTheDocument()
    }
    expect(localStorage.getItem('dum.manual.view')).toBe('page')
    unmount()

    renderWithProviders(<UserManualPage />, { route: '/manual' })
    expect(screen.getByRole('button', { name: 'One page' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: sections[1].title })).toBeInTheDocument()
  })

  it('opens the topic named in the address in Topics view even when One page is stored', () => {
    localStorage.setItem('dum.manual.view', 'page')
    const target = all[all.length - 1]
    renderWithProviders(<UserManualPage />, { route: `/manual?topic=${target.key}` })

    expect(screen.getByRole('button', { name: 'Topics' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent(target.topic.title)
    expect(localStorage.getItem('dum.manual.view')).toBe('topics')
  })

  it('shows the first topic for an unknown topic address', () => {
    renderWithProviders(<UserManualPage />, { route: '/manual?topic=nope.nope' })
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent(first.topic.title)
  })

  it('shows the topic that holds a searched word', async () => {
    const { word, entry } = wordOnlyInOneTopic()
    const { user } = renderWithProviders(<UserManualPage />, { route: '/manual' })
    await user.type(searchBox(), word)
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent(entry.topic.title)
  })

  it('shows the no-match message when search matches nothing', async () => {
    const { user } = renderWithProviders(<UserManualPage />, { route: '/manual' })
    await user.type(searchBox(), 'zzzznotathing')
    expect(screen.getByText('No topics match your search.')).toBeInTheDocument()
  })

  it('hides other sections in One page view when searching', async () => {
    const { word, section } = wordOnlyInOneSection()
    localStorage.setItem('dum.manual.view', 'page')
    const { user } = renderWithProviders(<UserManualPage />, { route: '/manual' })
    await user.type(searchBox(), word)

    expect(screen.getByRole('button', { name: section.title })).toBeInTheDocument()
    const other = sections.find(s => s.id !== section.id)
    expect(screen.queryByRole('button', { name: other.title })).toBeNull()
  })

  it('shows matching topics from several sections open in the menu while searching', async () => {
    const titles = sections.map(sec => sec.title.toLowerCase()).join(' ')
    let pick = null
    for (const entry of all) {
      for (const word of wordsOf(topicText(entry.topic))) {
        if (titles.includes(word)) continue
        const hits = all.filter(e => topicText(e.topic).includes(word))
        const secs = new Set(hits.map(e => e.section.id))
        if (secs.size === 2 && hits.length <= 6) { pick = { word, hits }; break }
      }
      if (pick) break
    }
    expect(pick).not.toBeNull()
    const { user } = renderWithProviders(<UserManualPage />, { route: '/manual' })
    await user.type(searchBox(), pick.word)
    const menu = screen.getByRole('navigation', { name: 'Manual topics' })
    for (const e of pick.hits) {
      expect(within(menu).getByRole('button', { name: e.topic.title })).toBeInTheDocument()
    }
  })

  it('scrolls to the top when the topic changes', async () => {
    const scroll = vi.fn()
    window.scrollTo = scroll
    const { user } = renderWithProviders(<UserManualPage />, { route: '/manual' })
    expect(scroll).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: /^Next: / }))
    expect(scroll).toHaveBeenCalled()
  })

  it('still renders in Topics view and switches when storage throws', async () => {
    // Only the manual's own key is blocked so the theme and auth providers still mount.
    const realGet = Storage.prototype.getItem
    const realSet = Storage.prototype.setItem
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(function (key) {
      if (key === 'dum.manual.view') throw new Error('blocked')
      return realGet.call(this, key)
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(function (key, value) {
      if (key === 'dum.manual.view') throw new Error('blocked')
      return realSet.call(this, key, value)
    })
    const { user } = renderWithProviders(<UserManualPage />, { route: '/manual' })

    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent(first.topic.title)
    await user.click(screen.getByRole('button', { name: 'One page' }))
    expect(screen.getByRole('button', { name: 'One page' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: sections[1].title })).toBeInTheDocument()
  })
})
