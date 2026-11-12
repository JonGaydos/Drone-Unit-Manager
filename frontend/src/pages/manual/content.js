// The manual's text lives in content.json, the one file to edit when the app
// changes. Shape: an array of sections { id, title, topics }, each topic
// { id, title, summary, steps?, notes?, image?: { src, alt, caption } }.
// Labels in **double asterisks** render bold and must match the app exactly.
import sections from './content.json' with { type: 'json' }

export { sections }
