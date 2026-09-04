/**
 * Centralized API client for all backend communication.
 * Handles authentication headers, token management, and error sanitization.
 */

/** @type {string} Base URL prefix for all API requests. */
const API_BASE = '/api'

/** @type {number} Per-request timeout in milliseconds. Without it, a hung
 *  backend would leave every spinner stuck forever. */
const DEFAULT_TIMEOUT_MS = 30000

/** Module-level guard so several concurrent 401s trigger only one logout +
 *  redirect, instead of each clobbering location.href and stacking toasts. */
let sessionExpired = false

/** Clear stored credentials and redirect to login exactly once per session. */
function handleUnauthorized() {
  if (sessionExpired) return
  sessionExpired = true
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  globalThis.location.href = '/login'
}

/** Re-arm the once-per-session logout guard after a successful (re-)login, so a
 *  future 401 in the same tab can again clear credentials and redirect. */
export function resetSessionExpired() {
  sessionExpired = false
}

/** Combine AbortSignals into one that aborts as soon as any input does, so a
 *  caller's signal (e.g. a superseded list load) races the request timeout. */
function anySignal(signals) {
  if (typeof AbortSignal !== 'undefined' && typeof AbortSignal.any === 'function') {
    return AbortSignal.any(signals)
  }
  const controller = new AbortController()
  const onAbort = (event) => {
    controller.abort(event?.target?.reason)
    for (const s of signals) s.removeEventListener('abort', onAbort)
  }
  for (const s of signals) {
    if (s.aborted) { controller.abort(s.reason); break }
    s.addEventListener('abort', onAbort)
  }
  return controller.signal
}

/** Parse a download filename from a Content-Disposition header. Prefers the
 *  RFC 5987 `filename*=charset''value` form (decoded), falling back to the
 *  legacy quoted/bare `filename=`. Returns `fallback` when neither is present.
 *  @param {string|null} disposition - The Content-Disposition header value.
 *  @param {string} fallback - Default name when nothing parseable is found.
 *  @returns {string} */
function parseFilename(disposition, fallback) {
  if (!disposition) return fallback
  // RFC 5987 extended form: filename*=UTF-8''my%20file.csv (stop at ';').
  const extended = /filename\*=\s*([^;]+)/i.exec(disposition)
  if (extended) {
    const raw = extended[1].trim().replace(/^["']|["']$/g, '')
    const parts = raw.split("''")
    const encoded = parts.length > 1 ? parts.slice(1).join("''") : raw
    try {
      return decodeURIComponent(encoded)
    } catch {
      return encoded
    }
  }
  // Legacy form: filename="my file.csv" or filename=my_file.csv (stop at ';').
  const legacy = /filename=\s*"?([^";]+)"?/i.exec(disposition)
  if (legacy) return legacy[1].trim()
  return fallback
}

/**
 * Core fetch wrapper that attaches auth headers and handles common error cases.
 * On 401 responses, clears stored credentials and redirects to login.
 * Sanitizes error messages to prevent leaking internal server details.
 * @param {string} path - API endpoint path (appended to API_BASE).
 * @param {RequestInit} [options={}] - Fetch options (method, body, headers, etc.).
 * @returns {Promise<Object>} Parsed JSON response body.
 * @throws {Error} On non-OK responses with a sanitized error message.
 */
async function request(path, options = {}) {
  const token = localStorage.getItem('token')
  const { signal: callerSignal, timeout, ...rest } = options
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  // Abort the request if it outlives the timeout, while still honoring a
  // caller-provided signal (whichever fires first wins). Pass timeout: 0 to
  // disable for long-running operations (provider sync, telemetry pull).
  const timeoutMs = timeout === undefined ? DEFAULT_TIMEOUT_MS : timeout
  let signal = callerSignal
  let timeoutId = null
  if (timeoutMs) {
    const timeoutController = new AbortController()
    timeoutId = setTimeout(
      () => timeoutController.abort(new DOMException('Request timed out', 'TimeoutError')),
      timeoutMs,
    )
    signal = callerSignal ? anySignal([callerSignal, timeoutController.signal]) : timeoutController.signal
  }

  let res
  try {
    res = await fetch(`${API_BASE}${path}`, { ...rest, headers, signal })
  } catch (err) {
    if (err?.name === 'TimeoutError') {
      throw new Error('The request timed out. Please try again.')
    }
    throw err
  } finally {
    if (timeoutId) clearTimeout(timeoutId)
  }

  // Automatic session expiry: clear credentials and redirect on 401 (once).
  // A 401 from the login request itself is a bad-credentials error, not an
  // expired session, so let it fall through to the sanitization path below and
  // surface the real detail for LoginPage to render inline.
  if (res.status === 401 && path !== '/auth/login') {
    handleUnauthorized()
    throw new Error('Session expired. Please log in again.')
  }

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }))
    let sanitized = 'An error occurred. Please try again.'
    if (typeof error.detail === 'string') {
      sanitized = error.detail
    } else if (Array.isArray(error.detail)) {
      sanitized = error.detail.map(e => e.msg || e.message || JSON.stringify(e)).join('; ')
    }
    // Don't expose SQL errors, tracebacks, or internal paths
    if (sanitized.includes('SQL') || sanitized.includes('Traceback') || sanitized.includes('/app/')) {
      throw new Error('An unexpected error occurred. Please try again.')
    }
    throw new Error(sanitized)
  }

  // 204 No Content and other empty bodies have nothing to parse.
  if (res.status === 204) return null
  const text = await res.text()
  return text ? JSON.parse(text) : null
}

/**
 * Run a fetch with the same timeout/AbortController behavior request() uses,
 * honoring a caller-provided signal (whichever fires first wins). On 401 it
 * clears credentials and redirects via handleUnauthorized(). Used by the
 * blob-download and upload helpers so they get parity with request().
 * @param {string} url - Fully qualified URL to fetch.
 * @param {RequestInit} init - Fetch init (method, headers, body).
 * @param {{timeout?: number, signal?: AbortSignal}} [options={}] - timeout in
 *   ms (default DEFAULT_TIMEOUT_MS, 0 disables) and an optional caller signal.
 * @returns {Promise<Response>} The raw Response (caller checks res.ok).
 */
async function fetchWithTimeout(url, init, options = {}) {
  const { signal: callerSignal, timeout } = options
  const timeoutMs = timeout === undefined ? DEFAULT_TIMEOUT_MS : timeout
  let signal = callerSignal
  let timeoutId = null
  if (timeoutMs) {
    const timeoutController = new AbortController()
    timeoutId = setTimeout(
      () => timeoutController.abort(new DOMException('Request timed out', 'TimeoutError')),
      timeoutMs,
    )
    signal = callerSignal ? anySignal([callerSignal, timeoutController.signal]) : timeoutController.signal
  }

  let res
  try {
    res = await fetch(url, { ...init, signal })
  } catch (err) {
    if (err?.name === 'TimeoutError') {
      throw new Error('The request timed out. Please try again.')
    }
    throw err
  } finally {
    if (timeoutId) clearTimeout(timeoutId)
  }

  if (res.status === 401) {
    handleUnauthorized()
    throw new Error('Session expired. Please log in again.')
  }
  return res
}

/**
 * API client with convenience methods for each HTTP verb.
 * All methods automatically include auth tokens and handle errors.
 */
export const api = {
  /** @param {string} path - GET endpoint. @param {RequestInit} [options] - Extra fetch options (e.g. { signal }). @returns {Promise<Object>} */
  get: (path, options) => request(path, options),
  /** @param {string} path - POST endpoint. @param {Object} data - Request body. @param {RequestInit} [options] - Extra fetch options (e.g. { signal }). @returns {Promise<Object>} */
  post: (path, data, options) => request(path, { method: 'POST', body: JSON.stringify(data), ...options }),
  /** @param {string} path - PATCH endpoint. @param {Object} data - Partial update body. @param {RequestInit} [options] - Extra fetch options. @returns {Promise<Object>} */
  patch: (path, data, options) => request(path, { method: 'PATCH', body: JSON.stringify(data), ...options }),
  /** @param {string} path - PUT endpoint. @param {Object} data - Full replacement body. @param {RequestInit} [options] - Extra fetch options. @returns {Promise<Object>} */
  put: (path, data, options) => request(path, { method: 'PUT', body: JSON.stringify(data), ...options }),
  /** @param {string} path - DELETE endpoint. @param {RequestInit} [options] - Extra fetch options. @returns {Promise<Object>} */
  delete: (path, options) => request(path, { method: 'DELETE', ...options }),

  /**
   * POST a JSON body and trigger a file download from the response blob.
   * Extracts the filename from the Content-Disposition header if available.
   * @param {string} path - API endpoint path.
   * @param {Object} body - JSON request body.
   * @param {{timeout?: number, signal?: AbortSignal}} [options={}] - timeout in
   *   ms (default 30s, 0 disables) and an optional caller AbortSignal.
   * @returns {Promise<void>}
   */
  downloadPost: async (path, body, options = {}) => {
    const token = localStorage.getItem('token')
    const res = await fetchWithTimeout(`${API_BASE}${path}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    }, options)
    if (!res.ok) throw new Error('Download failed')
    const blob = await res.blob()
    const filename = parseFilename(res.headers.get('Content-Disposition'), 'report.pdf')
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  },
  /**
   * GET a file and trigger a browser download from the response blob.
   * Extracts the filename from Content-Disposition, defaulting to "export.csv".
   * @param {string} path - API endpoint path.
   * @param {{timeout?: number, signal?: AbortSignal}} [options={}] - timeout in
   *   ms (default 30s, 0 disables) and an optional caller AbortSignal.
   * @returns {Promise<void>}
   */
  download: async (path, options = {}) => {
    const token = localStorage.getItem('token')
    const res = await fetchWithTimeout(`${API_BASE}${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    }, options)
    if (!res.ok) throw new Error('Download failed')
    const blob = await res.blob()
    const filename = parseFilename(res.headers.get('Content-Disposition'), 'export.csv')
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  },
  /**
   * Upload a file via multipart/form-data POST.
   * Does not set Content-Type header (browser sets boundary automatically).
   * @param {string} path - API endpoint path.
   * @param {FormData} formData - Form data containing the file and metadata.
   * @param {Object} [extraHeaders={}] - Additional request headers.
   * @param {{timeout?: number, signal?: AbortSignal}} [options={}] - timeout in
   *   ms (default 30s, 0 disables for large import/backup uploads) and an
   *   optional caller AbortSignal.
   * @returns {Promise<Object>} Parsed JSON response body.
   */
  upload: async (path, formData, extraHeaders = {}, options = {}) => {
    const token = localStorage.getItem('token')
    const headers = {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...extraHeaders,
    }
    const res = await fetchWithTimeout(`${API_BASE}${path}`, {
      method: 'POST',
      headers,
      body: formData,
    }, options)
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      let msg = 'Upload failed'
      if (typeof data.detail === 'string') {
        msg = data.detail
      } else if (Array.isArray(data.detail)) {
        msg = data.detail.map(e => e.msg || e.message || JSON.stringify(e)).join('; ')
      }
      if (msg.includes('SQL') || msg.includes('Traceback') || msg.includes('/app/')) {
        throw new Error('An unexpected error occurred')
      }
      throw new Error(msg)
    }
    return res.json()
  },
}
