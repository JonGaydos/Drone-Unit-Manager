import { defineConfig, devices } from '@playwright/test'
import base from './playwright.config.js'

// Takes the pictures for the in-app manual. Same backend, dev server and
// global setup as the e2e suite (a fresh local database), but its own folder.
export default defineConfig({
  testDir: 'manual-shots',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  globalSetup: base.globalSetup,
  use: {
    baseURL: 'http://localhost:5173',
    storageState: 'e2e/.auth/admin.json',
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 1,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 },
    },
  ],
  webServer: base.webServer,
})
