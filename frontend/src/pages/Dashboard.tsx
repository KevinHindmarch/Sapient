import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Briefcase, ClipboardList, Inbox, AlertTriangle, ShoppingCart } from 'lucide-react'
import {
  aiApi, liveApi, money, paperApi, portfolioApi,
  type AllHistories, type PaperOrder, type PortfolioSummary, type ValuePoint,
} from '../lib/api'
import type { Portfolio } from '../types'
import { useProfile } from '../lib/profile'
import ValueChart, { PERIODS, Sparkline, type Period, type Series } from '../components/ValueChart'

const WORKING = new Set(['QUEUED', 'SUBMITTING', 'SUBMITTED', 'PARTIALLY_FILLED', 'CANCEL_REQUESTED', 'UNKNOWN'])
type View = 'AUD' | 'USD' | 'BOTH'

const currencyOf = (p: Portfolio) => ((p.market || 'ASX') === 'US' ? 'USD' : 'AUD') as 'AUD' | 'USD'
const signed = (v: number, currency: 'AUD' | 'USD') => `${v >= 0 ? '▲ +' : '▼ -'}${money(Math.abs(v), currency, 0)}`

function Shimmer({ className = '' }: { className?: string }) {
  return <div className={`rounded-lg loading-shimmer ${className}`} />
}

export default function Dashboard() {
  const { profile } = useProfile()
  const [portfolios, setPortfolios] = useState<Portfolio[]>([])
  const [summaries, setSummaries] = useState<PortfolioSummary[] | null>(null)
  const [histories, setHistories] = useState<AllHistories | null>(null)
  const [pending, setPending] = useState(0)
  const [orders, setOrders] = useState<PaperOrder[]>([])
  const [loading, setLoading] = useState(true)
  const [view, setView] = useState<View>('AUD')
  const [period, setPeriod] = useState<Period>('3M')

  useEffect(() => {
    portfolioApi.list().then((r) => setPortfolios(r.data)).catch(() => undefined).finally(() => setLoading(false))
    portfolioApi.summaries().then((r) => setSummaries(r.data)).catch(() => setSummaries([]))
    portfolioApi.histories().then((r) => setHistories(r.data)).catch(() => undefined)
    aiApi.listSignals('pending').then((r) => setPending(Array.isArray(r.data) ? r.data.length : 0)).catch(() => undefined)
    Promise.all([paperApi.orders().catch(() => null), liveApi.orders().catch(() => null)])
      .then((all) => setOrders(all.flatMap((r) => r?.data ?? []).filter((o) => WORKING.has(o.state))))
  }, [])

  const totals = useMemo(() => (['AUD', 'USD'] as const).map((currency) => {
    const mine = (summaries ?? []).filter((s) => s.currency === currency)
    const value = mine.reduce((a, s) => a + s.total_value, 0)
    const putIn = mine.reduce((a, s) => a + s.money_put_in, 0)
    const gain = mine.reduce((a, s) => a + s.total_return, 0)
    const cash = mine.reduce((a, s) => a + s.cash, 0)
    return { currency, count: mine.length, value, putIn, gain, cash, pct: putIn > 0 ? (gain / putIn) * 100 : 0 }
  }), [summaries])
  const [aud, usd] = totals
  const rate = histories?.aud_per_usd ?? null
  const hasUsd = usd.count > 0
  const everything = aud.value + (rate ? usd.value * rate : 0)

  useEffect(() => {
    if (!hasUsd && view !== 'AUD') setView('AUD')
  }, [hasUsd, view])

  const series: Series[] = useMemo(() => {
    const c = histories?.combined ?? {}
    const a = c.AUD ?? []
    const u = c.USD ?? []
    if (view === 'AUD') return [{ key: 'aud', label: 'A$ portfolios', color: 'var(--aud)', points: a }]
    if (view === 'USD') return [{ key: 'usd', label: 'US$ portfolios', color: 'var(--usd)', points: u }]
    // Both: US$ converted at today's rate, added to A$ day by day (each carried forward).
    const days = [...new Set([...a, ...u].map((p) => p.date))].sort()
    const la = new Map(a.map((p) => [p.date, p.value]))
    const lu = new Map(u.map((p) => [p.date, p.value]))
    let lastA = 0
    let lastU = 0
    const both: ValuePoint[] = days.map((d) => {
      lastA = la.get(d) ?? lastA
      lastU = lu.get(d) ?? lastU
      return { date: d, value: Math.round(lastA + lastU * (rate ?? 0)) }
    })
    return [{ key: 'both', label: 'Everything in A$', color: 'var(--ink)', points: both }]
  }, [histories, view, rate])

  const sparkFor = (id: number) => histories?.portfolios.find((h) => h.portfolio_id === id)?.points.slice(-60) ?? []
  const summaryFor = (id: number) => summaries?.find((s) => s.portfolio_id === id)
  const toBuy = (summaries ?? []).flatMap((s) => s.holdings
    .filter((h) => (h.planned_quantity ?? 0) > h.quantity)
    .map((h) => ({ portfolio: s, symbol: h.symbol })))
  const missing = (summaries ?? []).filter((s) => s.prices_missing.length)
  const today = new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })

  return (
    <div className="max-w-7xl mx-auto space-y-6 animate-fade-in">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm theme-text-muted">{today}</p>
          <h1 className="page-title">Welcome back, {profile?.display_name || 'Investor'}</h1>
        </div>
        <div className="flex gap-2">
          <Link to="/auto-builder" className="btn-primary text-sm !py-2">Build a portfolio</Link>
        </div>
      </div>

      {/* Money cards: A$ and US$ are kept apart; the third card converts US$ at today's rate. */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[aud, usd].map((t) => (
          <div key={t.currency} className="stat-card space-y-3" data-testid={`totals-${t.currency.toLowerCase()}`}>
            <div className="flex items-center justify-between">
              <span className={`chip ${t.currency === 'AUD' ? 'chip-aud' : 'chip-usd'}`}>
                {t.currency === 'AUD' ? 'Australian shares · A$' : 'US shares · US$'}
              </span>
              <span className="text-xs theme-text-muted">{t.count} portfolio{t.count === 1 ? '' : 's'}</span>
            </div>
            {summaries === null ? <Shimmer className="h-9 w-40" /> : (
              <p className="stat-value !text-3xl">{money(t.value, t.currency, 0)}</p>
            )}
            {summaries !== null && t.count > 0 && (
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                <span className={`num font-semibold ${t.gain >= 0 ? 'text-pos' : 'text-neg'}`}>
                  {signed(t.gain, t.currency)} ({t.pct >= 0 ? '+' : ''}{t.pct.toFixed(1)}%)
                </span>
                <span className="theme-text-muted">put in <span className="num">{money(t.putIn, t.currency, 0)}</span></span>
                <span className="theme-text-muted">cash <span className="num">{money(t.cash, t.currency, 0)}</span></span>
              </div>
            )}
            {summaries !== null && t.count === 0 && <p className="text-sm theme-text-muted">No {t.currency === 'AUD' ? 'Australian' : 'US'} portfolios yet.</p>}
          </div>
        ))}
        <div className="stat-card space-y-3">
          <div className="flex items-center justify-between">
            <span className="chip">Everything in A$</span>
            {rate && <span className="num text-xs theme-text-muted">US$1 = A${rate.toFixed(4)}</span>}
          </div>
          {summaries === null ? <Shimmer className="h-9 w-40" /> : (
            <p className="stat-value !text-3xl">{money(everything, 'AUD', 0)}</p>
          )}
          {hasUsd && rate && everything > 0 && (
            <div className="space-y-1.5">
              <div className="flex h-2 rounded-full overflow-hidden" style={{ background: 'var(--chip)' }}>
                <span style={{ width: `${(aud.value / everything) * 100}%`, background: 'var(--aud)' }} />
                <span style={{ width: `${((usd.value * rate) / everything) * 100}%`, background: 'var(--usd)' }} />
              </div>
              <div className="flex justify-between text-xs theme-text-muted">
                <span className="text-aud">A$ {Math.round((aud.value / everything) * 100)}%</span>
                <span className="text-usd">US$ {Math.round(((usd.value * rate) / everything) * 100)}%</span>
              </div>
            </div>
          )}
          {hasUsd && !rate && <p className="text-xs theme-text-muted">Exchange rate unavailable right now: US$ not included.</p>}
          {!hasUsd && <p className="text-xs theme-text-muted">Only A$ portfolios so far.</p>}
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="card xl:col-span-2 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold theme-text">Value over time</h2>
              <p className="text-xs theme-text-muted">Rebuilt from your trades and daily closing prices{view === 'BOTH' ? '; US$ at today\'s rate' : ''}.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {hasUsd && (
                <div className="seg" role="group" aria-label="Currency">
                  {(['AUD', 'USD', 'BOTH'] as View[]).map((v) => (
                    <button key={v} type="button" aria-pressed={view === v} onClick={() => setView(v)}>
                      {v === 'AUD' ? 'A$' : v === 'USD' ? 'US$' : 'Both'}
                    </button>
                  ))}
                </div>
              )}
              <div className="seg" role="group" aria-label="Period">
                {PERIODS.map((p) => (
                  <button key={p} type="button" aria-pressed={period === p} onClick={() => setPeriod(p)}>{p}</button>
                ))}
              </div>
            </div>
          </div>
          {histories === null ? <Shimmer className="h-[260px] w-full" /> : (
            <ValueChart series={series} period={period} prefix={view === 'USD' ? 'US$' : 'A$'} />
          )}
        </div>

        <div className="card space-y-3" data-testid="attention">
          <h2 className="text-base font-semibold theme-text">Needs your attention</h2>
          {pending > 0 && (
            <AttentionRow to="/ai-inbox" icon={Inbox} title={`${pending} proposal${pending === 1 ? '' : 's'} to answer`}
              detail="Approve or reject in the AI Inbox." />
          )}
          {orders.length > 0 && (
            <AttentionRow to="/paper-orders" icon={ClipboardList} title={`${orders.length} order${orders.length === 1 ? '' : 's'} working at IBKR`}
              detail={orders.slice(0, 3).map((o) => `${o.side === 'BUY' ? 'Buy' : 'Sell'} ${o.quantity} ${o.symbol.replace('.AX', '')}`).join(' · ')} />
          )}
          {toBuy.length > 0 && (
            <AttentionRow to={`/portfolios/${toBuy[0].portfolio.portfolio_id}`} icon={ShoppingCart}
              title={`${toBuy.length} planned stock${toBuy.length === 1 ? '' : 's'} not bought yet`}
              detail={`${toBuy.slice(0, 4).map((x) => x.symbol.replace('.AX', '')).join(', ')}. Use "Buy … & manage" again on the portfolio.`} />
          )}
          {missing.length > 0 && (
            <AttentionRow to={`/portfolios/${missing[0].portfolio_id}`} icon={AlertTriangle}
              title="Some prices are missing" detail={missing.flatMap((s) => s.prices_missing).slice(0, 4).join(', ')} />
          )}
          {!pending && !orders.length && !toBuy.length && !missing.length && (
            <p className="text-sm theme-text-muted py-4">Nothing right now. Sapient checks each portfolio twice a trading day.</p>
          )}
        </div>
      </div>

      <div className="card space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold theme-text">Your portfolios</h2>
          <Link to="/portfolios" className="text-sm font-medium theme-text-secondary hover:underline">View all</Link>
        </div>
        {loading ? <Shimmer className="h-32 w-full" /> : portfolios.length === 0 ? (
          <div className="text-center py-10 space-y-2">
            <Briefcase className="w-8 h-8 mx-auto theme-text-muted" />
            <p className="theme-text-secondary">No portfolios yet</p>
            <p className="text-sm theme-text-muted">Build one with the Auto, Manual or CAPM builder.</p>
          </div>
        ) : (
          <div className="divide-y theme-border">
            {portfolios.map((p) => {
              const s = summaryFor(p.id)
              const currency = currencyOf(p)
              const up = (s?.total_return ?? 0) >= 0
              return (
                <Link key={p.id} to={`/portfolios/${p.id}`} className="flex items-center gap-4 py-3 group" style={{ borderColor: 'var(--border-color)' }}>
                  <div className="flex-1 min-w-0 space-y-1">
                    <p className="font-medium theme-text truncate group-hover:underline">{p.name}</p>
                    <div className="flex flex-wrap gap-1.5">
                      <span className={`chip ${currency === 'AUD' ? 'chip-aud' : 'chip-usd'}`}>{currency === 'AUD' ? 'ASX · A$' : 'US · US$'}</span>
                      <span className="chip">{p.trading_environment === 'live' ? 'TWS live' : p.trading_environment === 'paper' ? 'TWS paper' : 'Research only'}</span>
                      {p.strategy === 'factor' && <span className="chip">Model B</span>}
                      {p.ai_mode && p.ai_mode !== 'off' && <span className="chip">{p.ai_mode === 'autonomous' ? 'Fully automatic' : 'Asks first'}</span>}
                    </div>
                  </div>
                  <div className="hidden sm:block">
                    <Sparkline points={sparkFor(p.id)} color={currency === 'AUD' ? 'var(--aud)' : 'var(--usd)'} />
                  </div>
                  <div className="text-right shrink-0 w-36">
                    <p className="num font-semibold theme-text">{money(s ? s.total_value : Number(p.initial_investment), currency, 0)}</p>
                    {s ? (
                      <p className={`num text-xs ${up ? 'text-pos' : 'text-neg'}`}>
                        {up ? '▲ +' : '▼ '}{s.total_return_pct.toFixed(2)}%
                      </p>
                    ) : summaries === null ? <Shimmer className="h-3 w-16 ml-auto mt-1" /> : null}
                  </div>
                  <ArrowRight className="w-4 h-4 theme-text-muted shrink-0" />
                </Link>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

function AttentionRow({ to, icon: Icon, title, detail }: { to: string; icon: typeof Inbox; title: string; detail: string }) {
  return (
    <Link to={to} className="flex gap-3 rounded-xl p-3 surface-2 hover:opacity-90">
      <Icon className="w-4 h-4 mt-0.5 theme-text-secondary shrink-0" />
      <div className="min-w-0">
        <p className="text-sm font-medium theme-text">{title}</p>
        <p className="text-xs theme-text-muted truncate">{detail}</p>
      </div>
    </Link>
  )
}
