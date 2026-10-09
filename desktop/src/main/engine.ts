// Starts and supervises the Sapient engine (FastAPI + analytics, Python).
//
// Protocol (see backend/desktop_main.py): we write a fresh random token as the
// first stdin line; the engine prints {"event":"ready","port":N} when listening
// on 127.0.0.1, or {"event":"error",...}. Closing stdin makes it exit, so the
// engine can never outlive the app, even if Electron crashes.

import { ChildProcessWithoutNullStreams, spawn } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { EventEmitter } from 'node:events'
import fs from 'node:fs'
import path from 'node:path'
import readline from 'node:readline'

export interface EngineCommand {
  command: string
  args: string[]
  cwd?: string
}

export interface EngineInfo {
  port: number
  token: string
  apiBase: string
}

export type EngineState =
  | { kind: 'starting'; attempt: number }
  | { kind: 'ready'; info: EngineInfo }
  | { kind: 'failed'; message: string }
  | { kind: 'stopped' }

const READY_TIMEOUT_MS = 90_000 // first launch unpacks scipy/pandas and migrates the database
const MAX_RESTARTS = 3
const RESTART_WINDOW_MS = 60_000

export class EngineSupervisor extends EventEmitter {
  private child: ChildProcessWithoutNullStreams | null = null
  private state: EngineState = { kind: 'stopped' }
  private restarts: number[] = []
  private stopping = false

  constructor(
    private readonly engine: EngineCommand,
    private readonly dataDir: string,
    private readonly logFile: string,
    private readonly allowedOrigins: string[],
    /** 'api' serves HTTP and reports its port; 'worker' is the TWS connector (no port). */
    private readonly role: 'api' | 'worker' = 'api',
    /** Extra command-line arguments, e.g. ['--profile', 'live'] for the real-money connector. */
    private readonly extraArgs: string[] = [],
  ) {
    super()
  }

  get current(): EngineState {
    return this.state
  }

  start(): void {
    this.stopping = false
    this.restarts = []
    this.launch(1)
  }

  private setState(state: EngineState): void {
    this.state = state
    this.emit('state', state)
  }

  private log(line: string): void {
    fs.mkdirSync(path.dirname(this.logFile), { recursive: true })
    fs.appendFileSync(this.logFile, `[${new Date().toISOString()}] ${line}\n`)
  }

  private launch(attempt: number): void {
    const token = randomBytes(32).toString('base64url')
    const args = [...this.engine.args, '--data-dir', this.dataDir]
    if (this.role === 'worker') args.push('--worker')
    args.push(...this.extraArgs)
    for (const origin of this.allowedOrigins) args.push('--allowed-origin', origin)
    this.log(`starting engine (attempt ${attempt}): ${this.engine.command}`)
    this.setState({ kind: 'starting', attempt })

    const child = spawn(this.engine.command, args, {
      cwd: this.engine.cwd,
      windowsHide: true,
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONUNBUFFERED: '1', SAPIENT_DATA_DIR: this.dataDir },
    })
    this.child = child
    let settled = false

    const timer = setTimeout(() => {
      if (!settled) {
        settled = true
        this.log('engine did not become ready in time')
        child.kill()
        this.setState({ kind: 'failed', message: 'The Sapient engine took too long to start.' })
      }
    }, READY_TIMEOUT_MS)

    child.stdin.write(token + '\n')
    child.stderr.on('data', (chunk: Buffer) => this.log(chunk.toString().trimEnd()))
    readline.createInterface({ input: child.stdout }).on('line', (line) => {
      let event: { event?: string; port?: number; message?: string; code?: string }
      try {
        event = JSON.parse(line)
      } catch {
        this.log(`engine: ${line}`)
        return
      }
      if (settled) return
      if (event.event === 'ready' && (this.role === 'worker' || typeof event.port === 'number')) {
        settled = true
        clearTimeout(timer)
        const port = event.port ?? 0
        this.log(this.role === 'worker' ? 'TWS connector ready' : `engine ready on 127.0.0.1:${port}`)
        this.setState({ kind: 'ready', info: { port, token, apiBase: `http://127.0.0.1:${port}/api` } })
      } else if (event.event === 'error') {
        settled = true
        clearTimeout(timer)
        this.log(`engine error ${event.code}: ${event.message}`)
        this.setState({ kind: 'failed', message: event.message ?? 'The Sapient engine reported an error.' })
      }
    })

    child.on('error', (error) => {
      this.log(`failed to start engine: ${error.message}`)
      if (!settled) {
        settled = true
        clearTimeout(timer)
        this.setState({ kind: 'failed', message: `Could not start the Sapient engine (${error.message}).` })
      }
    })

    child.on('exit', (code, signal) => {
      clearTimeout(timer)
      this.log(`engine exited (code ${code}, signal ${signal})`)
      if (this.child === child) this.child = null
      if (this.stopping) {
        this.setState({ kind: 'stopped' })
        return
      }
      if (this.state.kind === 'failed') return
      const now = Date.now()
      this.restarts = this.restarts.filter((t) => now - t < RESTART_WINDOW_MS)
      if (this.restarts.length >= MAX_RESTARTS) {
        this.setState({ kind: 'failed', message: 'The Sapient engine stopped unexpectedly several times.' })
        return
      }
      this.restarts.push(now)
      setTimeout(() => this.launch(attempt + 1), 1000 * this.restarts.length)
    })
  }

  /** Close stdin (the engine exits by itself), then force-kill if it lingers. */
  async stop(): Promise<void> {
    this.stopping = true
    const child = this.child
    if (!child) return
    await new Promise<void>((resolve) => {
      const force = setTimeout(() => {
        child.kill()
        resolve()
      }, 5000)
      child.once('exit', () => {
        clearTimeout(force)
        resolve()
      })
      child.stdin.end()
    })
  }
}
