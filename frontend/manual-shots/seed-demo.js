/* global Buffer */
import {
  api, createVehicle, createPilotRecord, createFlight, createCertType,
  createPilotCertification, getPilotToken,
} from '../e2e/helpers/seed.js'

// Fake demo data for the manual pictures. Everything here is made up: names,
// @example.com emails, 555-01xx phones, DEMO- serials, FA-DEMO- registrations,
// two text-only locations and no coordinates.

const LOCATIONS = ['Training Field A', 'Riverside Park']
const PILOTS = [
  ['Avery', 'Brooks'], ['Jordan', 'Ellis'], ['Sam', 'Ortega'],
  ['Riley', 'Chen'], ['Morgan', 'Patel'], ['Casey', 'Nguyen'],
]
const VEHICLES = [
  { manufacturer: 'Skydio', model: 'X10', nickname: 'Demo One' },
  { manufacturer: 'DJI', model: 'Matrice 30', nickname: 'Demo Two' },
  { manufacturer: 'Autel', model: 'EVO II', nickname: 'Demo Three' },
]

const day = (offset) => {
  const d = new Date()
  d.setDate(d.getDate() + offset)
  return d.toISOString().slice(0, 10)
}
const pad = (n) => String(n).padStart(2, '0')

// Each optional step is independent: one failing record is reported, not fatal.
async function attempt(label, fn, skipped) {
  try {
    return await fn()
  } catch (e) {
    skipped.push(`${label}: ${String(e.message).slice(0, 160)}`)
    return null
  }
}

async function post(request, token, p, data, label) {
  const res = await api(request, token).post(p, data)
  if (!res.ok()) throw new Error(`${label}: ${res.status()} ${await res.text()}`)
  return res.json()
}

export async function seedDemo(request, adminToken) {
  const existing = await api(request, adminToken).get('/pilots')
  const body = existing.ok() ? await existing.json() : []
  const rows = Array.isArray(body) ? body : (body.items ?? [])
  if (rows.some((p) => p.first_name === 'Avery' && p.last_name === 'Brooks')) {
    return { skipped: ['already seeded'] }
  }

  const skipped = []
  const A = adminToken

  const pilots = []
  for (const [i, [first_name, last_name]] of PILOTS.entries()) {
    pilots.push(await createPilotRecord(request, A, {
      first_name,
      last_name,
      email: `${first_name}.${last_name}@example.com`.toLowerCase(),
      phone: `555-01${pad(10 + i)}`,
    }))
  }

  const vehicles = []
  for (const [i, v] of VEHICLES.entries()) {
    vehicles.push(await createVehicle(request, A, {
      ...v,
      serial_number: `DEMO-${String(i + 1).padStart(4, '0')}`,
      faa_registration: `FA-DEMO-${pad(i + 1)}`,
    }))
  }

  // FAA registrations: one expired and one current for the first vehicle, then
  // one running out soon and one far off, so the list shows each colour.
  const registrations = [
    [0, 'FA-DEMO-01', day(-1500)], [0, 'FA-DEMO-01R', day(-1020)],
    [1, 'FA-DEMO-02', day(-1085)], [2, 'FA-DEMO-03', day(-200)],
  ]
  for (const [v, registration_number, registration_date] of registrations) {
    await attempt(`registration ${registration_number}`, () => post(
      request, A, `/vehicles/${vehicles[v].id}/registrations`, { registration_number, registration_date }, 'registration',
    ), skipped)
  }

  // Equipment
  const batteries = []
  for (let i = 1; i <= 3; i++) {
    batteries.push(await attempt(`battery ${i}`, () => post(request, A, '/batteries', {
      serial_number: `DEMO-BAT-${pad(i)}`, nickname: `Demo Battery ${i}`, manufacturer: 'Skydio',
      cycle_count: 20 * i, health_pct: 100 - 8 * i,
    }, 'battery'), skipped))
  }

  // One battery still out and one returned, for the Checkouts page.
  const outBattery = batteries[0]
  const backBattery = batteries[1]
  if (outBattery) {
    await attempt('checkout', () => post(request, A, '/equipment-checkouts', {
      entity_type: 'battery', entity_id: outBattery.id, entity_name: outBattery.nickname,
      checked_out_by_id: pilots[1].id, expected_return: `${day(3)}T17:00:00`, notes_out: 'Demo training day',
    }, 'checkout'), skipped)
  }
  if (backBattery) {
    await attempt('returned checkout', async () => {
      const co = await post(request, A, '/equipment-checkouts', {
        entity_type: 'battery', entity_id: backBattery.id, entity_name: backBattery.nickname,
        checked_out_by_id: pilots[2].id,
      }, 'checkout')
      await post(request, A, `/equipment-checkouts/${co.id}/checkin`, { checked_in_by_id: pilots[2].id }, 'checkin')
    }, skipped)
  }
  await attempt('controller', () => post(request, A, '/controllers', {
    serial_number: 'DEMO-CTL-01', nickname: 'Demo Controller', manufacturer: 'Skydio', model: 'Beacon 2',
    assigned_pilot_id: pilots[0].id,
  }, 'controller'), skipped)
  await attempt('dock', () => post(request, A, '/docks', {
    serial_number: 'DEMO-DOCK-01', name: 'Demo Dock', location_name: LOCATIONS[0],
  }, 'dock'), skipped)
  await attempt('sensor', () => post(request, A, '/sensors', {
    serial_number: 'DEMO-SEN-01', name: 'Demo Thermal Sensor', type: 'thermal', manufacturer: 'Skydio',
  }, 'sensor'), skipped)
  await attempt('other equipment', () => post(request, A, '/other-equipment', {
    name: 'Demo Hard Case', category: 'Case', serial_number: 'DEMO-OTH-01',
  }, 'other equipment'), skipped)

  // 20 flights over the last 60 days, text locations only.
  const purposes = ['Training', 'Patrol', 'Search']
  for (let i = 0; i < 20; i++) {
    await createFlight(request, A, {
      pilot_id: pilots[i % pilots.length].id,
      vehicle_id: vehicles[i % vehicles.length].id,
      date: day(-3 * (i + 1)),
      duration_seconds: 420 + 60 * ((i * 7) % 20),
      purpose: purposes[i % purposes.length],
      takeoff_address: LOCATIONS[i % 2],
      landing_address: LOCATIONS[i % 2],
      max_altitude_m: 60 + (i % 5) * 10,
    })
  }

  // Certifications: current, expiring and expired.
  const part107 = await createCertType(request, A, {
    name: 'Demo Part 107 Certificate', category: 'faa', has_expiration: true, renewal_period_months: 24,
  })
  const skills = await createCertType(request, A, {
    name: 'Demo Skills Assessment', category: 'training', has_expiration: true, renewal_period_months: 12,
  })
  const certs = [
    [0, part107, day(-300), day(430)], [1, part107, day(-700), day(20)], [2, part107, day(-800), day(-10)],
    [3, part107, day(-100), day(630)], [0, skills, day(-340), day(25)], [4, skills, day(-400), day(-35)],
  ]
  for (const [p, t, issue_date, expiration_date] of certs) {
    await attempt('certification', () => createPilotCertification(request, A, {
      pilot_id: pilots[p].id, certification_type_id: t.id, status: 'complete', issue_date, expiration_date,
    }), skipped)
  }

  await attempt('maintenance record', () => post(request, A, '/maintenance', {
    entity_type: 'vehicle', entity_id: vehicles[0].id, maintenance_type: 'inspection',
    description: 'Demo propeller and motor inspection', performed_by: 'Demo Technician',
    performed_date: day(-14), next_due_date: day(76),
  }, 'maintenance'), skipped)
  await attempt('maintenance schedule', () => post(request, A, '/maintenance/schedules', {
    name: 'Demo quarterly airframe check', entity_type: 'vehicle', entity_id: vehicles[1].id,
    frequency: 'quarterly',
  }, 'schedule'), skipped)

  await attempt('checklist template', () => post(request, A, '/checklists/templates', {
    name: 'Demo Pre-Flight Checklist', description: 'Demo checklist for the manual.',
    items: [
      { label: 'Propellers undamaged and tight', required: true },
      { label: 'Battery charged and seated', required: true },
      { label: 'Camera lens clean', required: false },
      { label: 'Controller linked to the aircraft', required: true },
    ],
  }, 'checklist template'), skipped)

  await attempt('incident', () => post(request, A, '/incidents', {
    date: day(-9), title: 'Demo hard landing', severity: 'minor', category: 'near_miss',
    description: 'Demo incident for the manual. Landing gear bumped the ground.', location: LOCATIONS[0],
    pilot_id: pilots[1].id, vehicle_id: vehicles[1].id,
  }, 'incident'), skipped)

  // Nobody approves their own plan, so the plans are submitted by the e2e pilot
  // login and the admin approves one of them.
  const planBody = (title, n) => ({
    title, date_planned: `${day(n)}T14:00:00`, pilot_id: pilots[0].id, vehicle_id: vehicles[0].id,
    location: LOCATIONS[1], purpose: 'Training', estimated_duration_min: 30,
  })
  let submitter = A
  try {
    submitter = getPilotToken()
  } catch {
    skipped.push('flight plans submitted by admin (no pilot login)')
  }
  await attempt('pending flight plan', () => post(request, submitter, '/flight-plans', planBody('Demo pending plan', 5), 'plan'), skipped)
  await attempt('approved flight plan', async () => {
    const plan = await post(request, submitter, '/flight-plans', planBody('Demo approved plan', 7), 'plan')
    await post(request, A, `/flight-plans/${plan.id}/approve`, { review_notes: 'Approved for the demo' }, 'approve')
  }, skipped)

  await attempt('mission log', () => post(request, A, '/mission-logs', {
    date: day(-12), title: 'Demo search support', location: LOCATIONS[1], status: 'completed',
    vehicle_id: vehicles[2].id, man_hours: 2, pilots: [{ pilot_id: pilots[2].id, role: 'Pilot', hours: 1 }],
  }, 'mission'), skipped)
  await attempt('training log', () => post(request, A, '/training-logs', {
    date: day(-6), title: 'Demo proficiency session', training_type: 'Proficiency', location: LOCATIONS[0],
    outcome: 'completed', man_hours: 3, pilots: [{ pilot_id: pilots[3].id, role: 'Trainee', hours: 1.5 }],
  }, 'training'), skipped)
  await attempt('calendar event', () => post(request, A, '/calendar/events', {
    title: 'Demo team briefing', category: 'event', start_date: day(4),
  }, 'calendar'), skipped)

  await attempt('folder and document', async () => {
    const folder = await post(request, A, '/folders', { name: 'Demo Procedures' }, 'folder')
    const res = await request.post('http://localhost:8000/api/documents/upload', {
      headers: { Authorization: `Bearer ${A}` },
      multipart: {
        file: {
          name: 'demo-notes.txt', mimeType: 'text/plain',
          buffer: Buffer.from('Demo procedure notes. Fake content for the manual.'),
        },
        entity_type: 'general', document_type: 'manual', title: 'Demo procedure notes',
        folder_id: String(folder.id),
      },
    })
    if (!res.ok()) throw new Error(`upload: ${res.status()} ${await res.text()}`)
  }, skipped)

  if (skipped.length) console.warn('seed-demo skipped:\n' + skipped.join('\n'))
  return { skipped }
}
