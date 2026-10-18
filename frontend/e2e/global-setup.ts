import { chromium, type FullConfig } from '@playwright/test'

/**
 * Load the app once before the tests. A fresh Vite dev server pre-bundles dependencies on its
 * first browser visit and can reset connections while it does, which would fail the first test.
 */
export default async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0].use.baseURL ?? 'http://localhost:5173'
  const browser = await chromium.launch()
  const page = await browser.newPage()
  for (let attempt = 1; attempt <= 5; attempt++) {
    try {
      await page.goto(baseURL, { waitUntil: 'networkidle', timeout: 30_000 })
      await page.getByRole('button', { name: 'Create room' }).waitFor({ timeout: 15_000 })
      break
    } catch (error) {
      if (attempt === 5) throw error
      await page.waitForTimeout(2_000)
    }
  }
  await browser.close()
}
