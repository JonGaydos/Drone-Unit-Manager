import { describe, it, expect } from 'vitest'
import { existsSync } from 'node:fs'
import path from 'node:path'
import { cwd } from 'node:process'
import { sections } from './content'

const publicDir = path.resolve(cwd(), 'public')
const topics = sections.flatMap(s => s.topics.map(t => ({ section: s, topic: t })))
const EM_DASH = '—'

describe('manual content', () => {
  it('has unique section ids', () => {
    const ids = sections.map(s => s.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('has unique topic ids within each section', () => {
    for (const s of sections) {
      const ids = s.topics.map(t => t.id)
      expect(new Set(ids).size, s.id).toBe(ids.length)
    }
  })

  it('gives every topic a title and summary', () => {
    for (const { section, topic } of topics) {
      expect(topic.title?.trim(), `${section.id}.${topic.id} title`).toBeTruthy()
      expect(topic.summary?.trim(), `${section.id}.${topic.id} summary`).toBeTruthy()
    }
  })

  it('contains no em dashes', () => {
    for (const s of sections) {
      expect(s.title, s.id).not.toContain(EM_DASH)
      for (const t of s.topics) {
        const parts = [t.title, t.summary, ...(t.steps || []), ...(t.notes || []), t.image?.alt, t.image?.caption]
        for (const part of parts) {
          expect(part || '', `${s.id}.${t.id}`).not.toContain(EM_DASH)
        }
      }
    }
  })

  it('points every image at an existing file under /manual/ with alt text and a caption', () => {
    for (const { section, topic } of topics) {
      if (!topic.image) continue
      const name = `${section.id}.${topic.id}`
      expect(topic.image.src.startsWith('/manual-pictures/'), name).toBe(true)
      expect(existsSync(path.join(publicDir, topic.image.src)), `${name} file`).toBe(true)
      expect(topic.image.alt?.trim(), `${name} alt`).toBeTruthy()
      expect(topic.image.caption?.trim(), `${name} caption`).toBeTruthy()
    }
  })
})
