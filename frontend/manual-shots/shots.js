// One entry per manual picture.
//   file:    name under public/manual
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
]
