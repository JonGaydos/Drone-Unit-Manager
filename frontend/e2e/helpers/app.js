import { expect } from '@playwright/test'

// Sidebar link label -> route. The label is the visible NavLink text; some
// labels differ from their route (e.g. "Activity Reports" -> /incidents,
// "Photo Gallery" -> /media), so map explicitly. Update here if the Sidebar
// (frontend/src/components/layout/Sidebar.jsx) changes.
export const SECTIONS = {
  Dashboard: '/',
  Analytics: '/analytics',
  Weather: '/weather',
  Airspace: '/airspace',
  'Flight Plans': '/flight-plans',
  Checklists: '/checklists',
  Flights: '/flights',
  'Mission Log': '/missions',
  'Training Log': '/training',
  Calendar: '/calendar',
  Pilots: '/pilots',
  Fleet: '/fleet',
  Certifications: '/certifications',
  Maintenance: '/maintenance',
  Checkouts: '/checkouts',
  Compliance: '/compliance',
  Alerts: '/alerts',
  'Activity Reports': '/incidents',
  'Photo Gallery': '/media',
  Documents: '/documents',
  Reports: '/reports',
  Settings: '/settings',
  'Audit Log': '/audit-log', // admin-only nav item
}

// Navigate via the sidebar by its visible link name, then assert the URL.
export async function gotoSection(page, name) {
  const route = SECTIONS[name]
  if (!route) throw new Error(`unknown section "${name}"`)
  await page.getByRole('link', { name, exact: true }).click()
  const pattern = route === '/' ? /\/$/ : new RegExp(`${route}(?:$|[/?])`)
  await expect(page).toHaveURL(pattern)
}
