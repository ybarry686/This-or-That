import { expect, test, type Page } from '@playwright/test'

const shot = (page: Page, name: string) =>
  page.screenshot({ path: `test-results/screens/${name}.png`, fullPage: true })

test('two players play a full game from lobby to champion', async ({ browser }) => {
  const hostContext = await browser.newContext()
  const guestContext = await browser.newContext({ viewport: { width: 390, height: 844 } })
  const host = await hostContext.newPage()
  const guest = await guestContext.newPage()

  // Host creates the room.
  await host.goto('/')
  await shot(host, '01-landing')
  await host.getByLabel('Question').fill('Where should we eat?')
  await host.locator('#create-nickname').fill('Ana')
  await host.getByRole('button', { name: 'Create room' }).click()
  await expect(host.getByRole('heading', { name: 'Where should we eat?' })).toBeVisible()
  await expect(host.getByText(/save your host recovery link/i)).toBeVisible()
  const code = (await host.locator('strong').filter({ hasText: /^[A-Z0-9]{6}$/ }).innerText()).trim()
  await shot(host, '02-lobby-host')
  await host.getByRole('button', { name: 'I saved it' }).click()

  // Guest joins on a phone-sized screen.
  await guest.goto(`/r/${code}`)
  await guest.getByLabel('Your nickname').fill('Sam')
  await guest.getByRole('button', { name: 'Join' }).click()
  await expect(guest.getByRole('heading', { name: 'Where should we eat?' })).toBeVisible()

  // Presence reaches the host live.
  await expect(host.getByLabel('Sam is online')).toBeVisible()

  // Both submit; the guest only sees a count, the host sees everything.
  await host.getByRole('textbox', { name: 'Your option' }).fill('Pizza')
  await host.getByRole('button', { name: 'Add option' }).click()
  await guest.getByRole('textbox', { name: 'Your option' }).fill('Tacos')
  await guest.getByRole('button', { name: 'Add option' }).click()
  await expect(host.getByText('2 options submitted')).toBeVisible()
  await expect(guest.getByText('2 options submitted')).toBeVisible()
  await shot(guest, '03-lobby-guest-mobile')

  // Host starts; both land on the matchup once the reveal pause ends.
  await host.getByRole('button', { name: 'Start tournament' }).click()
  await expect(host.getByRole('status', { name: /fight/i })).toBeVisible()
  await shot(host, '04a-round-intro')
  for (const page of [host, guest]) {
    await expect(page.getByRole('region', { name: 'Current matchup' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Vote for Pizza' })).toBeEnabled()
  }
  await shot(host, '04-matchup-host')
  await shot(guest, '05-matchup-guest-mobile')

  // Everyone votes, so the matchup closes early and the champion is crowned on both screens.
  await host.getByRole('button', { name: 'Vote for Pizza' }).click()
  await expect(host.getByText('1/2 voted')).toBeVisible()
  await guest.keyboard.press('ArrowLeft')
  for (const page of [host, guest]) {
    await expect(page.getByRole('heading', { name: /champion/i })).toContainText('Pizza')
  }
  await expect(host.getByRole('status', { name: /champion/i })).toBeVisible()
  await shot(host, '05a-champion-reveal')
  await expect(host.getByText(/pizza beat tacos 2–0/i)).toBeVisible()
  await shot(host, '06-champion-host')
  await shot(guest, '07-champion-guest-mobile')

  await hostContext.close()
  await guestContext.close()
})
