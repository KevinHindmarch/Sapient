import { useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { AlertTriangle, CheckCircle2, ShieldCheck } from 'lucide-react'
import { apiErrorMessage, PaperLimits, PaperStatus, tradingApiFor } from '../lib/api'

interface Props {
  status: PaperStatus | null
  account: string | null       // account TWS is logged in to
  paperConfirmed: boolean      // the user ticked "this is my paper account" in Step 2
  onChange: () => void
}

const DEFAULT_LIMITS = { max_order_value: 2000, max_orders_per_day: 10, max_value_per_day: 10000, max_price_gap_pct: 3 }
// The server's own defaults come in the binding; these only cover a missing value.

function LimitField({ label, help, value, onChange, step = 1 }: {
  label: string; help: string; value: number; onChange: (v: number) => void; step?: number
}) {
  return (
    <label className="block text-sm">
      <span className="theme-text font-medium">{label}</span>
      <input type="number" className="input mt-1 w-full" min={0} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))} />
      <span className="text-xs theme-text-secondary">{help}</span>
    </label>
  )
}

// Step 4 on the Interactive Brokers page: authorise, limit and switch paper trading on or off.
export default function PaperTradingCard({ status, account, paperConfirmed, onChange }: Props) {
  const binding = status?.binding
  const live = status?.environment === 'live'
  const api = tradingApiFor(live ? 'live' : 'paper')
  const word = live ? 'real-money' : 'paper'
  const authorised = !!(binding?.account_id && binding.authorised_at)
  const [limits, setLimits] = useState(() => ({
    max_order_value: Number(binding?.max_order_value ?? DEFAULT_LIMITS.max_order_value),
    max_orders_per_day: Number(binding?.max_orders_per_day ?? DEFAULT_LIMITS.max_orders_per_day),
    max_value_per_day: Number(binding?.max_value_per_day ?? DEFAULT_LIMITS.max_value_per_day),
    max_price_gap_pct: Number(binding?.max_price_gap_pct ?? DEFAULT_LIMITS.max_price_gap_pct),
    autonomous_allowed: !!binding?.autonomous_allowed,
  }))
  const [ticked, setTicked] = useState(false)
  const [busy, setBusy] = useState(false)
  if (!status) return null

  const targetAccount = binding?.account_id ?? account ?? ''
  const statement = status.authorisation_text.replace('{account}', targetAccount)
  const set = <K extends keyof typeof limits>(key: K, value: (typeof limits)[K]) => setLimits((l) => ({ ...l, [key]: value }))

  const run = async (action: () => Promise<unknown>, done: string) => {
    setBusy(true)
    try {
      await action()
      toast.success(done)
      onChange()
    } catch (err) {
      toast.error(apiErrorMessage(err, 'That did not work'))
    } finally {
      setBusy(false)
    }
  }

  const limitFields = (
    <div className="grid sm:grid-cols-2 gap-4">
      <LimitField label="Most per order (A$)" help={`Sapient refuses bigger ${word} orders.`} step={100}
        value={limits.max_order_value} onChange={(v) => set('max_order_value', v)} />
      <LimitField label="Orders per day" help={`Counts every ${word} order Sapient queues.`} value={limits.max_orders_per_day}
        onChange={(v) => set('max_orders_per_day', Math.round(v))} />
      <LimitField label="Most per day (A$)" help={`Total value of the day's ${word} orders.`} step={500}
        value={limits.max_value_per_day} onChange={(v) => set('max_value_per_day', v)} />
      <LimitField label="Price check (%)" help={`Max gap between TWS's ${live ? 'real-time' : 'delayed'} price and Yahoo's before Sapient refuses.`}
        step={0.5} value={limits.max_price_gap_pct} onChange={(v) => set('max_price_gap_pct', v)} />
      <label className="sm:col-span-2 flex items-start gap-2 text-sm theme-text">
        <input type="checkbox" className="mt-1" checked={limits.autonomous_allowed}
          onChange={(e) => set('autonomous_allowed', e.target.checked)} />
        <span>Allow <strong>fully automatic</strong> {word} orders for portfolios set to Autonomous, without asking me
          (off: every AI proposal waits for your approval).</span>
      </label>
    </div>
  )

  return (
    <div className="card space-y-4" data-testid={live ? 'live-trading' : 'paper-trading'}>
      <div className="flex flex-wrap items-center gap-2">
        <h2 className={`text-lg font-semibold ${live ? 'text-red-600' : 'theme-text'}`}>
          Step 4 — {live ? 'Real-money trading' : 'Paper trading'}</h2>
        {authorised && binding?.enabled && (
          <span className="px-2 py-0.5 rounded-md text-xs font-bold border bg-emerald-500/15 text-emerald-600 border-emerald-500/30">ON · {binding.account_id}</span>
        )}
        {authorised && !binding?.enabled && (
          <span className="px-2 py-0.5 rounded-md text-xs font-bold border bg-slate-500/10 theme-text-secondary theme-border">
            {binding?.halted ? 'STOPPED (Emergency stop)' : 'OFF'}
          </span>
        )}
        {!live && <span className="px-2 py-0.5 rounded-md text-xs font-bold border bg-slate-500/10 theme-text-secondary theme-border">PRACTICE MONEY</span>}
        {live && <span className="px-2 py-0.5 rounded-md text-xs font-bold border bg-red-500/15 text-red-600 border-red-500/40">REAL MONEY</span>}
      </div>
      {live ? (
        <p className="text-sm theme-text-secondary">
          Sapient places <strong>real orders with your money</strong> in your IBKR <strong>live</strong> account: ASX shares
          only, whole shares, limit orders during ASX hours, never borrowing or short selling. Each order is priced from
          TWS's <strong>real-time</strong> price at that moment (buy at the current ask, sell at the current bid), and is
          refused if real-time prices aren't available or differ from Yahoo by more than your price check.
        </p>
      ) : (
        <p className="text-sm theme-text-secondary">
          Sapient sends <strong>practice orders</strong> to your IBKR <strong>paper</strong> account: ASX shares only, whole
          shares, limit orders during ASX hours. Prices come from TWS's free <strong>delayed</strong> data (15–20 minutes old),
          so Sapient never adds a premium: a buy is priced at the delayed price or lower, a sell at it or higher. Some orders
          may simply not fill.
        </p>
      )}

      {!authorised ? (
        <>
          <ol className="list-decimal pl-5 text-sm theme-text space-y-1">
            <li>Log in to TWS with {live ? <>your <strong>live</strong> account (port 7496)</> : <strong>Paper Trading</strong>}.</li>
            <li>In TWS: <strong>File → Global Configuration → API → Settings</strong>, <strong>untick “Read-Only API”</strong>,
              click Apply and OK. Do this only on the {live ? 'live' : 'paper'} login{live ? ' you want Sapient to trade' : ''}.</li>
            <li>Choose your limits and tick the statement below.</li>
          </ol>
          {(!paperConfirmed || !account) && (
            <p className="text-sm text-amber-600 flex items-center gap-2"><AlertTriangle className="w-4 h-4" />
              First connect TWS (Step 2) and confirm the account is your {live ? 'live (real-money)' : 'paper'} account.</p>
          )}
          {limitFields}
          <label className="flex items-start gap-2 text-sm theme-text rounded-xl border theme-border p-3">
            <input type="checkbox" className="mt-1" checked={ticked} onChange={(e) => setTicked(e.target.checked)}
              disabled={!paperConfirmed || !account} data-testid="paper-authorise-tick" />
            <span>{statement}</span>
          </label>
          <button className="btn-primary inline-flex items-center gap-2" disabled={!ticked || busy || !account}
            onClick={() => run(() => api.authorise(targetAccount, statement, limits as PaperLimits),
              live ? 'Real-money trading is on' : 'Paper trading is on')}>
            <ShieldCheck className="w-4 h-4" /> Authorise {live ? 'real-money' : 'paper'} trading
          </button>
        </>
      ) : (
        <>
          {status.ready ? (
            <p className="text-sm text-emerald-600 flex items-center gap-2"><CheckCircle2 className="w-4 h-4" />
              Ready: approvals for {live ? 'real-money' : 'paper'} portfolios and tickets on the{' '}
              <Link to="/paper-orders" className="underline">Orders</Link> page go to {binding?.account_id}.</p>
          ) : (
            <div className="text-sm space-y-1">
              <p className="theme-text font-medium">New {word} orders are paused because:</p>
              <ul className="list-disc pl-5 theme-text-secondary">
                {status.blockers.map((b) => <li key={b.code}>{b.message}</li>)}
              </ul>
            </div>
          )}
          {limitFields}
          <div className="flex flex-wrap gap-2">
            <button className="btn-secondary" disabled={busy}
              onClick={() => run(() => api.updateLimits(limits as PaperLimits), 'Limits saved')}>Save limits</button>
            {binding?.enabled ? (
              <button className="btn-secondary" disabled={busy}
                onClick={() => run(() => api.disable(), `${live ? 'Real-money' : 'Paper'} trading switched off`)}>Switch {word} trading off</button>
            ) : (
              <>
                <label className="flex items-center gap-2 text-sm theme-text">
                  <input type="checkbox" checked={ticked} onChange={(e) => setTicked(e.target.checked)} />
                  {statement}
                </label>
                <button className="btn-primary" disabled={!ticked || busy}
                  onClick={() => run(() => api.authorise(targetAccount, statement, limits as PaperLimits),
                    `${live ? 'Real-money' : 'Paper'} trading is on again`)}>Switch {word} trading on</button>
              </>
            )}
            <Link to="/paper-orders" className="btn-secondary">Orders</Link>
          </div>
        </>
      )}
    </div>
  )
}
