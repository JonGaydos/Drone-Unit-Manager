import { describe, it, expect, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { ThemeProvider, useTheme, THEMES } from '@/contexts/ThemeContext'

afterEach(() => {
  // The provider writes data-theme on the root; reset it so later suites that
  // inspect the document start clean.
  delete document.documentElement.dataset.theme
})

function renderTheme() {
  return renderHook(() => useTheme(), { wrapper: ThemeProvider })
}

describe('useTheme guard', () => {
  it('throws when called outside a ThemeProvider', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => renderHook(() => useTheme())).toThrow(
      'useTheme must be used within ThemeProvider',
    )
    spy.mockRestore()
  })
})

describe('default theme', () => {
  it('defaults to "dark" when nothing is stored', () => {
    const { result } = renderTheme()
    expect(result.current.theme).toBe('dark')
  })

  it('initializes from localStorage when a theme is stored', () => {
    localStorage.setItem('theme', 'glass')
    const { result } = renderTheme()
    expect(result.current.theme).toBe('glass')
  })

  it('applies the theme to the document root and persists it on mount', () => {
    renderTheme()
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('theme')).toBe('dark')
  })
})

describe('setTheme', () => {
  it('updates the value, the document attribute, and localStorage', async () => {
    server.use(http.patch('/api/auth/me', () => HttpResponse.json({})))
    const { result } = renderTheme()

    await act(async () => {
      await result.current.setTheme('light')
    })

    expect(result.current.theme).toBe('light')
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(localStorage.getItem('theme')).toBe('light')
  })

  it('PATCHes /api/auth/me with the new theme', async () => {
    let body = null
    server.use(http.patch('/api/auth/me', async ({ request }) => {
      body = await request.json()
      return HttpResponse.json({})
    }))
    const { result } = renderTheme()

    await act(async () => {
      await result.current.setTheme('grafana')
    })

    expect(body).toEqual({ theme: 'grafana' })
  })

  it('still updates the theme when the PATCH fails (not logged in)', async () => {
    // The source swallows PATCH errors so a logged-out user can still theme.
    server.use(http.patch('/api/auth/me', () => new HttpResponse(null, { status: 401 })))
    const { result } = renderTheme()

    await act(async () => {
      await result.current.setTheme('blue')
    })

    expect(result.current.theme).toBe('blue')
    expect(localStorage.getItem('theme')).toBe('blue')
  })
})


/** Read the stylesheet that defines the themes, for structural assertions. */
async function readIndexCss() {
  // Vitest runs from the frontend package root, and import.meta.url is not a
  // file URL after transform, so resolve from cwd instead.
  const { readFile } = await import('node:fs/promises')
  return readFile('src/index.css', 'utf8')
}

/** Relative luminance of a #rrggbb colour. */
function luminance(hex) {
  const h = hex.replace('#', '')
  const [r, g, b] = [0, 2, 4].map(i => Number.parseInt(h.slice(i, i + 2), 16))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

describe('THEMES export', () => {
  it('lists the fourteen available theme ids', () => {
    expect(THEMES.map(t => t.id)).toEqual([
      'dark', 'light', 'glass', 'grafana', 'blue', 'high-contrast',
      'midnight-slate', 'ranger-green', 'navy-brass', 'arctic',
      'carbon-amber', 'night-vision', 'sandstone', 'field-sage',
    ])
  })

  it('every registered theme has a stylesheet block behind it', async () => {
    // A theme in the picker with no CSS silently falls back to the dark
    // defaults, which looks like the picker being broken.
    const css = await readIndexCss()
    for (const { id } of THEMES) {
      const declared = id === 'dark'
        ? css.includes(':root, [data-theme="dark"]')
        : css.includes(`[data-theme="${id}"]`)
      expect(declared, `no CSS block for theme "${id}"`).toBe(true)
    }
  })

  it('keeps the sidebar visibly distinct from the working area', async () => {
    // The complaint that started this: nearly every theme had a sidebar within
    // a few luminance points of the background, so chrome and content read as
    // one flat surface. Under ~8 is not perceptible on a normal display.
    //
    // Exempt on purpose: "glass" uses translucent rgba surfaces, and
    // "high-contrast" pins pure black against pure white as an accessibility
    // contract rather than an oversight.
    const EXEMPT = new Set(['glass', 'high-contrast'])
    const css = await readIndexCss()

    const tooFlat = []
    for (const { id } of THEMES) {
      if (EXEMPT.has(id)) continue
      // Plain string scanning rather than a built regex: in a template literal
      // "\[" collapses to "[", which silently turns the selector into a
      // character class and matches nothing.
      const selector = id === 'dark' ? ':root, [data-theme="dark"]' : `[data-theme="${id}"]`
      const at = css.indexOf(selector)
      expect(at, `no CSS block for "${id}"`).toBeGreaterThan(-1)
      const open = css.indexOf('{', at)
      const body = css.slice(open + 1, css.indexOf('}', open))

      const pick = (name) => {
        const line = body.split('\n').find(l => l.trim().startsWith(`--${name}:`))
        const m = line && /(#[0-9a-fA-F]{6})/.exec(line)
        return m ? m[1] : null
      }
      const sidebar = pick('sidebar')
      const bg = pick('bg')
      if (!sidebar || !bg) continue
      const delta = Math.abs(luminance(bg) - luminance(sidebar))
      if (delta < 8) tooFlat.push(`${id} (${delta.toFixed(1)})`)
    }

    expect(tooFlat, `themes whose chrome is indistinguishable: ${tooFlat.join(', ')}`).toEqual([])
  })
})
