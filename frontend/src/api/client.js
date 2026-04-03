/**
 * Centralized API client for all backend communication.
 * Handles authentication headers, token management, and error sanitization.
 */

/** @type {string} Base URL prefix for all API requests. */
const API_BASE = '/api'

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
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  })

  // Automatic session expiry: clear credentials and redirect on 401
  if (res.status === 401) {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    globalThis.location.href = '/login'
    throw new Error('Unauthorized')
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

  return res.json()
}

/**
 * API client with convenience methods for each HTTP verb.
 * All methods automatically include auth tokens and handle errors.
 */
export const api = {
  /** @param {string} path - GET endpoint. @returns {Promise<Object>} */
  get: (path) => request(path),
  /** @param {string} path - POST endpoint. @param {Object} data - Request body. @returns {Promise<Object>} */
  post: (path, data) => request(path, { method: 'POST', body: JSON.stringify(data) }),
  /** @param {string} path - PATCH endpoint. @param {Object} data - Partial update body. @returns {Promise<Object>} */
  patch: (path, data) => request(path, { method: 'PATCH', body: JSON.stringify(data) }),
  /** @param {string} path - PUT endpoint. @param {Object} data - Full replacement body. @returns {Promise<Object>} */
  put: (path, data) => request(path, { method: 'PUT', body: JSON.stringify(data) }),
  /** @param {string} path - DELETE endpoint. @returns {Promise<Object>} */
  delete: (path) => request(path, { method: 'DELETE' }),

  /**
   * POST a JSON body and trigger a file download from the response blob.
   * Extracts the filename from the Content-Disposition header if available.
   * @param {string} path - API endpoint path.
   * @param {Object} body - JSON request body.
   * @returns {Promise<void>}
   */
  downloadPost: async (path, body) => {
    const token = localStorage.getItem('token')
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error('Download failed')
    const blob = await res.blob()
    const disposition = res.headers.get('Content-Disposition')
    let filename = 'report.pdf'
    if (disposition) {
      const match = /filename="?(.+?)"?$/i.exec(disposition)
      if (match) filename = match[1]
    }
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
   * @returns {Promise<void>}
   */
  download: async (path) => {
    const token = localStorage.getItem('token')
    const res = await fetch(`${API_BASE}${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!res.ok) throw new Error('Download failed')
    const blob = await res.blob()
    const disposition = res.headers.get('Content-Disposition')
    let filename = 'export.csv'
    if (disposition) {
      const match = /filename="?(.+?)"?$/.exec(disposition)
      if (match) filename = match[1]
    }
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
   * @returns {Promise<Object>} Parsed JSON response body.
   */
  upload: async (path, formData) => {
    const token = localStorage.getItem('token')
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: formData,
    })
    if (res.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      globalThis.location.href = '/login'
      throw new Error('Unauthorized')
    }
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      const msg = data.detail || 'Upload failed'
      if (msg.includes('SQL') || msg.includes('Traceback') || msg.includes('/app/')) {
        throw new Error('An unexpected error occurred')
      }
      throw new Error(msg)
    }
    return res.json()
  },
}
