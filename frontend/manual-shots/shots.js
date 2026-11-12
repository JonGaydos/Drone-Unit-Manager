// One entry per manual picture.
//   file:    name under public/manual-pictures
//   route:   page to open
//   prepare: optional, runs after the page loads (open a dialog, switch a tab)
//   target:  returns the Locator that is photographed

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
  {
    file: 'calendar-adding-events.png',
    route: '/calendar',
    prepare: async (page) => {
      await page.getByRole('button', { name: 'Add event / leave' }).click()
      await page.getByLabel('Title').fill('Demo team briefing')
      await page.getByLabel('Start date').fill(isoDay(4))
      await page.getByLabel('End date (optional)').fill(isoDay(5))
      await page.getByLabel('Notes (optional)').fill('Demo notes')
      await page.waitForTimeout(SETTLE_MS)
    },
    target: (page) => page.getByRole('dialog'),
  },
  {
    file: 'flight-plans-submitting.png',
    route: '/flight-plans',
    prepare: async (page) => {
      await page.setViewportSize({ width: 1280, height: 1100 }) // tall enough to show the whole form
      await page.getByRole('button', { name: 'Submit Plan' }).click()
      const dialog = page.getByRole('dialog')
      await dialog.locator('#title').fill('Demo training flight')
      await dialog.locator('#planned-date-time').fill(`${isoDay(6)}T14:00`)
      await pickContaining(dialog.locator('#pilot'), 'Avery Brooks')
      await pickContaining(dialog.locator('#vehicle'), 'Demo One')
      await dialog.locator('#location').fill('Training Field A')
      await dialog.locator('#purpose').fill('Training')
      await dialog.locator('#max-altitude-ft').fill('200')
      await dialog.locator('#est-duration-min').fill('30')
      await page.waitForTimeout(SETTLE_MS)
    },
    target: (page) => page.getByRole('dialog'),
  },
  {
    file: 'flight-plans-reviewing.png',
    route: '/flight-plans',
    target: (page) => page.locator('table').locator('xpath=ancestor::div[contains(@class,"rounded-xl")][1]'),
  },
  {
    file: 'checklists-completing.png',
    route: '/checklists',
    prepare: async (page) => {
      await page.setViewportSize({ width: 1280, height: 1000 }) // tall enough to show the whole dialog
      await page.getByRole('button', { name: 'Complete Checklist' }).click()
      const dialog = page.getByRole('dialog')
      await pickContaining(dialog.locator('#template'), 'Demo Pre-Flight Checklist')
      await pickContaining(dialog.locator('#pilot'), 'Avery Brooks')
      await pickContaining(dialog.locator('#vehicle'), 'Demo One')
      await dialog.getByRole('button', { name: 'Tick Propellers undamaged and tight' }).click()
      await dialog.getByRole('button', { name: 'Tick Battery charged and seated' }).click()
      await page.waitForTimeout(SETTLE_MS)
    },
    target: (page) => page.getByRole('dialog'),
  },
  {
    file: 'checklists-templates.png',
    route: '/checklists',
    prepare: async (page) => {
      await page.getByRole('button', { name: 'Create Template' }).click()
      const dialog = page.getByRole('dialog')
      await dialog.locator('#name').fill('Demo Landing Checklist')
      await dialog.locator('#description').fill('Demo checklist for after each flight.')
      await dialog.getByPlaceholder('Item 1...').fill('Aircraft powered down')
      await dialog.getByRole('button', { name: 'Add Item' }).click()
      await dialog.getByPlaceholder('Item 2...').fill('Battery removed')
      await dialog.getByRole('button', { name: 'Add Item' }).click()
      await dialog.getByPlaceholder('Item 3...').fill('Propellers inspected')
      await page.waitForTimeout(SETTLE_MS)
    },
    target: (page) => page.getByRole('dialog'),
  },
  {
    file: 'flights-viewing-flights.png',
    route: '/flights',
    target: (page) => page.locator('div.flex.flex-wrap.items-end.gap-3').first(),
  },
  {
    file: 'flights-adding-flights-manually.png',
    route: '/flights',
    prepare: async (page) => {
      await page.setViewportSize({ width: 1280, height: 1500 }) // tall enough to show the whole form
      await page.getByRole('button', { name: 'Add Flight' }).click()
      const dialog = page.getByRole('dialog')
      await pickContaining(dialog.locator('#pilot'), 'Avery Brooks')
      await pickContaining(dialog.locator('#vehicle'), 'Demo One')
      await dialog.locator('#date').fill(isoDay(-1))
      await dialog.locator('#duration-seconds').fill('900')
      await pickContaining(dialog.locator('#purpose'), 'Training')
      await dialog.locator('#takeoff-address').fill('Training Field A')
      await dialog.locator('#landing-address').fill('Training Field A')
      await dialog.locator('#case-number').fill('DEMO-0001')
      await page.waitForTimeout(SETTLE_MS)
    },
    target: (page) => page.getByRole('dialog'),
  },
  {
    file: 'flights-reviewing-flights.png',
    route: '/flights',
    prepare: async (page) => {
      const boxes = page.getByRole('checkbox', { name: /^Select flight/ })
      await boxes.nth(0).check()
      await boxes.nth(1).check()
      await page.getByText(/\d+ selected/).waitFor()
    },
    target: (page) => page.getByText(/\d+ selected/).locator('xpath=..'),
  },
  {
    file: 'missions-adding-missions.png',
    route: '/missions',
    prepare: async (page) => {
      await page.setViewportSize({ width: 1280, height: 1300 }) // tall enough to show the whole form
      await page.getByRole('button', { name: 'Add Mission' }).click()
      const dialog = page.getByRole('dialog')
      await dialog.locator('#title').fill('Demo search support')
      await dialog.locator('#location').fill('Riverside Park')
      await dialog.locator('#man-hours').fill('2')
      await pickContaining(dialog.locator('#drone-used'), 'Demo One')
      await dialog.locator('#description').fill('Demo description of the mission.')
      await dialog.getByRole('button', { name: '+ Add Pilot' }).click()
      await pickContaining(dialog.locator('select').filter({ hasText: 'Select pilot...' }), 'Avery Brooks')
      await dialog.locator('select').filter({ hasText: 'Role...' }).selectOption('PIC')
      await dialog.getByPlaceholder('Hrs').fill('2')
      await page.waitForTimeout(SETTLE_MS)
    },
    target: (page) => page.getByRole('dialog'),
  },
  {
    file: 'training-adding-training.png',
    route: '/training',
    prepare: async (page) => {
      await page.setViewportSize({ width: 1280, height: 1300 }) // tall enough to show the whole form
      await page.getByRole('button', { name: 'Add Training' }).click()
      const dialog = page.getByRole('dialog')
      await dialog.locator('#title').fill('Demo proficiency session')
      await dialog.locator('#location').fill('Training Field A')
      await dialog.locator('#instructor').fill('Demo Instructor')
      await dialog.locator('#man-hours').fill('3')
      await pickContaining(dialog.locator('#drone-used'), 'Demo One')
      await dialog.locator('#objectives').fill('Demo objectives for the session.')
      await dialog.getByRole('button', { name: '+ Add Pilot' }).click()
      await pickContaining(dialog.locator('select').filter({ hasText: 'Select pilot...' }), 'Avery Brooks')
      await dialog.locator('select').filter({ hasText: 'Role...' }).selectOption('Student')
      await dialog.getByPlaceholder('Hrs').fill('3')
      await page.waitForTimeout(SETTLE_MS)
    },
    target: (page) => page.getByRole('dialog'),
  },
  {
    file: 'fleet-fleet-list.png',
    route: '/fleet',
    prepare: async (page) => {
      await page.getByPlaceholder('Search vehicles...').fill('Demo')
      await page.getByRole('link', { name: 'Demo One', exact: true }).waitFor()
    },
    target: (page) => page.locator('div.space-y-4').filter({ has: page.locator('table') }).last(),
  },
  {
    file: 'fleet-adding-a-vehicle.png',
    route: '/fleet',
    prepare: async (page) => {
      await page.setViewportSize({ width: 1280, height: 1000 }) // tall enough to show the whole form
      await page.getByRole('button', { name: 'Add Vehicle' }).click()
      const dialog = page.getByRole('dialog')
      await dialog.locator('#field-serial_number').fill('DEMO-0004')
      await dialog.locator('#field-manufacturer').fill('Skydio')
      await dialog.locator('#field-model').fill('X10')
      await dialog.locator('#field-nickname').fill('Demo Four')
      await dialog.locator('#field-acquired_date').fill(isoDay(-30))
      await page.waitForTimeout(SETTLE_MS)
    },
    target: (page) => page.getByRole('dialog'),
  },
  {
    file: 'fleet-battery-readings.png',
    route: '/fleet',
    prepare: async (page) => {
      await page.getByRole('button', { name: 'Batteries' }).click()
      await page.getByRole('link', { name: 'Demo Battery 1', exact: true }).click()
      await page.getByRole('button', { name: 'Record Reading' }).click()
      const dialog = page.getByRole('dialog')
      await dialog.locator('#health-1').fill('91')
      await dialog.locator('#cycle-count-1').fill('30')
      await dialog.locator('#voltage').fill('16.4')
      await dialog.locator('#notes-1').fill('Demo monthly check')
      await page.waitForTimeout(SETTLE_MS)
    },
    target: (page) => page.getByRole('dialog'),
  },
  {
    file: 'registrations-faa-registrations.png',
    route: '/fleet',
    prepare: async (page) => {
      await page.getByRole('link', { name: 'Demo One', exact: true }).click()
      await page.getByRole('heading', { name: 'FAA Registration' }).waitFor()
    },
    target: (page) => page.getByRole('heading', { name: 'FAA Registration' }).locator('xpath=ancestor::div[contains(@class,"rounded-xl")][1]'),
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
  {
    file: 'checkouts-checking-equipment-out.png',
    route: '/checkouts',
    prepare: async (page) => {
      await page.getByRole('button', { name: 'Check Out', exact: true }).click()
      const dialog = page.getByRole('dialog')
      await dialog.locator('#checkout-type').selectOption('battery')
      await dialog.locator('#checkout-item option', { hasText: 'Demo Battery 3' }).waitFor({ state: 'attached' })
      await pickContaining(dialog.locator('#checkout-item'), 'Demo Battery 3')
      await pickContaining(dialog.locator('#checkout-pilot'), 'Riley Chen')
      await dialog.getByLabel('Expected return (optional)').fill(isoDay(2))
      await dialog.getByLabel('Notes (optional)').fill('Demo training day')
      await page.waitForTimeout(SETTLE_MS)
    },
    target: (page) => page.getByRole('dialog'),
  },
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
    target: (page) => page.getByRole('heading', { name: 'Avery Brooks' }).locator('xpath=ancestor::div[contains(@class,"rounded-xl")][1]'),
  },
  {
    file: 'pilots-needs-attention.png',
    route: '/pilots',
    prepare: async (page) => {
      await page.getByRole('link', { name: /Jordan Ellis/ }).click()
      await page.getByRole('heading', { name: 'Needs Attention' }).waitFor()
      await page.getByText('Certification expiring').first().waitFor()
    },
    target: (page) => page.getByRole('heading', { name: 'Needs Attention' }).locator('xpath=ancestor::div[contains(@class,"rounded-xl")][1]'),
  },
  {
    file: 'pilots-pilot-currency.png',
    route: '/settings',
    prepare: async (page) => {
      await page.getByRole('button', { name: 'New Rule' }).click()
      const dialog = page.getByRole('dialog')
      await dialog.locator('#rule-name').fill('Demo quarterly currency')
      await dialog.locator('#rule-desc').fill('Demo rule for the manual')
      await dialog.locator('#rule-hours').fill('5')
      await dialog.locator('#rule-days').fill('90')
      await dialog.locator('#rule-flights').fill('3')
      await page.waitForTimeout(SETTLE_MS)
    },
    target: (page) => page.getByRole('dialog'),
  },
  {
    file: 'certifications-certification-matrix.png',
    route: '/certifications',
    prepare: async (page) => {
      await page.getByLabel('Hide empty').check()
      await page.getByRole('row', { name: /Avery Brooks/ }).waitFor()
    },
    target: (page) => page.locator('table').locator('xpath=ancestor::div[contains(@class,"rounded-xl")][1]'),
  },
  {
    file: 'certifications-editing-a-certification.png',
    route: '/certifications',
    prepare: async (page) => {
      await page.setViewportSize({ width: 1280, height: 1000 })
      await page.getByRole('row', { name: /Jordan Ellis/ }).locator('td').filter({ hasText: 'expiring soon' }).first().click()
      const dialog = page.getByRole('dialog')
      await dialog.getByLabel('Notes').fill('Demo note: certificate copy filed')
      await page.waitForTimeout(SETTLE_MS)
    },
    target: (page) => page.getByRole('dialog'),
  },
  {
    file: 'certifications-renewing-a-certification.png',
    route: '/certifications',
    prepare: async (page) => {
      await page.getByRole('row', { name: /Jordan Ellis/ }).locator('td').filter({ hasText: 'expiring soon' }).first().click()
      const dialog = page.getByRole('dialog')
      await dialog.getByRole('button', { name: 'Renew', exact: true }).click()
      await dialog.getByLabel('New Issue Date').fill(isoDay(0))
      await page.waitForTimeout(SETTLE_MS)
    },
    target: (page) => page.getByRole('dialog'),
  },
  {
    file: 'compliance-compliance-score.png',
    route: '/compliance',
    prepare: async (page) => {
      await page.getByRole('heading', { name: 'Compliance Dashboard' }).waitFor()
      await page.waitForTimeout(1500) // let the score ring finish drawing
    },
    target: (page) => page.locator('div.space-y-6').filter({ has: page.getByRole('heading', { name: 'Compliance Dashboard' }) }).last().locator('xpath=./div[2]'),
  },
  {
    file: 'operating-authority-operating-authority.png',
    route: '/operating-authority',
    prepare: async (page) => {
      await page.getByRole('button', { name: 'Add Authority' }).click()
      const dialog = page.getByRole('dialog')
      await dialog.getByLabel('Title').fill('Demo blanket public safety COA')
      await dialog.getByLabel('COA / waiver number').fill('DEMO-COA-0001')
      await dialog.getByLabel('Issue date').fill(isoDay(-200))
      await dialog.getByLabel('Expiry date').fill(isoDay(165))
      await dialog.getByLabel('Notes').fill('Demo notes: altitude ceiling 400 ft')
      await page.waitForTimeout(SETTLE_MS)
    },
    target: (page) => page.getByRole('dialog'),
  },
  {
    file: 'incidents-incident-reporting.png',
    route: '/incidents',
    prepare: async (page) => {
      await page.setViewportSize({ width: 1280, height: 1300 })
      await page.getByRole('button', { name: 'New Report' }).click()
      const dialog = page.getByRole('dialog')
      await dialog.locator('#severity').selectOption('minor')
      await dialog.locator('#title').fill('Demo rough landing')
      await dialog.locator('#category').selectOption('near_miss')
      await dialog.locator('#location').fill('Training Field A')
      await dialog.locator('#description').fill('Demo description: the aircraft landed harder than planned.')
      await pickContaining(dialog.locator('#pilot'), 'Avery Brooks')
      await pickContaining(dialog.locator('#vehicle'), 'Demo One')
      await dialog.locator('#damage-description').fill('None')
      await page.waitForTimeout(SETTLE_MS)
    },
    target: (page) => page.getByRole('dialog'),
  },
  {
    file: 'maintenance-adding-a-maintenance-record.png',
    route: '/maintenance',
    prepare: async (page) => {
      await page.setViewportSize({ width: 1280, height: 1000 })
      await page.getByRole('button', { name: 'Add Maintenance' }).click()
      const dialog = page.getByRole('dialog')
      await pickContaining(dialog.locator('#entity'), 'Demo One')
      await dialog.locator('#maintenance-type').selectOption('inspection')
      await dialog.locator('#description').fill('Demo propeller and motor inspection')
      await pickContaining(dialog.locator('#performed-by'), 'Avery Brooks')
      await dialog.locator('#performed-date').fill(isoDay(0))
      await dialog.locator('#cost').fill('25')
      await dialog.locator('#next-due-date').fill(isoDay(90))
      await dialog.locator('#notes').fill('Demo notes: no damage found')
      await page.waitForTimeout(SETTLE_MS)
    },
    target: (page) => page.getByRole('dialog'),
  },
  {
    file: 'maintenance-schedules-and-tasks.png',
    route: '/maintenance',
    prepare: async (page) => {
      await page.setViewportSize({ width: 1280, height: 1000 })
      await page.getByRole('button', { name: 'Add Schedule / Task' }).click()
      const dialog = page.getByRole('dialog')
      await dialog.locator('#name').fill('Demo monthly airframe check')
      await pickContaining(dialog.locator('#entity-1'), 'Demo One')
      await dialog.locator('#frequency').selectOption('monthly')
      await dialog.locator('#next-due').fill(isoDay(30))
      await dialog.locator('#description-1').fill('Demo description: check arms, props and landing gear.')
      await page.waitForTimeout(SETTLE_MS)
    },
    target: (page) => page.getByRole('dialog'),
  },
  {
    file: 'documents-folders-and-finding-documents.png',
    route: '/documents',
    prepare: async (page) => {
      await page.getByRole('treeitem', { name: /Demo Procedures/ }).click()
      await page.waitForTimeout(SETTLE_MS)
    },
    target: (page) => page.getByRole('tree', { name: 'Document folders' }).locator('xpath=ancestor::div[contains(@class,"rounded-xl")][1]'),
  },
  {
    file: 'media-uploading-photos.png',
    route: '/media',
    prepare: async (page) => {
      await page.setViewportSize({ width: 1280, height: 1000 })
      await page.getByRole('button', { name: 'Upload' }).first().click()
      const dialog = page.getByRole('dialog')
      await dialog.getByLabel('Title').fill('Demo training field')
      await dialog.getByLabel('Description').fill('Demo description')
      await dialog.getByLabel('Date Taken').fill(isoDay(-3))
      await page.waitForTimeout(SETTLE_MS)
    },
    target: (page) => page.getByRole('dialog'),
  },
  {
    file: 'reports-building-a-report.png',
    route: '/reports',
    prepare: async (page) => {
      await page.getByRole('button', { name: 'Last 90d' }).click()
      await page.waitForTimeout(SETTLE_MS)
    },
    target: (page) => page.getByRole('heading', { name: 'Report Builder' }).locator('xpath=ancestor::div[contains(@class,"rounded-xl")][1]'),
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
    target: (page) => page.getByRole('heading', { name: 'Email Digest' }).locator('xpath=ancestor::div[contains(@class,"rounded-xl")][1]'),
  },
  {
    file: 'settings-api-tokens.png',
    route: '/settings',
    prepare: async (page) => {
      await page.getByRole('button', { name: 'API Tokens' }).click()
      await page.getByRole('button', { name: 'Create Token' }).click()
      const dialog = page.getByRole('dialog')
      await dialog.locator('#token-name').fill('Demo dashboard')
      await dialog.locator('#token-expiry').selectOption('90')
      await page.waitForTimeout(SETTLE_MS)
    },
    target: (page) => page.getByRole('dialog'),
  },
  {
    file: 'backup-in-app-backup.png',
    route: '/settings',
    prepare: async (page) => {
      await page.getByRole('heading', { name: 'Backup & Restore' }).waitFor()
    },
    target: (page) => page.getByRole('heading', { name: 'Backup & Restore' }).locator('xpath=ancestor::div[contains(@class,"rounded-xl")][1]'),
  },
]
