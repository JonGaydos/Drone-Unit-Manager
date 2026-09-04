import { http, HttpResponse } from 'msw'

// Minimal defaults so AuthProvider's mount validation resolves for an
// authenticated render. Tests override per-case with server.use(...).
export const handlers = [
  http.get('/api/auth/me', () =>
    HttpResponse.json({ id: 1, username: 'admin', role: 'admin' })),
]
