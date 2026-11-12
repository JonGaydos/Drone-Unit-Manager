export function topicKey(sectionId, topicId) {
  return `${sectionId}.${topicId}`
}

export function flattenTopics(sections) {
  return sections.flatMap(section =>
    section.topics.map(topic => ({ key: topicKey(section.id, topic.id), section, topic }))
  )
}

export function findTopic(sections, key) {
  return flattenTopics(sections).find(entry => entry.key === key) || null
}

export function neighbors(sections, key) {
  const all = flattenTopics(sections)
  const i = all.findIndex(entry => entry.key === key)
  if (i === -1) return { prev: null, next: null }
  return { prev: all[i - 1] || null, next: all[i + 1] || null }
}

export function topicText(topic) {
  return [topic.title, topic.summary, ...(topic.steps || []), ...(topic.notes || [])]
    .filter(Boolean)
    .join('\n')
    .toLowerCase()
}

export function filterSections(sections, query) {
  const q = (query || '').trim().toLowerCase()
  if (!q) return sections
  return sections
    .map(section => {
      if (section.title.toLowerCase().includes(q)) return section
      return { ...section, topics: section.topics.filter(t => topicText(t).includes(q)) }
    })
    .filter(section => section.topics.length > 0)
}
