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
  // The Audit Log user filter's choices.
  http.get('/api/audit/users', () => HttpResponse.json([])),
  // Settings > General shows every user's digest preferences card.
  http.get('/api/notifications/preferences', () => HttpResponse.json({
    enabled: true, frequency: 'daily', send_time: '07:00', send_day: null,
    categories: ['expiring_certs'], email_override: null,
  })),
  http.get('/api/notifications/log', () => HttpResponse.json([])),
  // The currency rule picker's fleet models.
  http.get('/api/currency/models', () => HttpResponse.json([])),
  // Settings > Flight Requirements: definitions, fleet models, templates and settings.
  http.get('/api/requirements', () => HttpResponse.json([])),
  http.get('/api/requirements/models', () => HttpResponse.json([])),
  http.get('/api/requirements/templates', () => HttpResponse.json([])),
  http.get('/api/requirements/settings', () => HttpResponse.json({ grace_days: 14, fiscal_year_start_month: 10 })),
  // Requirement progress on the dashboard, Compliance, Pilots and pilot pages.
  http.get('/api/requirements/status', () => HttpResponse.json({ score: null, requirements: [] })),
  http.get('/api/requirements/flags', () => HttpResponse.json({})),
  http.get('/api/requirements/pilots/:id', ({ params }) =>
    HttpResponse.json({ pilot_id: Number(params.id), current: [], pending: [], history: [] })),
  // Settings reads whether the server serves /docs.
  http.get('/api/health', () => HttpResponse.json({ status: 'ok', api_docs: false })),
]
