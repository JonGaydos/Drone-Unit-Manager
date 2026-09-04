import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { http, HttpResponse, delay } from 'msw'
import { server } from '@/test/server'
import { api, resetSessionExpired } from '@/api/client'

beforeEach(() => {
  // sessionExpired is module-level state; re-arm it so the 401 guard tests
  // don't contaminate each other.
  resetSessionExpired()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('api verbs', () => {
  it('GET hits /api/<path> and returns parsed JSON', async () => {
    server.use(http.get('/api/things', () => HttpResponse.json({ ok: true })))
    expect(await api.get('/things')).toEqual({ ok: true })
  })

  it('GET sends Authorization when a token is stored', async () => {
    localStorage.setItem('token', 'abc123')
    let auth = null
    server.use(http.get('/api/things', ({ request }) => {
      auth = request.headers.get('Authorization')
      return HttpResponse.json({})
    }))
    await api.get('/things')
    expect(auth).toBe('Bearer abc123')
  })

  it('GET omits Authorization when no token is stored', async () => {
    let auth = 'unset'
    server.use(http.get('/api/things', ({ request }) => {
      auth = request.headers.get('Authorization')
      return HttpResponse.json({})
    }))
    await api.get('/things')
    expect(auth).toBeNull()
  })

  it('POST sends JSON Content-Type + stringified body and returns JSON', async () => {
    let ct = null
    let body = null
    server.use(http.post('/api/things', async ({ request }) => {
      ct = request.headers.get('Content-Type')
      body = await request.json()
      return HttpResponse.json({ id: 7 })
    }))
    const result = await api.post('/things', { name: 'x' })
    expect(ct).toBe('application/json')
    expect(body).toEqual({ name: 'x' })
    expect(result).toEqual({ id: 7 })
  })

  it('PATCH sends JSON Content-Type + stringified body', async () => {
    let ct = null
    let body = null
    server.use(http.patch('/api/things/1', async ({ request }) => {
      ct = request.headers.get('Content-Type')
      body = await request.json()
      return HttpResponse.json({ id: 1 })
    }))
    await api.patch('/things/1', { name: 'y' })
    expect(ct).toBe('application/json')
    expect(body).toEqual({ name: 'y' })
  })

  it('PUT sends JSON Content-Type + stringified body', async () => {
    let ct = null
    let body = null
    server.use(http.put('/api/things/1', async ({ request }) => {
      ct = request.headers.get('Content-Type')
      body = await request.json()
      return HttpResponse.json({ id: 1 })
    }))
    await api.put('/things/1', { name: 'z' })
    expect(ct).toBe('application/json')
    expect(body).toEqual({ name: 'z' })
  })

  it('DELETE uses the DELETE method', async () => {
    let method = null
    server.use(http.delete('/api/things/1', ({ request }) => {
      method = request.method
      return new HttpResponse(null, { status: 204 })
    }))
    await api.delete('/things/1')
    expect(method).toBe('DELETE')
  })
})

describe('401 handling', () => {
  it('throws session-expired, clears credentials, and redirects once across concurrent 401s', async () => {
    // Stub a writable href but keep a real origin so fetch can still resolve
    // the relative /api URL.
    vi.stubGlobal('location', { href: 'http://localhost/', origin: 'http://localhost' })
    localStorage.setItem('token', 'x')
    localStorage.setItem('user', JSON.stringify({ id: 1 }))
    server.use(http.get('/api/secure', () => new HttpResponse(null, { status: 401 })))

    const results = await Promise.allSettled([api.get('/secure'), api.get('/secure')])

    for (const r of results) {
      expect(r.status).toBe('rejected')
      expect(r.reason).toBeInstanceOf(Error)
      expect(r.reason.message).toBe('Session expired. Please log in again.')
    }
    expect(localStorage.getItem('token')).toBeNull()
    expect(localStorage.getItem('user')).toBeNull()
    expect(globalThis.location.href).toBe('/login')
  })

  it('redirects again after resetSessionExpired()', async () => {
    vi.stubGlobal('location', { href: 'http://localhost/', origin: 'http://localhost' })
    server.use(http.get('/api/secure', () => new HttpResponse(null, { status: 401 })))

    await expect(api.get('/secure')).rejects.toThrow('Session expired. Please log in again.')
    expect(globalThis.location.href).toBe('/login')

    // Second 401 without reset does not redirect again (guard still set).
    globalThis.location.href = 'http://localhost/'
    await expect(api.get('/secure')).rejects.toThrow('Session expired. Please log in again.')
    expect(globalThis.location.href).toBe('http://localhost/')

    // After reset, a new 401 redirects again.
    resetSessionExpired()
    await expect(api.get('/secure')).rejects.toThrow('Session expired. Please log in again.')
    expect(globalThis.location.href).toBe('/login')
  })

  it('does NOT treat a 401 on /auth/login as a session expiry', async () => {
    // A failed login is a bad-credentials error, not an expired session. The
    // global 401 handler must be exempt for /auth/login so LoginPage can show
    // an inline error instead of clearing storage and redirecting.
    vi.stubGlobal('location', { href: 'http://localhost/login', origin: 'http://localhost' })
    localStorage.setItem('token', 'x')
    localStorage.setItem('user', JSON.stringify({ id: 1 }))
    server.use(http.post('/api/auth/login', () =>
      HttpResponse.json({ detail: 'Invalid credentials' }, { status: 401 })))

    // The real detail surfaces, not the session-expired message.
    await expect(api.post('/auth/login', { username: 'a', password: 'b' }))
      .rejects.toThrow('Invalid credentials')

    // No credential clearing and no redirect.
    expect(localStorage.getItem('token')).toBe('x')
    expect(localStorage.getItem('user')).toBe(JSON.stringify({ id: 1 }))
    expect(globalThis.location.href).toBe('http://localhost/login')
  })
})

describe('timeout', () => {
  it('rejects with a timeout message when the response outlives the timeout', async () => {
    server.use(http.get('/api/slow', async () => {
      await delay(50)
      return HttpResponse.json({})
    }))
    await expect(api.get('/slow', { timeout: 1 })).rejects.toThrow(
      'The request timed out. Please try again.',
    )
  })

  it('does not time out when timeout is 0', async () => {
    server.use(http.get('/api/slow', async () => {
      await delay(20)
      return HttpResponse.json({ ok: true })
    }))
    expect(await api.get('/slow', { timeout: 0 })).toEqual({ ok: true })
  })
})

describe('empty bodies', () => {
  it('resolves null on 204 No Content', async () => {
    server.use(http.get('/api/empty', () => new HttpResponse(null, { status: 204 })))
    expect(await api.get('/empty')).toBeNull()
  })

  it('resolves null on a 200 with an empty body', async () => {
    server.use(http.get('/api/empty', () => new HttpResponse('', { status: 200 })))
    expect(await api.get('/empty')).toBeNull()
  })
})

describe('error sanitization', () => {
  it('throws a plain string detail verbatim', async () => {
    server.use(http.get('/api/err', () =>
      HttpResponse.json({ detail: 'plain' }, { status: 400 })))
    await expect(api.get('/err')).rejects.toThrow('plain')
  })

  it('joins an array detail with "; "', async () => {
    server.use(http.get('/api/err', () =>
      HttpResponse.json({ detail: [{ msg: 'a' }, { msg: 'b' }] }, { status: 422 })))
    await expect(api.get('/err')).rejects.toThrow('a; b')
  })

  it('replaces SQL details with a generic message', async () => {
    const sensitive = 'SQL error near SELECT * FROM users'
    server.use(http.get('/api/err', () =>
      HttpResponse.json({ detail: sensitive }, { status: 500 })))
    await expect(api.get('/err')).rejects.toThrow('An unexpected error occurred. Please try again.')
    await expect(api.get('/err')).rejects.not.toThrow(sensitive)
  })

  it('replaces Traceback details with a generic message', async () => {
    const sensitive = 'Traceback (most recent call last): ...'
    server.use(http.get('/api/err', () =>
      HttpResponse.json({ detail: sensitive }, { status: 500 })))
    const err = await api.get('/err').catch((e) => e)
    expect(err.message).toBe('An unexpected error occurred. Please try again.')
    expect(err.message).not.toContain('Traceback')
  })

  it('replaces internal-path details with a generic message', async () => {
    const sensitive = 'Error in /app/main.py line 42'
    server.use(http.get('/api/err', () =>
      HttpResponse.json({ detail: sensitive }, { status: 500 })))
    const err = await api.get('/err').catch((e) => e)
    expect(err.message).toBe('An unexpected error occurred. Please try again.')
    expect(err.message).not.toContain('/app/')
  })
})

/** Spy on document.createElement('a') to capture the anchor the download
 *  helpers create. Returns the live anchor so we can read its `download`
 *  attribute; stubs `.click()` so jsdom does not attempt navigation. */
function spyOnAnchor() {
  const real = document.createElement.bind(document)
  let anchor = null
  const spy = vi.spyOn(document, 'createElement').mockImplementation((tag) => {
    const el = real(tag)
    if (tag === 'a') {
      el.click = vi.fn()
      anchor = el
    }
    return el
  })
  return { spy, getAnchor: () => anchor }
}

describe('download filename parsing', () => {
  it('decodes an RFC 5987 filename* for api.download', async () => {
    const { spy, getAnchor } = spyOnAnchor()
    server.use(http.get('/api/file', () =>
      new HttpResponse('data', {
        headers: { 'Content-Disposition': "attachment; filename*=UTF-8''my%20file.csv" },
      })))
    await api.download('/file')
    expect(getAnchor().download).toBe('my file.csv')
    spy.mockRestore()
  })

  it('uses a legacy quoted filename for api.download', async () => {
    const { spy, getAnchor } = spyOnAnchor()
    server.use(http.get('/api/file', () =>
      new HttpResponse('data', {
        headers: { 'Content-Disposition': 'attachment; filename="report.csv"' },
      })))
    await api.download('/file')
    expect(getAnchor().download).toBe('report.csv')
    spy.mockRestore()
  })

  it('falls back to export.csv for api.download with no disposition', async () => {
    const { spy, getAnchor } = spyOnAnchor()
    server.use(http.get('/api/file', () => new HttpResponse('data')))
    await api.download('/file')
    expect(getAnchor().download).toBe('export.csv')
    spy.mockRestore()
  })

  it('falls back to report.pdf for api.downloadPost with no disposition', async () => {
    const { spy, getAnchor } = spyOnAnchor()
    server.use(http.post('/api/file', () => new HttpResponse('data')))
    await api.downloadPost('/file', { q: 1 })
    expect(getAnchor().download).toBe('report.pdf')
    spy.mockRestore()
  })

  it('decodes an RFC 5987 filename* for api.downloadPost', async () => {
    const { spy, getAnchor } = spyOnAnchor()
    server.use(http.post('/api/file', () =>
      new HttpResponse('data', {
        headers: { 'Content-Disposition': "attachment; filename*=UTF-8''my%20file.csv" },
      })))
    await api.downloadPost('/file', {})
    expect(getAnchor().download).toBe('my file.csv')
    spy.mockRestore()
  })
})

describe('upload', () => {
  it('posts multipart form-data (browser-set Content-Type) and returns JSON', async () => {
    let ct = null
    server.use(http.post('/api/import', ({ request }) => {
      ct = request.headers.get('Content-Type')
      return HttpResponse.json({ imported: 3 })
    }))
    const fd = new FormData()
    fd.append('file', new Blob(['a,b,c'], { type: 'text/csv' }), 'data.csv')
    const result = await api.upload('/import', fd)
    expect(ct).toMatch(/^multipart\/form-data/)
    expect(result).toEqual({ imported: 3 })
  })

  it('joins an array detail on a non-OK upload', async () => {
    server.use(http.post('/api/import', () =>
      HttpResponse.json({ detail: [{ msg: 'bad row 1' }, { msg: 'bad row 2' }] }, { status: 422 })))
    await expect(api.upload('/import', new FormData())).rejects.toThrow('bad row 1; bad row 2')
  })

  it('sanitizes SQL/Traceback/path details on a non-OK upload', async () => {
    const sensitive = 'Traceback in /app/import.py: SQL syntax error'
    server.use(http.post('/api/import', () =>
      HttpResponse.json({ detail: sensitive }, { status: 500 })))
    const err = await api.upload('/import', new FormData()).catch((e) => e)
    expect(err.message).toBe('An unexpected error occurred')
    expect(err.message).not.toContain('SQL')
    expect(err.message).not.toContain('Traceback')
    expect(err.message).not.toContain('/app/')
  })

  it('sends Authorization when a token is stored', async () => {
    localStorage.setItem('token', 'tok')
    let auth = null
    server.use(http.post('/api/import', ({ request }) => {
      auth = request.headers.get('Authorization')
      return HttpResponse.json({})
    }))
    await api.upload('/import', new FormData())
    expect(auth).toBe('Bearer tok')
  })

  it('omits Authorization when no token is stored', async () => {
    let auth = 'unset'
    server.use(http.post('/api/import', ({ request }) => {
      auth = request.headers.get('Authorization')
      return HttpResponse.json({})
    }))
    await api.upload('/import', new FormData())
    expect(auth).toBeNull()
  })
})

describe('download auth headers', () => {
  it('api.download sends Authorization when a token is stored', async () => {
    const { spy } = spyOnAnchor()
    localStorage.setItem('token', 'tok')
    let auth = null
    server.use(http.get('/api/file', ({ request }) => {
      auth = request.headers.get('Authorization')
      return new HttpResponse('data')
    }))
    await api.download('/file')
    expect(auth).toBe('Bearer tok')
    spy.mockRestore()
  })

  it('api.download omits Authorization when no token is stored', async () => {
    const { spy } = spyOnAnchor()
    let auth = 'unset'
    server.use(http.get('/api/file', ({ request }) => {
      auth = request.headers.get('Authorization')
      return new HttpResponse('data')
    }))
    await api.download('/file')
    expect(auth).toBeNull()
    spy.mockRestore()
  })

  it('api.downloadPost sends Authorization when a token is stored', async () => {
    const { spy } = spyOnAnchor()
    localStorage.setItem('token', 'tok')
    let auth = null
    server.use(http.post('/api/file', ({ request }) => {
      auth = request.headers.get('Authorization')
      return new HttpResponse('data')
    }))
    await api.downloadPost('/file', { q: 1 })
    expect(auth).toBe('Bearer tok')
    spy.mockRestore()
  })

  it('api.downloadPost omits Authorization when no token is stored', async () => {
    const { spy } = spyOnAnchor()
    let auth = 'unset'
    server.use(http.post('/api/file', ({ request }) => {
      auth = request.headers.get('Authorization')
      return new HttpResponse('data')
    }))
    await api.downloadPost('/file', { q: 1 })
    expect(auth).toBeNull()
    spy.mockRestore()
  })
})

describe('download failures', () => {
  it('api.download throws "Download failed" on a non-OK response', async () => {
    const { spy } = spyOnAnchor()
    server.use(http.get('/api/file', () => new HttpResponse(null, { status: 500 })))
    await expect(api.download('/file')).rejects.toThrow('Download failed')
    spy.mockRestore()
  })

  it('api.downloadPost throws "Download failed" on a non-OK response', async () => {
    const { spy } = spyOnAnchor()
    server.use(http.post('/api/file', () => new HttpResponse(null, { status: 500 })))
    await expect(api.downloadPost('/file', {})).rejects.toThrow('Download failed')
    spy.mockRestore()
  })
})

describe('caller-provided signal', () => {
  it('rejects when the caller aborts the request before it resolves', async () => {
    const controller = new AbortController()
    server.use(http.get('/api/slow', async () => {
      await delay(50)
      return HttpResponse.json({ ok: true })
    }))
    const pending = api.get('/slow', { signal: controller.signal })
    controller.abort()
    await expect(pending).rejects.toThrow()
  })
})
