// End-to-end smoke test of a built Sapient desktop app.
//   node e2e/smoke.mjs <path-to-Sapient-executable> [screenshot-dir] [--mode fresh|seed|upgraded] [--profile dir]
// Modes:
//   fresh     (default) brand-new data folder: the welcome wizard must appear; complete it,
//             run every check, then save a portfolio ("CI Portfolio") for later upgrade checks.
//   seed      run an older release: just save "CI Portfolio" through its API (no wizard checks).
//   upgraded  data from an earlier run must still be there: no wizard, "CI Portfolio" still saved.
// --profile reuses a home/config folder between runs (Linux/macOS); on Windows Electron always
// keeps its data in the real %APPDATA%\Sapient, exactly like an installed app.
import { _electron as electron } from 'playwright-core'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

const positional = []
const options = { mode: 'fresh', profile: '' }
const argv = process.argv.slice(2)
for (let i = 0; i < argv.length; i++) {
  if (argv[i] === '--mode') options.mode = argv[++i]
  else if (argv[i] === '--profile') options.profile = argv[++i]
  else positional.push(argv[i])
}
const [exe, shots = os.tmpdir()] = positional
if (!exe || !['fresh', 'seed', 'upgraded'].includes(options.mode)) {
  console.error('usage: node e2e/smoke.mjs <Sapient executable> [screenshot dir] [--mode fresh|seed|upgraded] [--profile dir]')
  process.exit(2)
}
const mode = options.mode
const PORTFOLIO = 'CI Portfolio'
const profile = options.profile || fs.mkdtempSync(path.join(os.tmpdir(), 'sapient-e2e-'))
fs.mkdirSync(profile, { recursive: true })
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
const shot = (name) => page.screenshot({ path: path.join(shots, `${mode}-${name}.png`) })

console.log(`mode: ${mode}, data folder: ${userData}`)
await page.waitForURL(/index\.html/, { timeout: 180_000 })
const bridge = await page.evaluate(() => ({
  base: window.sapient?.apiBase ?? '', token: window.sapient?.apiToken ?? '', node: typeof window.require,
}))
check(/^http:\/\/127\.0\.0\.1:\d+\/api$/.test(bridge.base), 'engine API is on 127.0.0.1')
check(bridge.token.length >= 32, 'per-launch API token provided to the UI')
const api = async (route, init = {}) => {
  const res = await fetch(bridge.base + route, {
    ...init, headers: { Authorization: `Bearer ${bridge.token}`, 'Content-Type': 'application/json', ...(init.headers ?? {}) },
  })
  if (!res.ok) throw new Error(`${init.method ?? 'GET'} ${route} -> ${res.status} ${await res.text()}`)
  return res.json()
}
const savePortfolio = () => api('/portfolio/save', {
  method: 'POST',
  body: JSON.stringify({ name: PORTFOLIO, optimization_results: { weights: {} }, investment_amount: 10000 }),
})
const portfolioNames = async () => (await api('/portfolio/list')).map((p) => p.name)

if (mode === 'seed') {
  // Older releases may or may not have the welcome wizard; finish it through the API if shown.
  await page.locator('text=Welcome back').or(page.locator('[data-testid="onboarding"]')).first()
    .waitFor({ timeout: 60_000 })
  if (await page.locator('[data-testid="onboarding"]').count()) {
    await api('/profile', { method: 'PUT', body: JSON.stringify({ display_name: 'CI Tester', complete_onboarding: true }) })
  }
  await savePortfolio()
  check((await portfolioNames()).includes(PORTFOLIO), `older release saved "${PORTFOLIO}"`)
  await shot('dashboard')
  await app.close()
  console.log('seed run finished')
  process.exit(0)
}

if (mode === 'fresh') {
  await page.waitForSelector('[data-testid="onboarding"]', { timeout: 60_000 })
  await shot('wizard-welcome')
  check(true, 'first run shows the welcome wizard')
  await page.click('button:has-text("Get started")')
  await page.fill('input[placeholder="Your first name"]', 'CI Tester')
  await page.click('button:has-text("Continue")')
  await page.click('button:has-text("Dark")')
  check(await page.evaluate(() => document.documentElement.classList.contains('dark')), 'theme choice previews straight away')
  await page.click('button:has-text("Continue")')
  await page.click('button:has-text("Later")')
  await page.click('button:has-text("Continue")')
  await page.waitForSelector("text=You're all set, CI Tester!")
  await shot('wizard-done')
  await page.click('button:has-text("Open Sapient")')
  const profileAfter = await api('/profile')
  check(profileAfter.onboarded && profileAfter.display_name === 'CI Tester' && profileAfter.theme === 'dark',
    'wizard saved name and theme')
}

await page.waitForSelector('text=Welcome back', { timeout: 60_000 })
check((await page.locator('[data-testid="onboarding"]').count()) === 0, 'dashboard shown (no wizard)')
await shot('dashboard')
check(bridge.node === 'undefined', 'Node.js is not exposed to the UI')
check((await fetch(bridge.base + '/profile')).status === 401, 'API refuses requests without the token')

const profileNow = await api('/profile')
if (mode === 'upgraded') {
  check(profileNow.onboarded, 'upgrade does not repeat the welcome wizard')
  check((await portfolioNames()).includes(PORTFOLIO), `"${PORTFOLIO}" is still there after the upgrade`)
}
const expectedTheme = profileNow.theme === 'dark'
check(await page.evaluate(() => document.documentElement.classList.contains('dark')) === expectedTheme,
  `saved theme (${profileNow.theme}) is applied`)

// The TWS connector process starts alongside the engine and reports in.
let tws = null
for (let i = 0; i < 60 && !tws?.worker_running; i++) {
  tws = await api('/tws/status')
  if (!tws.worker_running) await new Promise((r) => setTimeout(r, 1000))
}
check(tws?.worker_running, `TWS connector is running (state ${tws?.state})`)
// Attached, not visible: a narrow window hides the sidebar (the pill is then in the menu).
await page.waitForSelector('[data-testid="tws-pill"]', { state: 'attached', timeout: 30_000 })

await page.evaluate(() => { location.hash = '#/brokerage' })
await page.waitForSelector('[data-testid="tws-status"]', { timeout: 30_000 })
await page.waitForSelector('text=Step 3 — Test the connection', { timeout: 30_000 })
await shot('brokerage')
check(true, 'Interactive Brokers setup page renders')

await page.evaluate(() => { location.hash = '#/settings' })
await page.waitForSelector('h2:has-text("Local profile")', { timeout: 30_000 })
await page.waitForSelector('[data-testid="data-dir"]', { timeout: 30_000 })
const shownDir = (await page.locator('[data-testid="data-dir"]').textContent())?.trim()
check(shownDir === userData, `Settings shows the data folder (${shownDir})`)
check(fs.existsSync(path.join(userData, 'sapient.db')), 'database created in the data folder')
const version = await app.evaluate(({ app }) => app.getVersion())
await page.waitForSelector(`text=You have Sapient ${version}`, { timeout: 30_000 })
check(true, `Updates card shows the installed version (${version})`)

await page.evaluate(() => { window.location.href = 'https://example.com' }).catch(() => {})
await page.waitForTimeout(1000)
check(page.url().startsWith('app://sapient/'), 'navigation to external sites is blocked')

if (mode === 'fresh' && !(await portfolioNames()).includes(PORTFOLIO)) {
  await savePortfolio()
  check((await portfolioNames()).includes(PORTFOLIO), `saved "${PORTFOLIO}" for the upgrade check`)
}

await app.close()
await new Promise((resolve) => setTimeout(resolve, 3000))
const log = fs.readFileSync(path.join(logs, 'engine.log'), 'utf8')
check(/engine exited/.test(log), 'engine process stops when the app closes')
const connectorLog = fs.readFileSync(path.join(logs, 'tws-connector-process.log'), 'utf8')
check(/engine exited/.test(connectorLog), 'TWS connector stops when the app closes')
check(errors.length === 0, `no console errors (${JSON.stringify(errors)})`)
console.log(`desktop smoke test passed (${mode})`)
