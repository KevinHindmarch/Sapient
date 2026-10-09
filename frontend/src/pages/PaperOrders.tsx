import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { ClipboardList, Loader2, Send } from 'lucide-react'
import { apiErrorMessage, liveApi, PaperOrder, PaperOrderState, PaperStatus, paperApi, tradingApiFor, TradingEnv, UNKNOWN_CHECK_TEXT } from '../lib/api'

const STATE: Record<PaperOrderState, { text: string; tone: string }> = {
  QUEUED: { text: 'Waiting to send', tone: 'text-sky-500' },
  SUBMITTING: { text: 'Sending…', tone: 'text-sky-500' },
  SUBMITTED: { text: 'Working at TWS', tone: 'text-sky-500' },
  PARTIALLY_FILLED: { text: 'Partly filled', tone: 'text-emerald-500' },
  FILLED: { text: 'Filled', tone: 'text-emerald-500' },
  CANCEL_REQUESTED: { text: 'Cancelling…', tone: 'text-amber-500' },
  CANCELLED: { text: 'Cancelled', tone: 'theme-text-secondary' },
  REJECTED: { text: 'Refused by TWS', tone: 'text-red-500' },
  EXPIRED: { text: 'Not sent (expired)', tone: 'theme-text-secondary' },
  BLOCKED: { text: 'Not sent', tone: 'theme-text-secondary' },
  UNKNOWN: { text: 'Outcome unknown', tone: 'text-red-500' },
}
const ORIGIN = { manual: 'You', ai_approval: 'AI (you approved)', ai_autonomous: 'AI (automatic)', entry: 'Portfolio purchase' }

const aud = (value: string | number | null | undefined) =>
  value === null || value === undefined ? '—' : `A$${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 3 })}`

export default function PaperOrders() {
  const [orders, setOrders] = useState<PaperOrder[]>([])
  const [statuses, setStatuses] = useState<Record<TradingEnv, PaperStatus | null>>({ paper: null, live: null })
  const [env, setEnv] = useState<TradingEnv>('paper')
  const [ticket, setTicket] = useState({ symbol: '', side: 'BUY' as 'BUY' | 'SELL', quantity: '' })
  const [sending, setSending] = useState(false)
  const [checking, setChecking] = useState<PaperOrder | null>(null)

  const load = useCallback(async () => {
    try {
      const [o, p, l] = await Promise.all([paperApi.orders(), paperApi.status(), liveApi.status()])
      setOrders(o.data)
      setStatuses({ paper: p.data, live: l.data })
    } catch { /* engine restarting */ }
  }, [])

  useEffect(() => {
    void load()
    const timer = window.setInterval(() => { void load() }, 3000)
    return () => window.clearInterval(timer)
  }, [load])

  const place = async () => {
    let symbol = ticket.symbol.trim().toUpperCase()
    if (symbol && !symbol.endsWith('.AX')) symbol += '.AX'
    const quantity = Number(ticket.quantity)
    if (!symbol || !Number.isInteger(quantity) || quantity < 1) return toast.error('Enter an ASX code and a whole number of shares')
    setSending(true)
    try {
      await tradingApiFor(env).place({ symbol, side: ticket.side, quantity, idempotency_key: `manual:${crypto.randomUUID()}` })
      toast.success(`${ticket.side} ${quantity} ${symbol} queued for your ${env === 'live' ? 'LIVE (real-money)' : 'paper'} account`)
      setTicket({ symbol: '', side: ticket.side, quantity: '' })
      await load()
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Paper order refused'))
    } finally {
      setSending(false)
    }
  }

  const act = async (fn: () => Promise<unknown>, done: string) => {
    try {
      await fn()
      toast.success(done)
      await load()
    } catch (err) {
      toast.error(apiErrorMessage(err, 'That did not work'))
    }
  }

  const status = statuses[env]
  const binding = status?.binding
  const authorised = !!binding?.authorised_at
  const liveAuthorised = !!statuses.live?.binding.authorised_at
  const live = env === 'live'
  return (
    <div className="max-w-5xl mx-auto space-y-6 animate-fade-in" data-testid="paper-orders">
      <div className="page-header">
        <h1 className="page-title flex items-center gap-2"><ClipboardList className="w-7 h-7 text-sky-500" /> Orders</h1>
        <p className="page-subtitle">Orders Sapient sends to Interactive Brokers: <strong>paper</strong> (practice money) and,
          if you authorised it, <strong className="text-red-600">live (real money)</strong>.</p>
      </div>

      {liveAuthorised && (
        <div className="flex gap-2" role="tablist">
          <button className={env === 'paper' ? 'btn-primary' : 'btn-secondary'} onClick={() => setEnv('paper')}>Paper ticket</button>
          <button className={env === 'live' ? 'btn-primary !bg-red-600 !from-red-600 !to-red-700' : 'btn-secondary'}
            onClick={() => setEnv('live')} data-testid="ticket-live">Real-money ticket</button>
        </div>
      )}
      {!authorised ? (
        <div className="card text-sm theme-text-secondary">
          {live ? 'Real-money' : 'Paper'} trading is not authorised yet. Set it up in{' '}
          <Link to="/brokerage" className="text-sky-500 underline">Brokerage → Step 4</Link>.
        </div>
      ) : (
        <div className={`card space-y-3 ${live ? 'border-red-500/40' : ''}`}>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold theme-text">New {live ? 'REAL-MONEY' : 'paper'} order</h2>
            <span className={`px-2 py-0.5 rounded-md text-xs font-bold border ${live
              ? 'bg-red-500/15 text-red-600 border-red-500/40' : 'bg-emerald-500/15 text-emerald-600 border-emerald-500/30'}`}>
              {live ? 'TWS LIVE · REAL MONEY' : 'TWS PAPER'} · {binding?.account_id}
            </span>
          </div>
          {status && !status.ready && (
            <ul className="list-disc pl-5 text-sm text-amber-600">
              {status.blockers.map((b) => <li key={b.code}>{b.message}</li>)}
            </ul>
          )}
          <div className="flex flex-wrap gap-2 items-end">
            <label className="text-sm">
              <span className="theme-text-secondary text-xs block">ASX code</span>
              <input className="input w-32" placeholder="BHP" value={ticket.symbol} aria-label="ASX code"
                onChange={(e) => setTicket({ ...ticket, symbol: e.target.value })} />
            </label>
            <label className="text-sm">
              <span className="theme-text-secondary text-xs block">Buy or sell</span>
              <select className="input" value={ticket.side} aria-label="Buy or sell"
                onChange={(e) => setTicket({ ...ticket, side: e.target.value as 'BUY' | 'SELL' })}>
                <option value="BUY">Buy</option>
                <option value="SELL">Sell</option>
              </select>
            </label>
            <label className="text-sm">
              <span className="theme-text-secondary text-xs block">Shares</span>
              <input className="input w-28" type="number" min={1} step={1} value={ticket.quantity} aria-label="Shares"
                onChange={(e) => setTicket({ ...ticket, quantity: e.target.value })} />
            </label>
            <button className="btn-primary inline-flex items-center gap-2" onClick={place}
              disabled={sending || !status?.ready}>
              {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />} {live ? 'Send REAL-MONEY order' : 'Send paper order'}
            </button>
          </div>
          <p className="text-xs theme-text-secondary">
            {live
              ? <>Sapient prices it from TWS's <strong>real-time</strong> price when it sends (buy at the ask, sell at the bid) and refuses if</>
              : <>Sapient sets the limit price from TWS's delayed price when it sends (a buy at that price or lower, a sell at it
            or higher) and refuses if</>}{' '}it is more than {Number(binding?.max_price_gap_pct ?? 3)}% away from Yahoo's price.
            Limits: up to {aud(binding?.max_order_value)} per order, {binding?.max_orders_per_day} orders and{' '}
            {aud(binding?.max_value_per_day)} per day.
          </p>
        </div>
      )}

      <div className="card">
        <h2 className="text-lg font-semibold theme-text mb-3">Orders</h2>
        {orders.length === 0 ? (
          <p className="text-sm theme-text-secondary">No orders yet.</p>
        ) : (
          <div className="space-y-3">
            {orders.map((o) => {
              const st = STATE[o.state]
              return (
                <div key={o.id} className={`rounded-xl border p-3 text-sm ${o.environment === 'live' ? 'border-red-500/40' : 'theme-border'}`}
                  data-testid="paper-order">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold border ${o.environment === 'live'
                      ? 'bg-red-500/15 text-red-600 border-red-500/40' : 'bg-slate-500/10 theme-text-secondary theme-border'}`}>
                      {o.environment === 'live' ? 'REAL MONEY' : 'PAPER'}
                    </span>
                    <span className={`font-bold ${o.side === 'BUY' ? 'text-emerald-500' : 'text-red-500'}`}>{o.side}</span>
                    <span className="font-semibold theme-text">{Number(o.quantity)} {o.symbol}</span>
                    <span className="theme-text-secondary">limit {aud(o.limit_price)}{o.quote?.delayed ? ' (delayed price)' : ''}</span>
                    <span className={`font-medium ${st.tone}`}>{st.text}</span>
                    {Number(o.filled_quantity) > 0 && (
                      <span className="theme-text">{Number(o.filled_quantity)} filled at {aud(o.avg_fill_price)}</span>
                    )}
                    <span className="ml-auto text-xs theme-text-muted">
                      {ORIGIN[o.origin]}{o.portfolio_name ? ` · ${o.portfolio_name}` : ''} · {new Date(o.created_at).toLocaleString()}
                    </span>
                  </div>
                  {o.detail && <p className="text-xs theme-text-secondary mt-1">{o.detail}</p>}
                  {o.fills.length > 0 && (
                    <p className="text-xs theme-text-secondary mt-1">
                      Fills: {o.fills.map((f) => `${Number(f.shares)} @ ${aud(f.price)}${f.commission ? ` (fee ${f.commission} ${f.commission_currency ?? ''})` : ''}`).join(', ')}
                    </p>
                  )}
                  <div className="flex gap-2 mt-2">
                    {['QUEUED', 'SUBMITTED', 'PARTIALLY_FILLED'].includes(o.state) && (
                      <button className="btn-secondary text-xs" onClick={() => act(() => tradingApiFor(o.environment).cancel(o.id), 'Cancel requested')}>
                        Cancel order
                      </button>
                    )}
                    {o.state === 'UNKNOWN' && (
                      <button className="btn-secondary text-xs" onClick={() => setChecking(o)}>I've checked TWS…</button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {checking && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="card max-w-md w-full space-y-3">
            <h3 className="text-lg font-semibold theme-text">Order outcome unknown</h3>
            <p className="text-sm theme-text-secondary">
              Sapient sent {checking.side} {Number(checking.quantity)} {checking.symbol} but TWS didn't confirm it. Sapient will
              never send it again by itself. Open TWS → <strong>Orders</strong> and <strong>Trades</strong> and look for it
              (order id {checking.api_order_id}). If it's there, leave this; Sapient picks it up on the next sync.
            </p>
            <p className="text-sm theme-text">Only if it is definitely not there and did not fill:</p>
            <div className="flex gap-2 justify-end">
              <button className="btn-secondary" onClick={() => setChecking(null)}>Back</button>
              <button className="btn-primary" onClick={() => {
                const id = checking.id
                setChecking(null)
                void act(() => tradingApiFor(checking.environment).resolveUnknown(id), 'Marked as not placed')
              }}>{UNKNOWN_CHECK_TEXT}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
