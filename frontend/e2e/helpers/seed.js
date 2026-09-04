import { readFileSync } from 'node:fs'
import path from 'node:path'

const API = 'http://localhost:8000/api'

// Prefer getAdminToken() over apiLogin() in specs — the suite shares a per-IP
// 5-logins/60s rate limit; only global-setup and auth.spec should spend real logins.
// Reads the admin JWT straight from the storageState global-setup wrote; no HTTP.
export function getAdminToken() {
  const file = path.resolve(process.cwd(), 'e2e/.auth/admin.json')
  const state = JSON.parse(readFileSync(file, 'utf8'))
  for (const origin of state.origins ?? []) {
    for (const item of origin.localStorage ?? []) {
      if (item.name === 'token') return item.value
    }
  }
  throw new Error(`getAdminToken: no localStorage 'token' in ${file}`)
}

export async function apiLogin(request, username, password) {
  const res = await request.post(`${API}/auth/login`, { data: { username, password } })
  if (!res.ok()) throw new Error(`login failed: ${res.status()} ${await res.text()}`)
  return (await res.json()).token
}

export function api(request, token) {
  const headers = { Authorization: `Bearer ${token}` }
  return {
    get: (p) => request.get(`${API}${p}`, { headers }),
    post: (p, data) => request.post(`${API}${p}`, { headers, data }),
    patch: (p, data) => request.patch(`${API}${p}`, { headers, data }),
    del: (p) => request.delete(`${API}${p}`, { headers }),
  }
}

async function created(res, label) {
  if (!res.ok()) throw new Error(`${label}: ${res.status()} ${await res.text()}`)
  return res.json()
}

// --- Convenience creators (fields verified against the real backend schemas) ---

// POST /api/auth/users (admin only). role one of viewer|pilot|supervisor|admin.
export async function createUser(request, token, fields) {
  return created(await api(request, token).post('/auth/users', fields), 'createUser')
}

// POST /api/vehicles (supervisor+). Required: serial_number, manufacturer, model.
export async function createVehicle(request, token, fields) {
  return created(await api(request, token).post('/vehicles', fields), 'createVehicle')
}

// POST /api/pilots. Required: first_name, last_name.
export async function createPilotRecord(request, token, fields) {
  return created(await api(request, token).post('/pilots', fields), 'createPilotRecord')
}

// POST /api/flights. All fields optional; pass pilot_id + vehicle_id to link.
export async function createFlight(request, token, fields) {
  return created(await api(request, token).post('/flights', fields), 'createFlight')
}

// POST /api/certification-types (supervisor+). Required: name.
export async function createCertType(request, token, fields) {
  return created(await api(request, token).post('/certification-types', fields), 'createCertType')
}

// POST /api/pilot-certifications (supervisor+). Required: pilot_id, certification_type_id.
export async function createPilotCertification(request, token, fields) {
  return created(await api(request, token).post('/pilot-certifications', fields), 'createPilotCertification')
}
