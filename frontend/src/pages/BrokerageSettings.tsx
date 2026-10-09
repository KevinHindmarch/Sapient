import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Circle, Loader2, PlugZap, RefreshCw, ShieldCheck, XCircle } from 'lucide-react'
import { toast } from 'sonner'
import { apiErrorMessage, PaperStatus, paperApi, TwsAccount, TwsCommand, TwsSettings, TwsStatus, TwsTestStep, twsApi } from '../lib/api'
import TwsSetupGuide from '../components/TwsSetupGuide'
import PaperTradingCard from '../components/PaperTradingCard'
import { TWS_STATE_LABELS } from '../components/TwsStatusPill'

type SdkInfo = { found: boolean; folder: string | null; version: string | null }

function StepIcon({ status }: { status: TwsTestStep['status'] | 'running' }) {
  if (status === 'ok') return <CheckCircle2 className="w-5 h-5 text-emerald-500" />
  if (status === 'warn') return <AlertTriangle className="w-5 h-5 text-amber-500" />
  if (status === 'fail') return <XCircle className="w-5 h-5 text-red-500" />
  if (status === 'running') return <Loader2 className="w-5 h-5 animate-spin text-sky-500" />
  return <Circle className="w-5 h-5 text-slate-400" />
}

function money(value: unknown, currency?: unknown) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '—'
  return `${currency ? `${currency} ` : ''}${number.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
}

export default function BrokerageSettings() {
  const [settings, setSettings] = useState<TwsSettings | null>(null)
  const [form, setForm] = useState({ port: '7497', client_id: '71', expected_account: '', sdk_folder: '', paper_confirmed: false })
  const [sdk, setSdk] = useState<SdkInfo | null>(null)
  const [status, setStatus] = useState<TwsStatus | null>(null)
  const [account, setAccount] = useState<TwsAccount | null>(null)
  const [paper, setPaper] = useState<PaperStatus | null>(null)
  const loadPaper = useCallback(() => { paperApi.status().then((res) => setPaper(res.data)).catch(() => undefined) }, [])
  const [saving, setSaving] = useState(false)
  const [test, setTest] = useState<TwsCommand | null>(null)
  const [testing, setTesting] = useState(false)
  const [guideOpen, setGuideOpen] = useState(true)
  const pollTest = useRef<number | null>(null)

  const loadSettings = useCallback(async () => {
    const [settingsRes, sdkRes] = await Promise.all([twsApi.settings(), twsApi.sdk()])
    const s = settingsRes.data
    setSettings(s)
    setSdk(sdkRes.data)
    setForm({ port: String(s.port), client_id: String(s.client_id), expected_account: s.expected_account ?? '',
      sdk_folder: s.sdk_folder ?? '', paper_confirmed: s.paper_confirmed })
    setGuideOpen(!s.enabled)
  }, [])

  useEffect(() => { loadSettings().catch(() => toast.error('Could not load the TWS settings')) }, [loadSettings])

  // Live status (and account data once connected).
  useEffect(() => {
    let alive = true
    const refresh = async () => {
      try {
        const res = await twsApi.status()
        if (!alive) return
        setStatus(res.data)
        paperApi.status().then((p) => { if (alive) setPaper(p.data) }).catch(() => undefined)
        if (res.data.state === 'READY' || res.data.state === 'IBKR_DISCONNECTED') {
          const acc = await twsApi.account()
          if (alive) setAccount(acc.data)
        }
      } catch { /* engine restarting; try again next tick */ }
    }
    refresh()
    const timer = window.setInterval(refresh, 3000)
    return () => { alive = false; window.clearInterval(timer) }
  }, [])

  useEffect(() => () => { if (pollTest.current) window.clearInterval(pollTest.current) }, [])

  const save = async (enable: boolean) => {
    const port = Number(form.port), clientId = Number(form.client_id)
    if (!Number.isInteger(port) || port < 1 || port > 65535) return toast.error('The port must be a number like 7497')
    if (!Number.isInteger(clientId) || clientId < 1) return toast.error('The client ID must be a whole number above 0')
    if (!/^[A-Za-z0-9]{0,32}$/.test(form.expected_account.trim())) return toast.error('The account number should only contain letters and numbers')
    setSaving(true)
    try {
      const res = await twsApi.saveSettings({
        enabled: enable, port, client_id: clientId, expected_account: form.expected_account.trim(),
        paper_confirmed: form.paper_confirmed, sdk_folder: form.sdk_folder.trim(),
      })
      setSettings(res.data)
      setForm((current) => ({ ...current, paper_confirmed: res.data.paper_confirmed }))
      setSdk((await twsApi.sdk()).data)
      toast.success(enable ? 'Saved. Sapient will connect to TWS (read-only).' : 'Saved. Sapient will not connect to TWS.')
    } catch (error) {
      toast.error(apiErrorMessage(error, 'Could not save the settings'))
    } finally {
      setSaving(false)
    }
  }

  const runTest = async () => {
    setTesting(true)
    setTest(null)
    try {
      const { data } = await twsApi.startTest()
      if (pollTest.current) window.clearInterval(pollTest.current)
      pollTest.current = window.setInterval(async () => {
        try {
          const res = await twsApi.testResult(data.id)
          setTest(res.data)
          if (res.data.status === 'done' || res.data.status === 'failed') {
            window.clearInterval(pollTest.current!)
            pollTest.current = null
            setTesting(false)
          }
        } catch {
          window.clearInterval(pollTest.current!)
          pollTest.current = null
          setTesting(false)
        }
      }, 1000)
    } catch (error) {
      toast.error(apiErrorMessage(error, 'Could not start the test'))
      setTesting(false)
    }
  }

  const state = status?.state ?? 'NOT_CONFIGURED'
  const label = TWS_STATE_LABELS[state] ?? { text: state, tone: 'amber' }
  const isPaper = !!status?.account?.startsWith('DU') && !!settings?.paper_confirmed
  const paperOn = !!(paper?.binding.enabled && paper.binding.account_id && paper.binding.account_id === status?.account)
  const summary = (account?.snapshots.summary?.data ?? {}) as Record<string, { value: string; currency: string }>
  const positions = (account?.snapshots.positions?.data ?? []) as Array<Record<string, string>>
  const openOrders = (account?.snapshots.open_orders?.data ?? []) as Array<Record<string, string>>
  const executions = (account?.snapshots.executions?.data ?? []) as Array<Record<string, string>>
  const toneClass = { green: 'bg-emerald-500/15 text-emerald-600 border-emerald-500/30',
    amber: 'bg-amber-500/15 text-amber-600 border-amber-500/30', red: 'bg-red-500/15 text-red-600 border-red-500/30' }[label.tone]

  return (
    <div className="max-w-4xl mx-auto space-y-6 animate-fade-in">
      <div className="page-header">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-8 h-8 text-sky-400" />
          <h1 className="page-title">Interactive Brokers</h1>
        </div>
        <p className="page-subtitle">Connect Sapient to Trader Workstation (TWS) on this PC — read-only, or paper orders once you authorise them</p>
      </div>

      {/* Status */}
      <div className="card" data-testid="tws-status">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-semibold theme-text">Connection</h2>
          <span className={`px-2 py-0.5 rounded-md text-xs font-bold border ${toneClass}`}>{label.text}</span>
          {state === 'READY' && (
            <span className="px-2 py-0.5 rounded-md text-xs font-bold border bg-sky-500/15 text-sky-600 border-sky-500/30">
              {paperOn ? 'TWS PAPER' : isPaper ? 'TWS PAPER · READ-ONLY' : 'TWS · READ-ONLY'}
            </span>
          )}
          {paperOn ? (
            <span className="px-2 py-0.5 rounded-md text-xs font-bold border bg-emerald-500/15 text-emerald-600 border-emerald-500/30">
              ORDERS: TWS PAPER · LIVE OFF
            </span>
          ) : (
            <span className="px-2 py-0.5 rounded-md text-xs font-bold border bg-slate-500/10 theme-text-secondary theme-border">
              ORDERS: SIMULATION ONLY
            </span>
          )}
        </div>
        <p className="text-sm theme-text-secondary mt-2">{status?.detail ?? 'Checking…'}</p>
        {status && !status.worker_running && (
          <p className="text-sm text-amber-600 mt-1">The TWS connector isn't running. Restarting Sapient usually fixes this.</p>
        )}
        <div className="grid sm:grid-cols-3 gap-3 mt-4 text-sm">
          <div><p className="theme-text-secondary text-xs">Account</p><p className="theme-text font-mono">{status?.account ?? '—'}</p></div>
          <div><p className="theme-text-secondary text-xs">Last update from TWS</p>
            <p className="theme-text">{status?.last_sync_at ? new Date(status.last_sync_at).toLocaleTimeString() : '—'}</p></div>
          <div><p className="theme-text-secondary text-xs">IBKR API software</p>
            <p className="theme-text">{sdk?.found ? `Installed (${sdk.version ?? 'version unknown'})` : 'Not found'}</p></div>
        </div>
        {settings?.enabled && (
          <button className="btn-secondary mt-4 inline-flex items-center gap-2" onClick={() => twsApi.reconnect().then(() => toast.success('Reconnecting…'))}>
            <RefreshCw className="w-4 h-4" /> Reconnect
          </button>
        )}
      </div>

      {/* Setup guide */}
      <div className="card">
        <button className="w-full flex items-center justify-between text-left" onClick={() => setGuideOpen(!guideOpen)}>
          <h2 className="text-lg font-semibold theme-text">Step 1 — Set up TWS (about 10–15 minutes)</h2>
          {guideOpen ? <ChevronDown className="w-5 h-5 theme-text-secondary" /> : <ChevronRight className="w-5 h-5 theme-text-secondary" />}
        </button>
        {guideOpen && <div className="mt-5"><TwsSetupGuide /></div>}
      </div>

      {/* Settings */}
      <div className="card" data-testid="tws-settings">
        <h2 className="text-lg font-semibold theme-text mb-1">Step 2 — Connection settings</h2>
        <p className="text-sm theme-text-secondary mb-4">These must match TWS (File → Global Configuration → API → Settings). Sapient only connects to TWS on this PC.</p>
        <div className="grid sm:grid-cols-3 gap-4">
          <label className="text-sm theme-text-secondary">Socket port
            <input className="input w-full mt-1" inputMode="numeric" value={form.port} onChange={(e) => setForm({ ...form, port: e.target.value })} />
            <span className="text-xs">Paper is normally 7497</span>
          </label>
          <label className="text-sm theme-text-secondary">Client ID
            <input className="input w-full mt-1" inputMode="numeric" value={form.client_id} onChange={(e) => setForm({ ...form, client_id: e.target.value })} />
            <span className="text-xs">Any number above 0 not used by another program</span>
          </label>
          <label className="text-sm theme-text-secondary">Paper account number
            <input className="input w-full mt-1 font-mono" placeholder="DU1234567" value={form.expected_account}
              onChange={(e) => setForm({ ...form, expected_account: e.target.value.toUpperCase(), paper_confirmed: false })} />
            <span className="text-xs">Shown at the top of TWS</span>
          </label>
        </div>
        <label className="flex items-start gap-2 mt-4 text-sm theme-text">
          <input type="checkbox" className="mt-1" checked={form.paper_confirmed}
            onChange={(e) => setForm({ ...form, paper_confirmed: e.target.checked })} />
          <span>I checked that TWS shows the red <strong>Paper Trading</strong> banner for this account.</span>
        </label>
        <details className="mt-3 text-sm theme-text-secondary">
          <summary className="cursor-pointer">Advanced: IBKR API software folder</summary>
          <input className="input w-full mt-2 font-mono" placeholder="C:\TWS API" value={form.sdk_folder}
            onChange={(e) => setForm({ ...form, sdk_folder: e.target.value })} />
          <p className="text-xs mt-1">Leave empty to look in C:\TWS API automatically. {sdk?.folder ? `Found: ${sdk.folder}` : ''}</p>
        </details>
        <div className="flex flex-wrap gap-2 mt-5">
          <button className="btn-primary" disabled={saving} onClick={() => save(true)}>
            {settings?.enabled ? 'Save' : 'Save and connect'}
          </button>
          {settings?.enabled && <button className="btn-secondary" disabled={saving} onClick={() => save(false)}>Disconnect</button>}
        </div>
      </div>

      {/* Test connection */}
      <div className="card" data-testid="tws-test">
        <h2 className="text-lg font-semibold theme-text mb-1">Step 3 — Test the connection</h2>
        <p className="text-sm theme-text-secondary mb-4">Checks everything step by step. Nothing is ever ordered or changed in your account.</p>
        <button className="btn-primary inline-flex items-center gap-2" disabled={testing || !settings} onClick={runTest}>
          {testing ? <Loader2 className="w-4 h-4 animate-spin" /> : <PlugZap className="w-4 h-4" />} Test connection
        </button>
        {(testing || test) && (
          <div className="mt-5 space-y-3">
            {test?.result?.steps ? test.result.steps.map((step) => (
              <div key={step.key} className="flex gap-3">
                <StepIcon status={step.status} />
                <div className="flex-1 text-sm">
                  <p className="theme-text font-medium">{step.title}</p>
                  {step.detail && <p className="theme-text-secondary">{step.detail}</p>}
                  {step.fix && <p className="mt-1 text-amber-700 dark:text-amber-400">How to fix: {step.fix}</p>}
                </div>
              </div>
            )) : (
              <div className="flex gap-3 text-sm theme-text-secondary"><StepIcon status="running" />
                {test?.status === 'failed' ? test.result?.message : 'Testing… this takes up to a minute.'}</div>
            )}
            {test?.result?.steps && (
              <p className={`text-sm font-semibold ${test.result.ok ? 'text-emerald-600' : 'text-red-600'}`}>
                {test.result.ok ? 'Everything works. Sapient can read your TWS account.' : 'Fix the step marked with a red cross, then test again.'}
              </p>
            )}
          </div>
        )}
      </div>

      {paper && (
        <PaperTradingCard key={paper.binding.authorised_at ?? 'new'} status={paper} account={status?.account ?? null}
          paperConfirmed={!!settings?.paper_confirmed} onChange={loadPaper} />
      )}

      {/* Read-only account */}
      {account && (state === 'READY' || state === 'IBKR_DISCONNECTED') && (
        <div className="card" data-testid="tws-account">
          <h2 className="text-lg font-semibold theme-text mb-1">Your account (read-only)</h2>
          <p className="text-xs theme-text-secondary mb-4">From TWS{account.snapshots.summary ? `, updated ${new Date(account.snapshots.summary.taken_at).toLocaleTimeString()}` : ''}. Refreshes every minute.</p>
          <div className="grid sm:grid-cols-4 gap-3 mb-6">
            {[['NetLiquidation', 'Net value'], ['TotalCashValue', 'Cash'], ['BuyingPower', 'Buying power'], ['GrossPositionValue', 'Invested']].map(([tag, title]) => (
              <div key={tag} className="p-3 rounded-xl border theme-border">
                <p className="text-xs theme-text-secondary">{title}</p>
                <p className="theme-text font-semibold">{money(summary[tag]?.value, summary[tag]?.currency)}</p>
              </div>
            ))}
          </div>
          <h3 className="font-semibold theme-text mb-2">Positions ({positions.length})</h3>
          {positions.length === 0 ? <p className="text-sm theme-text-secondary mb-4">No positions.</p> : (
            <table className="w-full text-sm mb-6">
              <thead><tr className="text-left theme-text-secondary"><th className="py-1">Stock</th><th>Exchange</th><th className="text-right">Shares</th><th className="text-right">Average cost</th></tr></thead>
              <tbody>{positions.map((p, i) => (
                <tr key={i} className="border-t theme-border theme-text"><td className="py-1.5 font-mono">{p.symbol}</td>
                  <td>{p.primaryExchange || p.exchange} {p.currency}</td><td className="text-right">{p.position}</td>
                  <td className="text-right">{money(p.avg_cost)}</td></tr>))}</tbody>
            </table>
          )}
          <h3 className="font-semibold theme-text mb-2">Open orders ({openOrders.length})</h3>
          {openOrders.length === 0 ? <p className="text-sm theme-text-secondary mb-4">None.</p> : (
            <ul className="text-sm theme-text mb-4 space-y-1">{openOrders.map((o, i) => (
              <li key={i}>{o.action} {o.quantity} {o.symbol} {o.order_type} {o.limit_price ? `@ ${o.limit_price}` : ''} — {o.status}</li>))}</ul>
          )}
          <h3 className="font-semibold theme-text mb-2">Recent fills ({executions.length})</h3>
          {executions.length === 0 ? <p className="text-sm theme-text-secondary">None today.</p> : (
            <ul className="text-sm theme-text space-y-1">{executions.map((e, i) => (
              <li key={i}>{e.time} — {e.side} {e.shares} {e.symbol} @ {e.price}</li>))}</ul>
          )}
        </div>
      )}
    </div>
  )
}
