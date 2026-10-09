// Sapient desktop shell: one secure window, the bundled UI served from app://,
// and the local Sapient engine supervised in the background.

import { app, BrowserWindow, ipcMain, Menu, net, protocol, session, shell } from 'electron'
import fs from 'node:fs'
import path from 'node:path'
import { pathToFileURL } from 'node:url'
import { EngineCommand, EngineState, EngineSupervisor, haltOffline } from './engine'
import { errorPage, loadingPage, SHELL_SCRIPT } from './pages'
import { registerUpdater, RELEASES_URL } from './updater'
import { Alerts } from './alerts'

const SCHEME = 'app'
const HOST = 'sapient'
const APP_ORIGIN = `${SCHEME}://${HOST}`
const devRendererUrl = process.env.SAPIENT_DEV_RENDERER_URL // e.g. Vite on http://127.0.0.1:5000

protocol.registerSchemesAsPrivileged([
  { scheme: SCHEME, privileges: { standard: true, secure: true, supportFetchAPI: true } },
])

let mainWindow: BrowserWindow | null = null
let engine: EngineSupervisor
let connector: EngineSupervisor | null = null  // TWS connector for the paper login (+ market-hours scheduler)
let liveConnector: EngineSupervisor | null = null  // TWS connector for the live (real-money) login
let shellPage = ''  // HTML for app://sapient/__shell while starting or failed
let alerts: Alerts | null = null  // tray, notifications, emergency stop
let quitting = false
let startHidden = process.argv.includes('--hidden')

function rendererDir(): string {
  return path.join(__dirname, '..', '..', 'renderer')
}

function engineCommand(): EngineCommand {
  if (app.isPackaged) {
    const exe = process.platform === 'win32' ? 'sapient-api.exe' : 'sapient-api'
    return { command: path.join(process.resourcesPath, 'engine', exe), args: [] }
  }
  // Development: the repository's Python environment (created by `uv sync`).
  const repo = path.resolve(__dirname, '..', '..', '..')
  const python = process.platform === 'win32'
    ? path.join(repo, '.venv', 'Scripts', 'python.exe')
    : path.join(repo, '.venv', 'bin', 'python')
  return { command: python, args: [path.join(repo, 'backend', 'desktop_main.py')], cwd: repo }
}

function logDir(): string {
  return app.getPath('logs')
}

function contentSecurityPolicy(): string {
  const state = engine?.current
  const api = state?.kind === 'ready' ? `http://127.0.0.1:${state.info.port}` : ''
  return [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",  // React style attributes
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    `connect-src 'self' ${api}`.trim(),
    "object-src 'none'",
    "base-uri 'none'",
    "frame-ancestors 'none'",
    "form-action 'none'",
  ].join('; ')
}

function serveApp(): void {
  protocol.handle(SCHEME, async (request) => {
    const url = new URL(request.url)
    if (url.host !== HOST) return new Response('Not found', { status: 404 })
    const headers = { 'Content-Security-Policy': contentSecurityPolicy() }
    if (url.pathname === '/__shell') {
      return new Response(shellPage, { headers: { ...headers, 'Content-Type': 'text/html; charset=utf-8' } })
    }
    if (url.pathname === '/__shell.js') {
      return new Response(SHELL_SCRIPT, { headers: { ...headers, 'Content-Type': 'text/javascript' } })
    }
    const root = rendererDir()
    const relative = decodeURIComponent(url.pathname === '/' ? '/index.html' : url.pathname)
    const file = path.normalize(path.join(root, relative))
    if (!file.startsWith(root + path.sep) || !fs.existsSync(file)) {
      return new Response('Not found', { status: 404 })
    }
    const response = await net.fetch(pathToFileURL(file).toString())
    const merged = new Headers(response.headers)
    merged.set('Content-Security-Policy', headers['Content-Security-Policy'])
    return new Response(response.body, { status: response.status, headers: merged })
  })
}

function isAppUrl(target: string): boolean {
  if (target.startsWith(APP_ORIGIN + '/')) return true
  return !!devRendererUrl && target.startsWith(devRendererUrl)
}

function showShell(html: string): void {
  shellPage = html
  mainWindow?.loadURL(`${APP_ORIGIN}/__shell`)
}

function showApp(): void {
  if (!mainWindow) return
  mainWindow.loadURL(devRendererUrl ?? `${APP_ORIGIN}/index.html`)
}

function onEngineState(state: EngineState): void {
  if (state.kind === 'starting') {
    showShell(loadingPage(state.attempt > 1 ? 'Restarting the Sapient engine…' : 'Preparing your local engine and data…'))
  } else if (state.kind === 'ready') {
    showApp()
  } else if (state.kind === 'failed') {
    showShell(errorPage(state.message, path.join(logDir(), 'engine.log')))
  }
}

function iconPath(): string {
  return path.join(__dirname, '..', '..', 'build', 'icon.png')
}

/**
 * A restore chosen in Settings → Backups is applied here, before the engine opens the
 * database: the current file is kept as backups/before-restore-<time>.db.
 */
function applyPendingRestore(dataDir: string, logFile: string): void {
  const requestFile = path.join(dataDir, 'restore-request.json')
  if (!fs.existsSync(requestFile)) return
  const note = (line: string) => fs.appendFileSync(logFile, `[${new Date().toISOString()}] ${line}\n`)
  try {
    const request = JSON.parse(fs.readFileSync(requestFile, 'utf8')) as { backup?: string }
    const name = String(request.backup ?? '')
    const source = path.join(dataDir, 'backups', name)
    if (!/^[A-Za-z0-9._-]+\.db$/.test(name) || !fs.existsSync(source)) throw new Error(`backup ${name} not found`)
    const database = path.join(dataDir, 'sapient.db')
    const stamp = new Date().toISOString().replace(/[:.]/g, '-')
    if (fs.existsSync(database)) fs.copyFileSync(database, path.join(dataDir, 'backups', `before-restore-${stamp}.db`))
    for (const extra of ['-wal', '-shm']) fs.rmSync(database + extra, { force: true })
    fs.copyFileSync(source, database)
    note(`restored database from backups/${name}`)
  } catch (error) {
    note(`restore failed: ${(error as Error).message}`)
  } finally {
    fs.rmSync(requestFile, { force: true })
  }
}

function showWindow(): void {
  startHidden = false
  if (!mainWindow) { createWindow(); return }
  if (mainWindow.isMinimized()) mainWindow.restore()
  mainWindow.show()
  mainWindow.focus()
}

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    title: 'Sapient',
    icon: iconPath(),
    backgroundColor: '#f8fafc',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, '..', 'preload', 'index.js'),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      webSecurity: true,
      spellcheck: false,
    },
  })
  // Started with Windows: stay in the tray until the user opens Sapient.
  mainWindow.once('ready-to-show', () => { if (!startHidden) mainWindow?.show() })
  mainWindow.on('closed', () => { mainWindow = null })
  // Optional: closing the window keeps Sapient (and its automatic checks) running in the tray.
  mainWindow.on('close', (event) => {
    if (!quitting && alerts?.closeToTray) {
      event.preventDefault()
      mainWindow?.hide()
      alerts.hiddenToTray()
    }
  })

  // Never navigate away from the app; open https links in the user's browser.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('https://')) void shell.openExternal(url)
    return { action: 'deny' }
  })
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (!isAppUrl(url)) event.preventDefault()
  })

  onEngineState(engine.current)
}

/** A TWS connector that keeps crashing is reported straight away (it retries by itself every few minutes). */
function watchConnector(supervisor: EngineSupervisor, label: string): void {
  supervisor.on('state', (state: EngineState) => {
    if (state.kind === 'failed' && !quitting) {
      alerts?.warn(`Sapient's ${label} TWS connector stopped`,
        'Orders, fills and cancels for that account are paused. Sapient retries in 5 minutes; '
        + 'see Brokerage, or open the log folder from Settings.')
    }
  })
}

function registerIpc(): void {
  ipcMain.on('sapient:config', (event) => {
    const state = engine.current
    event.returnValue = state.kind === 'ready'
      ? { apiBase: state.info.apiBase, apiToken: state.info.token, appVersion: app.getVersion() }
      : { apiBase: '', apiToken: '', appVersion: app.getVersion() }
  })
  ipcMain.on('sapient:open-external', (_event, url: unknown) => {
    if (typeof url === 'string' && url.startsWith('https://')) void shell.openExternal(url)
  })
  ipcMain.on('sapient:open-logs', () => { void shell.openPath(logDir()) })
  ipcMain.on('sapient:retry', () => engine.start())
  ipcMain.on('sapient:open-releases', () => { void shell.openExternal(RELEASES_URL) })
  registerUpdater(() => mainWindow, logDir())
}

if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', () => showWindow())

  app.whenReady().then(() => {
    Menu.setApplicationMenu(null)
    session.defaultSession.setPermissionRequestHandler((_wc, _permission, callback) => callback(false))
    serveApp()
    registerIpc()
    const origins = devRendererUrl ? [new URL(devRendererUrl).origin] : [APP_ORIGIN]
    applyPendingRestore(app.getPath('userData'), path.join(logDir(), 'engine.log'))
    engine = new EngineSupervisor(engineCommand(), app.getPath('userData'),
      path.join(logDir(), 'engine.log'), origins)
    engine.on('state', onEngineState)
    engine.start()
    // The TWS connector starts once the engine has prepared the database.
    engine.once('state', function startConnector(state: EngineState) {
      if (state.kind !== 'ready') { engine.once('state', startConnector); return }
      connector = new EngineSupervisor(engineCommand(), app.getPath('userData'),
        path.join(logDir(), 'tws-connector-process.log'), [], 'worker')
      watchConnector(connector, 'paper')
      connector.start()
      liveConnector = new EngineSupervisor(engineCommand(), app.getPath('userData'),
        path.join(logDir(), 'tws-connector-live-process.log'), [], 'worker', ['--profile', 'live'])
      watchConnector(liveConnector, 'live (real-money)')
      liveConnector.start()
    })
    createWindow()
    if (process.platform === 'win32') app.setAppUserModelId('com.sapient.desktop')  // toast notifications
    alerts = new Alerts(
      () => mainWindow,
      () => {
        const state = engine.current
        return state.kind === 'ready' ? { apiBase: state.info.apiBase, token: state.info.token } : null
      },
      showWindow,
      path.join(app.getPath('userData'), 'desktop-settings.json'),
      iconPath(),
      () => haltOffline(engineCommand(), app.getPath('userData')),
    )
    alerts.start()
  })

  app.on('before-quit', (event) => {
    if (quitting) return
    quitting = true
    alerts?.stop()
    event.preventDefault()
    void Promise.allSettled([engine.stop(), connector?.stop(), liveConnector?.stop()]).finally(() => app.exit(0))
  })
  app.on('window-all-closed', () => app.quit())
}
