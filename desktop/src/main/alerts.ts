// Tray icon, desktop notifications for new trade proposals, the Emergency stop,
// and the optional "keep running in the tray" behaviour. Everything here talks to
// the local engine with the same per-launch token the UI uses.

import { app, BrowserWindow, dialog, ipcMain, Menu, nativeImage, Notification, powerSaveBlocker, Tray } from 'electron'
import fs from 'node:fs'
import path from 'node:path'

export interface EngineEndpoint { apiBase: string; token: string }

interface Proposal {
  id: number
  symbol: string
  action: string
  quantity: number
  rule_summary: string
  portfolio_name?: string | null
  expires_at?: string | null
}

interface PaperOrder {
  id: string
  environment?: 'paper' | 'live'
  origin: string
  symbol: string
  side: string
  quantity: string
  state: string
  filled_quantity: string
  avg_fill_price: string | null
  limit_price: string | null
  detail: string | null
}

interface DesktopSettings {
  closeToTray: boolean   // closing the window keeps Sapient running in the tray (default on)
  openAtLogin: boolean   // start with Windows, hidden in the tray (default off)
  keepAwake: boolean     // stop the PC sleeping while a market Sapient trades is open (default on)
}
const DEFAULTS: DesktopSettings = { closeToTray: true, openAtLogin: false, keepAwake: true }

interface SchedulerStatus { markets?: { code: string; open_now: boolean }[] }

// Paper order changes worth a notification (automatic trades must never be silent).
const kind = (o: PaperOrder) => (o.environment === 'live' ? 'REAL-MONEY' : 'Paper')
const ORDER_NOTICES: Record<string, (o: PaperOrder) => string> = {
  FILLED: (o) => `${kind(o)} ${o.side.toLowerCase()} filled: ${Number(o.filled_quantity)} ${o.symbol} at A$${o.avg_fill_price ?? '?'}`,
  PARTIALLY_FILLED: (o) => `${kind(o)} ${o.side.toLowerCase()} partly filled: ${Number(o.filled_quantity)} of ${Number(o.quantity)} ${o.symbol}`,
  REJECTED: (o) => `TWS refused the ${kind(o).toLowerCase()} ${o.side.toLowerCase()} of ${o.symbol}`,
  UNKNOWN: (o) => `Check TWS: outcome of the ${kind(o).toLowerCase()} ${o.side.toLowerCase()} of ${o.symbol} is unknown`,
}

const POLL_MS = 30_000

export class Alerts {
  private tray: Tray | null = null
  private seen = new Set<number>()
  private seeded = false
  private orderStates = new Map<string, string>()
  private ordersSeeded = false
  private pending = 0
  private timer: NodeJS.Timeout | null = null
  private settings: DesktopSettings
  private hintShown = false
  private awakeBlocker: number | null = null

  constructor(
    private readonly window: () => BrowserWindow | null,
    private readonly endpoint: () => EngineEndpoint | null,
    private readonly showWindow: () => void,
    private readonly settingsFile: string,
    private readonly iconFile: string,
    /** Emergency stop straight in the database when the engine is not answering. */
    private readonly haltOffline: () => Promise<number>,
  ) {
    this.settings = this.loadSettings()
  }

  get closeToTray(): boolean { return this.settings.closeToTray }

  start(): void {
    this.createTray()
    this.registerIpc()
    this.applyLoginItem()
    void this.poll()
    this.timer = setInterval(() => { void this.poll() }, POLL_MS)
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer)
    this.setAwake(false)
    this.tray?.destroy()
    this.tray = null
  }

  /** A problem the user must know about even with the window closed (e.g. a TWS connector stopped). */
  warn(title: string, body: string): void {
    if (!Notification.isSupported()) return
    const note = new Notification({ title, body })
    note.on('click', () => this.showWindow())
    note.show()
  }

  /** Called when the window is hidden instead of closed. */
  hiddenToTray(): void {
    if (this.hintShown || !Notification.isSupported()) return
    this.hintShown = true
    new Notification({ title: 'Sapient is still running',
      body: 'Automatic checks continue. Use the tray icon to open Sapient or quit.' }).show()
  }

  // -- settings -----------------------------------------------------------
  private loadSettings(): DesktopSettings {
    try {
      const raw = JSON.parse(fs.readFileSync(this.settingsFile, 'utf8')) as Partial<DesktopSettings>
      return {
        closeToTray: typeof raw.closeToTray === 'boolean' ? raw.closeToTray : DEFAULTS.closeToTray,
        openAtLogin: raw.openAtLogin === true,
        keepAwake: typeof raw.keepAwake === 'boolean' ? raw.keepAwake : DEFAULTS.keepAwake,
      }
    } catch {
      return { ...DEFAULTS }
    }
  }

  /** Start with Windows (hidden in the tray) when the user asked for it. */
  private applyLoginItem(): void {
    if (process.platform !== 'win32' || !app.isPackaged) return
    app.setLoginItemSettings({ openAtLogin: this.settings.openAtLogin, args: ['--hidden'] })
  }

  private setAwake(on: boolean): void {
    if (on && this.awakeBlocker === null) {
      this.awakeBlocker = powerSaveBlocker.start('prevent-app-suspension')
    } else if (!on && this.awakeBlocker !== null) {
      powerSaveBlocker.stop(this.awakeBlocker)
      this.awakeBlocker = null
    }
  }

  /** Keep the PC awake while the ASX or US market is open, so automatic checks and orders aren't missed. */
  private async refreshAwake(): Promise<void> {
    if (!this.settings.keepAwake) { this.setAwake(false); return }
    try {
      const status = await this.call<SchedulerStatus>('/ai/scheduler')
      this.setAwake((status.markets ?? []).some((m) => m.open_now))
    } catch {
      // engine restarting: keep the current state
    }
  }

  private saveSettings(): void {
    fs.mkdirSync(path.dirname(this.settingsFile), { recursive: true })
    fs.writeFileSync(this.settingsFile, JSON.stringify(this.settings, null, 2))
  }

  private registerIpc(): void {
    ipcMain.handle('sapient:desktop-settings', () => ({ ...this.settings }))
    ipcMain.handle('sapient:set-close-to-tray', (_event, value: unknown) => {
      this.settings.closeToTray = value === true
      this.saveSettings()
      return { ...this.settings }
    })
    ipcMain.handle('sapient:set-desktop-setting', (_event, key: unknown, value: unknown) => {
      if ((key === 'closeToTray' || key === 'openAtLogin' || key === 'keepAwake') && typeof value === 'boolean') {
        this.settings[key] = value
        this.saveSettings()
        if (key === 'openAtLogin') this.applyLoginItem()
        if (key === 'keepAwake') void this.refreshAwake()
      }
      return { ...this.settings }
    })
    ipcMain.handle('sapient:emergency-stop', () => this.emergencyStop(false))
  }

  // -- tray ---------------------------------------------------------------
  private createTray(): void {
    try {
      const icon = nativeImage.createFromPath(this.iconFile).resize({ width: 16, height: 16 })
      this.tray = new Tray(icon)
      this.tray.on('click', () => this.showWindow())
      this.refreshTray()
    } catch {
      this.tray = null  // some Linux desktops have no tray; notifications still work
    }
  }

  private refreshTray(): void {
    if (!this.tray) return
    const waiting = this.pending === 1 ? '1 proposal waiting' : `${this.pending} proposals waiting`
    this.tray.setToolTip(this.pending ? `Sapient — ${waiting}` : 'Sapient')
    this.tray.setContextMenu(Menu.buildFromTemplate([
      { label: 'Open Sapient', click: () => this.showWindow() },
      { label: this.pending ? `AI Inbox (${this.pending})` : 'AI Inbox', click: () => this.openInbox() },
      { label: 'Orders', click: () => this.openPage('#/paper-orders') },
      { type: 'separator' },
      { label: 'Emergency stop…', click: () => { void this.emergencyStop(true) } },
      { type: 'separator' },
      { label: 'Quit Sapient', click: () => app.quit() },
    ]))
  }

  private openInbox(): void {
    this.openPage('#/ai-inbox')
  }

  private openPage(hash: '#/ai-inbox' | '#/paper-orders'): void {
    this.showWindow()
    void this.window()?.webContents.executeJavaScript(`location.hash = '${hash}'`).catch(() => undefined)
  }

  // -- engine calls -------------------------------------------------------
  private async call<T>(route: string, method = 'GET'): Promise<T> {
    const endpoint = this.endpoint()
    if (!endpoint) throw new Error('Sapient is still starting')
    const response = await fetch(endpoint.apiBase + route, {
      method, headers: { Authorization: `Bearer ${endpoint.token}` },
    })
    if (!response.ok) throw new Error(`${route} answered ${response.status}`)
    return await response.json() as T
  }

  private async poll(): Promise<void> {
    let proposals: Proposal[]
    try {
      proposals = await this.call<Proposal[]>('/ai/signals?status=pending')
    } catch {
      return  // engine starting or restarting; try again next time
    }
    this.pending = proposals.length
    this.refreshTray()
    const fresh = proposals.filter((p) => !this.seen.has(p.id))
    proposals.forEach((p) => this.seen.add(p.id))
    // What was already waiting at launch is shown in the app, not as a burst of toasts.
    if (this.seeded && fresh.length && Notification.isSupported()) this.notify(fresh)
    this.seeded = true
    await this.pollOrders()
    await this.refreshAwake()
  }

  private async pollOrders(): Promise<void> {
    let orders: PaperOrder[]
    try {
      orders = await this.call<PaperOrder[]>('/paper/orders')
    } catch {
      return
    }
    const notices: { title: string; body: string }[] = []
    for (const order of orders) {
      const before = this.orderStates.get(order.id)
      this.orderStates.set(order.id, order.state)
      if (!this.ordersSeeded) {
        // At launch only orders that need the user now are announced (e.g. crash recovery marked them unknown).
        if (order.state === 'UNKNOWN') notices.push({ title: ORDER_NOTICES.UNKNOWN(order), body: order.detail ?? '' })
        continue
      }
      if (before === order.state) continue
      if (before === undefined && order.origin === 'ai_autonomous') {
        notices.push({ title: `Sapient is placing a ${kind(order).toLowerCase()} ${order.side.toLowerCase()}: ${Number(order.quantity)} ${order.symbol}`,
          body: `Automatic (fully automatic mode, ${order.environment === 'live' ? 'REAL MONEY' : 'paper account'}). `
            + 'Press Emergency stop in the tray to stop.' })
      }
      const describe = ORDER_NOTICES[order.state]
      if (describe) notices.push({ title: describe(order), body: order.detail ?? 'See Paper orders in Sapient.' })
    }
    this.ordersSeeded = true
    if (!Notification.isSupported()) return
    for (const notice of notices.slice(0, 3)) {
      const note = new Notification(notice)
      note.on('click', () => this.openPage('#/paper-orders'))
      note.show()
    }
    if (notices.length > 3) {
      const note = new Notification({ title: `Sapient: ${notices.length - 3} more paper order updates`, body: 'Open Paper orders to see them.' })
      note.on('click', () => this.openPage('#/paper-orders'))
      note.show()
    }
  }

  private notify(fresh: Proposal[]): void {
    const first = fresh[0]
    const answerBy = first.expires_at
      ? ` · answer by ${new Date(first.expires_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
      : ''
    const title = fresh.length === 1
      ? `Sapient proposes: ${first.action} ${first.quantity} ${first.symbol}`
      : `Sapient: ${fresh.length} new trade proposals`
    const body = fresh.length === 1
      ? `${first.rule_summary}${answerBy}. Open the AI Inbox to approve or reject it; nothing is sent until you approve.`
      : `${fresh.map((p) => `${p.action} ${p.symbol}`).join(', ')}. Open the AI Inbox to review.`
    const note = new Notification({ title, body })
    note.on('click', () => this.openInbox())
    note.show()
  }

  async emergencyStop(confirm: boolean): Promise<{ ok: boolean; message: string }> {
    if (confirm) {
      const choice = await dialog.showMessageBox({
        type: 'warning',
        title: 'Emergency stop',
        message: 'Stop all AI trading now?',
        detail: 'This switches AI Trading, paper and real-money trading off, expires all waiting proposals, blocks queued '
          + 'orders and asks TWS to cancel Sapient\'s own working orders (never your own TWS orders). '
          + 'You can switch things back on later (after a 24-hour cooldown).',
        buttons: ['Stop now', 'Cancel'],
        defaultId: 0,
        cancelId: 1,
      })
      if (choice.response !== 0) return { ok: false, message: 'Cancelled' }
    }
    try {
      let result: { cancelled_signals?: number; paper_orders_cancel_requested?: number }
      try {
        result = await this.call('/ai/kill-switch', 'POST')
      } catch {
        // The engine isn't answering: record the stop directly in Sapient's database instead.
        result = { paper_orders_cancel_requested: await this.haltOffline() }
      }
      const paperOrders = result.paper_orders_cancel_requested ?? 0
      const expired = result.cancelled_signals === undefined ? 'all' : String(result.cancelled_signals)
      const message = `Stopped. AI Trading, paper and real-money trading are off and ${expired} waiting proposal(s) were expired. `
        + (paperOrders
          ? `Cancel requested for ${paperOrders} working order(s); TWS confirms each one on the Orders page. `
            + 'An order can still fill before its cancel arrives. Check TWS if in doubt.'
          : 'Sapient had no working orders at Interactive Brokers. Orders you placed yourself in TWS are not touched.')
      await this.poll().catch(() => undefined)
      if (confirm) await dialog.showMessageBox({ type: 'info', title: 'Emergency stop', message: 'AI trading stopped', detail: message })
      return { ok: true, message }
    } catch (error) {
      const message = `The stop could not be recorded (${(error as Error).message}). Quit Sapient (tray → Quit) `
        + 'to stop it completely, and check TWS for working orders.'

      if (confirm) await dialog.showMessageBox({ type: 'error', title: 'Emergency stop', message: 'Stop failed', detail: message })
      return { ok: false, message }
    }
  }
}
