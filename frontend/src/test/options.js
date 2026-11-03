// Rows shaped exactly as GET /api/pilots/options and /api/fleet/options return
// them, so a page reading a field the endpoints lack fails its test.

export function pilotOption(id, fullName, overrides = {}) {
  return { id, full_name: fullName, badge_number: null, status: 'active', ...overrides }
}

export function vehicleOption({ id, nickname = null, manufacturer = null, model = null, serialNumber = `V-${id}`, status = 'active' }) {
  return { id, name: nickname || serialNumber, status, nickname, manufacturer, model, serial_number: serialNumber }
}

export function serialOption(id, name, serialNumber = name, status = 'active') {
  return { id, name, status, serial_number: serialNumber }
}

export function nameOption(id, name, status = 'active') {
  return { id, name, status }
}

export function fleetOptions(rows = {}) {
  return { vehicles: [], batteries: [], controllers: [], sensors: [], attachments: [], docks: [], other_equipment: [], ...rows }
}
