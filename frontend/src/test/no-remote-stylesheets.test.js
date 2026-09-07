/**
 * The app's Content-Security-Policy sets style-src 'self' 'unsafe-inline', so
 * any stylesheet pulled from another origin is blocked at load time. That is
 * not a visible error in the bundle -- it only shows up as a broken page in the
 * browser. It happened once: Leaflet's CSS was pulled from unpkg.com via a CSS
 * @import, the CSP blocked it, and every map rendered with mispositioned tiles.
 *
 * This guards the whole class: no source stylesheet or HTML entry may reference
 * a remote stylesheet. Bundle third-party CSS from node_modules instead (e.g.
 * @import "leaflet/dist/leaflet.css"), which Vite serves from 'self'.
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { describe, it, expect } from 'vitest'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '../..')

// A url()/import that points at http(s):// -- i.e. off-origin.
const REMOTE = /@import\s+["']https?:\/\//i
const REMOTE_LINK = /<link[^>]+rel=["']stylesheet["'][^>]*href=["']https?:\/\//i

describe('no remote stylesheets (blocked by CSP style-src self)', () => {
  it('src/index.css imports no stylesheet over http(s)', () => {
    const css = readFileSync(resolve(root, 'src/index.css'), 'utf8')
    const offender = css.split('\n').find((l) => REMOTE.test(l))
    expect(offender, `remote @import in index.css: ${offender}`).toBeUndefined()
  })

  it('index.html links no stylesheet over http(s)', () => {
    const html = readFileSync(resolve(root, 'index.html'), 'utf8')
    expect(REMOTE_LINK.test(html), 'remote <link rel=stylesheet> in index.html').toBe(false)
  })

  it('Leaflet CSS is bundled from the package, so the maps keep their layout', () => {
    const css = readFileSync(resolve(root, 'src/index.css'), 'utf8')
    expect(css).toMatch(/@import\s+["']leaflet\/dist\/leaflet\.css["']/)
  })
})
