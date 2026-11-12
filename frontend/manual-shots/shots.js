// One entry per manual picture.
//   file:    name under public/manual
//   route:   page to open
//   prepare: optional, runs after the page loads (open a dialog, switch a tab)
//   target:  returns the Locator that is photographed
export const SHOTS = [
  {
    file: 'manual-layout-switch.png',
    route: '/manual',
    target: (page) => page.getByRole('group', { name: 'Manual layout' }).locator('xpath=..'),
  },
]
