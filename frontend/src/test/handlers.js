import { http, HttpResponse } from 'msw'
import { withPermissions } from './permissions'

// Minimal defaults so AuthProvider's mount validation resolves for an
// authenticated render: the user seeded by the render helper, or an admin.
// Tests override per-case with server.use(...).
export const handlers = [
  http.get('/api/auth/me', () => {
    const stored = localStorage.getItem('user')
    return HttpResponse.json(stored ? JSON.parse(stored) : withPermissions({ id: 1, username: 'admin', role: 'admin' }))
  }),
  http.get('/api/settings/idle_lock_minutes', () =>
    HttpResponse.json({ key: 'idle_lock_minutes', value: '30' })),
]
