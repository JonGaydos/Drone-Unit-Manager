// One entry per manual picture.
//   file:    name under public/manual-pictures
//   route:   page to open
//   prepare: optional, runs after the page loads (open a dialog, switch a tab)
//   target:  returns the Locator that is photographed
//
// Most pictures open a dialog and fill it; formShot() builds those entries.
// Its `fields` map has one entry per field, in order. The key says how to fill
// it: '#id' types into that element, 'pick #id' chooses the option containing
// the text, 'select #id' chooses the option with that value, and 'label Text'
// types into the field with that label.

const SETTLE_MS = 450 // dialogs slide in; wait for them to stop moving

// Choose the option whose text contains `text` (the option list has other records too).
async function pickContaining(select, text) {
  const value = await select.evaluate((el, t) => {
    const option = [...el.options].find((o) => o.textContent.includes(t))
    return option ? option.value : null
  }, text)
  if (value === null) throw new Error(`no option containing ${text}`)
  await select.selectOption(value)
}

const isoDay = (offset) => {
  const d = new Date()
  d.setDate(d.getDate() + offset)
  return d.toISOString().slice(0, 10)
}

const dialogOf = (page) => page.getByRole('dialog')

// The rounded card that contains `locator`.
const cardOf = (locator) => locator.locator('xpath=ancestor::div[contains(@class,"rounded-xl")][1]')

async function fillFields(dialog, fields) {
  for (const [key, value] of Object.entries(fields)) {
    const [how, ...rest] = key.split(' ')
    const what = rest.join(' ')
    if (how === 'pick') await pickContaining(dialog.locator(what), value)
    else if (how === 'select') await dialog.locator(what).selectOption(value)
    else if (how === 'label') await dialog.getByLabel(what).fill(value)
    else await dialog.locator(key).fill(value)
  }
}

// A picture of a dialog: optionally make the window taller, run `before`
// (navigate or switch tabs), click the `open` button, fill `fields`, then run
// `after` for anything a field map cannot express.
function formShot(file, route, { open, height, before, fields = {}, after }) {
  return {
    file,
    route,
    prepare: async (page) => {
      if (height) await page.setViewportSize({ width: 1280, height }) // tall enough to show the whole form
      if (before) await before(page)
      if (open) await page.getByRole('button', { name: open, exact: true }).first().click()
      const dialog = dialogOf(page)
      await fillFields(dialog, fields)
      if (after) await after(dialog, page)
      await page.waitForTimeout(SETTLE_MS)
    },
    target: dialogOf,
  }
}

// Add one crew row to a mission or training log dialog.
const addCrew = (role, hours) => async (dialog) => {
  await dialog.getByRole('button', { name: '+ Add Pilot' }).click()
  await pickContaining(dialog.locator('select').filter({ hasText: 'Select pilot...' }), 'Avery Brooks')
  await dialog.locator('select').filter({ hasText: 'Role...' }).selectOption(role)
  await dialog.getByPlaceholder('Hrs').fill(hours)
}

// Open the expiring certification of Jordan Ellis from the matrix.
const openJordanCert = (page) =>
  page.getByRole('row', { name: /Jordan Ellis/ }).locator('td').filter({ hasText: 'expiring soon' }).first().click()

export const SHOTS = [
  {
    file: 'manual-layout-switch.png',
    route: '/manual',
    target: (page) => page.getByRole('group', { name: 'Manual layout' }).locator('xpath=..'),
  },
  {
    file: 'dashboard-overview.png',
    route: '/',
    target: (page) => page.locator('div.grid.auto-rows-min'),
  },
  {
    file: 'analytics-filtering.png',
    route: '/analytics',
    prepare: async (page) => {
      await page.locator('ul button').filter({ hasText: 'Brooks' }).first().click()
      await page.getByText('Active filters:').waitFor()
      await page.waitForTimeout(2000) // let the chart animation finish
    },
    target: (page) => page.locator('div.space-y-6').filter({ has: page.getByText('Active filters:') }).last(),
  },
  formShot('calendar-adding-events.png', '/calendar', {
    open: 'Add event / leave',
    fields: {
      'label Title': 'Demo team briefing',
      'label Start date': isoDay(4),
      'label End date (optional)': isoDay(5),
      'label Notes (optional)': 'Demo notes',
    },
  }),
  formShot('flight-plans-submitting.png', '/flight-plans', {
    open: 'Submit Plan',
    height: 1100,
    fields: {
      '#title': 'Demo training flight',
      '#planned-date-time': `${isoDay(6)}T14:00`,
      'pick #pilot': 'Avery Brooks',
      'pick #vehicle': 'Demo One',
      '#location': 'Training Field A',
      '#purpose': 'Training',
      '#max-altitude-ft': '200',
      '#est-duration-min': '30',
    },
  }),
  {
    file: 'flight-plans-reviewing.png',
    route: '/flight-plans',
    target: (page) => cardOf(page.locator('table')),
  },
  formShot('checklists-completing.png', '/checklists', {
    open: 'Complete Checklist',
    height: 1000,
    fields: {
      'pick #template': 'Demo Pre-Flight Checklist',
      'pick #pilot': 'Avery Brooks',
      'pick #vehicle': 'Demo One',
    },
    after: async (dialog) => {
      await dialog.getByRole('button', { name: 'Tick Propellers undamaged and tight' }).click()
      await dialog.getByRole('button', { name: 'Tick Battery charged and seated' }).click()
    },
  }),
  formShot('checklists-templates.png', '/checklists', {
    open: 'Create Template',
    fields: { '#name': 'Demo Landing Checklist', '#description': 'Demo checklist for after each flight.' },
    after: async (dialog) => {
      const items = ['Aircraft powered down', 'Battery removed', 'Propellers inspected']
      for (const [i, text] of items.entries()) {
        if (i > 0) await dialog.getByRole('button', { name: 'Add Item' }).click()
        await dialog.getByPlaceholder(`Item ${i + 1}...`).fill(text)
      }
    },
  }),
  {
    file: 'flights-viewing-flights.png',
    route: '/flights',
    target: (page) => page.locator('div.flex.flex-wrap.items-end.gap-3').first(),
  },
  formShot('flights-adding-flights-manually.png', '/flights', {
    open: 'Add Flight',
    height: 1500,
    fields: {
      'pick #pilot': 'Avery Brooks',
      'pick #vehicle': 'Demo One',
      '#date': isoDay(-1),
      '#duration-seconds': '900',
      'pick #purpose': 'Training',
      '#takeoff-address': 'Training Field A',
      '#landing-address': 'Training Field A',
      '#case-number': 'DEMO-0001',
    },
  }),
  {
    file: 'flights-reviewing-flights.png',
    route: '/flights',
    prepare: async (page) => {
      const boxes = page.getByRole('checkbox', { name: /^Select flight/ })
      await boxes.nth(0).check()
      await boxes.nth(1).check()
      await page.getByText('2 selected', { exact: true }).waitFor()
    },
    target: (page) => page.getByText('2 selected', { exact: true }).locator('xpath=..'),
  },
  formShot('missions-adding-missions.png', '/missions', {
    open: 'Add Mission',
    height: 1300,
    fields: {
      '#title': 'Demo search support',
      '#location': 'Riverside Park',
      '#man-hours': '2',
      'pick #drone-used': 'Demo One',
      '#description': 'Demo description of the mission.',
    },
    after: addCrew('PIC', '2'),
  }),
  formShot('training-adding-training.png', '/training', {
    open: 'Add Training',
    height: 1300,
    fields: {
      '#title': 'Demo proficiency session',
      '#location': 'Training Field A',
      '#instructor': 'Demo Instructor',
      '#man-hours': '3',
      'pick #drone-used': 'Demo One',
      '#objectives': 'Demo objectives for the session.',
    },
    after: addCrew('Student', '3'),
  }),
  {
    file: 'fleet-fleet-list.png',
    route: '/fleet',
    prepare: async (page) => {
      await page.getByPlaceholder('Search vehicles...').fill('Demo')
      await page.getByRole('link', { name: 'Demo One', exact: true }).waitFor()
    },
    target: (page) => page.locator('div.space-y-4').filter({ has: page.locator('table') }).last(),
  },
  formShot('fleet-adding-a-vehicle.png', '/fleet', {
    open: 'Add Vehicle',
    height: 1000,
    fields: {
      '#field-serial_number': 'DEMO-0004',
      '#field-manufacturer': 'Skydio',
      '#field-model': 'X10',
      '#field-nickname': 'Demo Four',
      '#field-acquired_date': isoDay(-30),
    },
  }),
  formShot('fleet-battery-readings.png', '/fleet', {
    before: async (page) => {
      await page.getByRole('button', { name: 'Batteries' }).click()
      await page.getByRole('link', { name: 'Demo Battery 1', exact: true }).click()
    },
    open: 'Record Reading',
    fields: { '#health-1': '91', '#cycle-count-1': '30', '#voltage': '16.4', '#notes-1': 'Demo monthly check' },
  }),
  {
    file: 'registrations-faa-registrations.png',
    route: '/fleet',
    prepare: async (page) => {
      await page.getByRole('link', { name: 'Demo One', exact: true }).click()
      await page.getByRole('heading', { name: 'FAA Registration' }).waitFor()
    },
    target: (page) => cardOf(page.getByRole('heading', { name: 'FAA Registration' })),
  },
  {
    file: 'fleet-health-reading-fleet-health.png',
    route: '/fleet-health',
    prepare: async (page) => {
      await page.getByRole('heading', { name: 'Battery Health' }).waitFor()
      await page.waitForTimeout(1500) // let the chart animation finish
    },
    target: (page) => page.locator('div.space-y-6').filter({ has: page.getByRole('heading', { name: 'Fleet Health', level: 1 }) }).last(),
  },
  formShot('checkouts-checking-equipment-out.png', '/checkouts', {
    open: 'Check Out',
    fields: { 'select #checkout-type': 'battery' },
    after: async (dialog) => {
      await dialog.locator('#checkout-item option', { hasText: 'Demo Battery 3' }).waitFor({ state: 'attached' })
      await fillFields(dialog, {
        'pick #checkout-item': 'Demo Battery 3',
        'pick #checkout-pilot': 'Riley Chen',
        'label Expected return (optional)': isoDay(2),
        'label Notes (optional)': 'Demo training day',
      })
    },
  }),
  {
    file: 'checkouts-active-and-returned-records.png',
    route: '/checkouts',
    prepare: async (page) => {
      await page.getByText('Show returned').click()
      await page.getByText('Demo Battery 2').first().waitFor()
    },
    target: (page) => page.locator('div.space-y-6').filter({ has: page.getByRole('heading', { name: 'Equipment Checkouts' }) }).last(),
  },
  {
    file: 'pilots-pilot-profiles.png',
    route: '/pilots',
    prepare: async (page) => {
      await page.getByRole('link', { name: /Avery Brooks/ }).click()
      await page.getByRole('heading', { name: 'Avery Brooks' }).waitFor()
    },
    target: (page) => cardOf(page.getByRole('heading', { name: 'Avery Brooks' })),
  },
  {
    file: 'pilots-needs-attention.png',
    route: '/pilots',
    prepare: async (page) => {
      await page.getByRole('link', { name: /Jordan Ellis/ }).click()
      await page.getByRole('heading', { name: 'Needs Attention' }).waitFor()
      await page.getByText('Certification expiring').first().waitFor()
    },
    target: (page) => cardOf(page.getByRole('heading', { name: 'Needs Attention' })),
  },
  formShot('pilots-pilot-currency.png', '/settings', {
    open: 'New Rule',
    fields: {
      '#rule-name': 'Demo quarterly currency',
      '#rule-desc': 'Demo rule for the manual',
      '#rule-hours': '5',
      '#rule-days': '90',
      '#rule-flights': '3',
    },
  }),
  {
    file: 'certifications-certification-matrix.png',
    route: '/certifications',
    prepare: async (page) => {
      await page.getByLabel('Hide empty').check()
      await page.getByRole('row', { name: /Avery Brooks/ }).waitFor()
    },
    target: (page) => cardOf(page.locator('table')),
  },
  formShot('certifications-editing-a-certification.png', '/certifications', {
    height: 1000,
    before: openJordanCert,
    fields: { 'label Notes': 'Demo note: certificate copy filed' },
  }),
  formShot('certifications-renewing-a-certification.png', '/certifications', {
    before: openJordanCert,
    after: async (dialog) => {
      await dialog.getByRole('button', { name: 'Renew', exact: true }).click()
      await dialog.getByLabel('New Issue Date').fill(isoDay(0))
    },
  }),
  {
    file: 'compliance-compliance-score.png',
    route: '/compliance',
    prepare: async (page) => {
      await page.getByRole('heading', { name: 'Compliance Dashboard' }).waitFor()
      await page.waitForTimeout(1500) // let the score ring finish drawing
    },
    target: (page) => page.locator('div.space-y-6').filter({ has: page.getByRole('heading', { name: 'Compliance Dashboard' }) }).last().locator('xpath=./div[2]'),
  },
  formShot('operating-authority-operating-authority.png', '/operating-authority', {
    open: 'Add Authority',
    fields: {
      'label Title': 'Demo blanket public safety COA',
      'label COA / waiver number': 'DEMO-COA-0001',
      'label Issue date': isoDay(-200),
      'label Expiry date': isoDay(165),
      'label Notes': 'Demo notes: altitude ceiling 400 ft',
    },
  }),
  formShot('incidents-incident-reporting.png', '/incidents', {
    open: 'New Report',
    height: 1300,
    fields: {
      'select #severity': 'minor',
      '#title': 'Demo rough landing',
      'select #category': 'near_miss',
      '#location': 'Training Field A',
      '#description': 'Demo description: the aircraft landed harder than planned.',
      'pick #pilot': 'Avery Brooks',
      'pick #vehicle': 'Demo One',
      '#damage-description': 'None',
    },
  }),
  formShot('maintenance-adding-a-maintenance-record.png', '/maintenance', {
    open: 'Add Maintenance',
    height: 1000,
    fields: {
      'pick #entity': 'Demo One',
      'select #maintenance-type': 'inspection',
      '#description': 'Demo propeller and motor inspection',
      'pick #performed-by': 'Avery Brooks',
      '#performed-date': isoDay(0),
      '#cost': '25',
      '#next-due-date': isoDay(90),
      '#notes': 'Demo notes: no damage found',
    },
  }),
  formShot('maintenance-schedules-and-tasks.png', '/maintenance', {
    open: 'Add Schedule / Task',
    height: 1000,
    fields: {
      '#name': 'Demo monthly airframe check',
      'pick #entity-1': 'Demo One',
      'select #frequency': 'monthly',
      '#next-due': isoDay(30),
      '#description-1': 'Demo description: check arms, props and landing gear.',
    },
  }),
  {
    file: 'documents-folders-and-finding-documents.png',
    route: '/documents',
    prepare: async (page) => {
      await page.getByRole('treeitem', { name: /Demo Procedures/ }).click()
      await page.waitForTimeout(SETTLE_MS)
    },
    target: (page) => cardOf(page.getByRole('tree', { name: 'Document folders' })),
  },
  formShot('media-uploading-photos.png', '/media', {
    open: 'Upload',
    height: 1000,
    fields: { 'label Title': 'Demo training field', 'label Description': 'Demo description', 'label Date Taken': isoDay(-3) },
  }),
  {
    file: 'reports-building-a-report.png',
    route: '/reports',
    prepare: async (page) => {
      await page.getByRole('button', { name: 'Last 90d' }).click()
      await page.waitForTimeout(SETTLE_MS)
    },
    target: (page) => cardOf(page.getByRole('heading', { name: 'Report Builder' })),
  },
  {
    file: 'settings-email-digest.png',
    route: '/settings',
    prepare: async (page) => {
      await page.getByLabel('Send me email digests').check()
      // The floating Save Settings bar would cover the card's lower edge.
      await page.evaluate(() => document.querySelectorAll('.sticky.bottom-4').forEach((el) => { el.style.display = 'none' }))
      await page.waitForTimeout(SETTLE_MS)
    },
    target: (page) => cardOf(page.getByRole('heading', { name: 'Email Digest' })),
  },
  formShot('settings-api-tokens.png', '/settings', {
    before: (page) => page.getByRole('button', { name: 'API Tokens' }).click(),
    open: 'Create Token',
    fields: { '#token-name': 'Demo dashboard', 'select #token-expiry': '90' },
  }),
  {
    file: 'backup-in-app-backup.png',
    route: '/settings',
    prepare: async (page) => {
      await page.getByRole('heading', { name: 'Backup & Restore' }).waitFor()
    },
    target: (page) => cardOf(page.getByRole('heading', { name: 'Backup & Restore' })),
  },
]
