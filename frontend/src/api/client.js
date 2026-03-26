const API_BASE = '/api'

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

  if (res.status === 401) {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    window.location.href = '/login'
    throw new Error('Unauthorized')
  }

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }))
    const sanitized = error.detail || 'An error occurred. Please try again.'
    // Don't expose SQL errors, tracebacks, or internal paths
    if (sanitized.includes('SQL') || sanitized.includes('Traceback') || sanitized.includes('/app/')) {
      throw new Error('An unexpected error occurred. Please try again.')
    }
    throw new Error(sanitized)
  }

  return res.json()
}

export const api = {
  get: (path) => request(path),
  post: (path, data) => request(path, { method: 'POST', body: JSON.stringify(data) }),
  patch: (path, data) => request(path, { method: 'PATCH', body: JSON.stringify(data) }),
  put: (path, data) => request(path, { method: 'PUT', body: JSON.stringify(data) }),
  delete: (path) => request(path, { method: 'DELETE' }),
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
      const match = disposition.match(/filename="?(.+?)"?$/i)
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
      const match = disposition.match(/filename="?(.+?)"?$/)
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
      window.location.href = '/login'
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
