// Tray icon, desktop notifications for new trade proposals, the Emergency stop,
// and the optional "keep running in the tray" behaviour. Everything here talks to
// the local engine with the same per-launch token the UI uses.

import { app, BrowserWindow, dialog, ipcMain, Menu, nativeImage, Notification, Tray } from 'electron'
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

interface DesktopSettings { closeToTray: boolean }

// Paper order changes worth a notification (automatic trades must never be silent).
const ORDER_NOTICES: Record<string, (o: PaperOrder) => string> = {
  FILLED: (o) => `Paper ${o.side.toLowerCase()} filled: ${Number(o.filled_quantity)} ${o.symbol} at A$${o.avg_fill_price ?? '?'}`,
  PARTIALLY_FILLED: (o) => `Paper ${o.side.toLowerCase()} partly filled: ${Number(o.filled_quantity)} of ${Number(o.quantity)} ${o.symbol}`,
  REJECTED: (o) => `TWS refused the paper ${o.side.toLowerCase()} of ${o.symbol}`,
  UNKNOWN: (o) => `Check TWS: outcome of the paper ${o.side.toLowerCase()} of ${o.symbol} is unknown`,
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

  constructor(
    private readonly window: () => BrowserWindow | null,
    private readonly endpoint: () => EngineEndpoint | null,
    private readonly showWindow: () => void,
    private readonly settingsFile: string,
    private readonly iconFile: string,
  ) {
    this.settings = this.loadSettings()
  }

  get closeToTray(): boolean { return this.settings.closeToTray }

  start(): void {
    this.createTray()
    this.registerIpc()
    void this.poll()
    this.timer = setInterval(() => { void this.poll() }, POLL_MS)
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer)
    this.tray?.destroy()
    this.tray = null
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
      return { closeToTray: raw.closeToTray === true }
    } catch {
      return { closeToTray: false }
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
      { label: 'Paper orders', click: () => this.openPage('#/paper-orders') },
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
    if (!this.seeded) {  // what was already waiting at launch is shown in the app, not as a burst of toasts
      this.seeded = true
      return
    }
    if (fresh.length && Notification.isSupported()) this.notify(fresh)
    await this.pollOrders()
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
      if (!this.ordersSeeded || before === order.state) continue
      if (before === undefined && order.origin === 'ai_autonomous') {
        notices.push({ title: `Sapient is placing a paper ${order.side.toLowerCase()}: ${Number(order.quantity)} ${order.symbol}`,
          body: 'Automatic (Autonomous mode). Paper account only. Press Emergency stop in the tray to stop.' })
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
      ? `${first.rule_summary}${answerBy}. Simulation only — nothing is sent to your broker.`
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
        detail: 'This switches AI Trading and paper trading off, expires all waiting proposals, blocks queued orders '
          + 'and asks TWS to cancel Sapient\'s own working paper orders (never your own TWS orders). '
          + 'You can switch things back on later (after a 24-hour cooldown).',
        buttons: ['Stop now', 'Cancel'],
        defaultId: 0,
        cancelId: 1,
      })
      if (choice.response !== 0) return { ok: false, message: 'Cancelled' }
    }
    try {
      const result = await this.call<{ cancelled_signals: number; paper_orders_cancel_requested?: number }>(
        '/ai/kill-switch', 'POST')
      const paperOrders = result.paper_orders_cancel_requested ?? 0
      const message = `Stopped. AI Trading and paper trading are off and ${result.cancelled_signals} waiting proposal(s) were expired. `
        + (paperOrders
          ? `Cancel requested for ${paperOrders} working paper order(s); TWS confirms each one on the Paper orders page. `
            + 'An order can still fill before its cancel arrives. Check TWS if in doubt.'
          : 'Sapient had no working orders at Interactive Brokers. Orders you placed yourself in TWS are not touched.')
      await this.poll()
      if (confirm) await dialog.showMessageBox({ type: 'info', title: 'Emergency stop', message: 'AI trading stopped', detail: message })
      return { ok: true, message }
    } catch (error) {
      const message = `The stop could not be recorded (${(error as Error).message}). Close Sapient to stop it completely.`
      if (confirm) await dialog.showMessageBox({ type: 'error', title: 'Emergency stop', message: 'Stop failed', detail: message })
      return { ok: false, message }
    }
  }
}
