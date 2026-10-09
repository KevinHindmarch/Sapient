// End-to-end smoke test of a built Sapient desktop app.
//   node e2e/smoke.mjs <path-to-Sapient-executable> [screenshot-dir]
// Uses a throwaway profile, so it never touches the user's real data.
import { _electron as electron } from 'playwright-core'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

const [exe, shots = os.tmpdir()] = process.argv.slice(2)
if (!exe) {
  console.error('usage: node e2e/smoke.mjs <Sapient executable> [screenshot dir]')
  process.exit(2)
}
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'sapient-e2e-'))
const env = { ...process.env, HOME: profile, XDG_CONFIG_HOME: path.join(profile, '.config'), APPDATA: profile }
const isRootLinux = process.platform === 'linux' && process.getuid?.() === 0
const app = await electron.launch({
  executablePath: exe,
  args: isRootLinux ? ['--no-sandbox'] : [],
  env,
  timeout: 180_000,
})
const userData = await app.evaluate(({ app }) => app.getPath('userData'))
const logs = await app.evaluate(({ app }) => app.getPath('logs'))
const errors = []
const page = await app.firstWindow()
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
page.on('pageerror', (e) => errors.push(String(e)))

function check(condition, message) {
  if (!condition) throw new Error('FAILED: ' + message)
  console.log('ok -', message)
}

await page.waitForURL(/index\.html/, { timeout: 180_000 })
await page.waitForSelector('text=Welcome back', { timeout: 60_000 })
await page.screenshot({ path: path.join(shots, 'dashboard.png') })
const bridge = await page.evaluate(() => ({
  base: window.sapient?.apiBase ?? '', token: window.sapient?.apiToken ?? '', node: typeof window.require,
}))
check(/^http:\/\/127\.0\.0\.1:\d+\/api$/.test(bridge.base), 'engine API is on 127.0.0.1')
check(bridge.token.length >= 32, 'per-launch API token provided to the UI')
check(bridge.node === 'undefined', 'Node.js is not exposed to the UI')

const unauthorised = (await fetch(bridge.base + '/profile')).status
check(unauthorised === 401, 'API refuses requests without the token')

await page.evaluate(() => { location.hash = '#/brokerage' })
await page.waitForSelector('text=Set up TWS', { timeout: 30_000 })
await page.screenshot({ path: path.join(shots, 'brokerage.png') })
check(true, 'Brokerage setup guide renders')

await page.evaluate(() => { location.hash = '#/settings' })
await page.waitForSelector('h2:has-text("Local profile")', { timeout: 30_000 })
const shownDir = (await page.locator('.font-mono').first().textContent())?.trim()
check(shownDir === userData, `Settings shows the data folder (${shownDir})`)
check(fs.existsSync(path.join(userData, 'sapient.db')), 'database created in the data folder')
const version = await app.evaluate(({ app }) => app.getVersion())
await page.waitForSelector(`text=You have Sapient ${version}`, { timeout: 30_000 })
check(true, `Updates card shows the installed version (${version})`)

await page.evaluate(() => { window.location.href = 'https://example.com' }).catch(() => {})
await page.waitForTimeout(1000)
check(page.url().startsWith('app://sapient/'), 'navigation to external sites is blocked')

await app.close()
await new Promise((resolve) => setTimeout(resolve, 3000))
const log = fs.readFileSync(path.join(logs, 'engine.log'), 'utf8')
check(/engine exited/.test(log), 'engine process stops when the app closes')
check(errors.length === 0, `no console errors (${JSON.stringify(errors)})`)
console.log('desktop smoke test passed')
