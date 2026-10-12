import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Briefcase } from 'lucide-react'
import {
  aiApi, liveApi, money, paperApi, portfolioApi,
  type AllHistories, type PaperOrder, type PortfolioSummary, type SchedulerStatus, type ValuePoint,
} from '../lib/api'
import type { Portfolio } from '../types'
import { useProfile } from '../lib/profile'
import ValueChart, { PERIODS, Sparkline, type Period, type Series } from '../components/ValueChart'

const WORKING = new Set(['QUEUED', 'SUBMITTING', 'SUBMITTED', 'PARTIALLY_FILLED', 'CANCEL_REQUESTED', 'UNKNOWN'])
type View = 'AUD' | 'USD' | 'BOTH'
type Cur = 'AUD' | 'USD'

const currencyOf = (p: Portfolio) => ((p.market || 'ASX') === 'US' ? 'USD' : 'AUD') as Cur
const colorOf = (c: Cur | 'ALL') => (c === 'AUD' ? 'var(--aud)' : c === 'USD' ? 'var(--usd)' : 'var(--ink)')
const pct = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`

function Shimmer({ className = '' }: { className?: string }) {
  return <div className={`rounded-lg loading-shimmer ${className}`} />
}

/** Change since the previous trading day's close in a series (null if there isn't one). */
function dayChange(points: ValuePoint[]) {
  if (points.length < 2) return null
  const now = points[points.length - 1].value
  const before = points[points.length - 2].value
  return { amount: now - before, pct: before > 0 ? ((now - before) / before) * 100 : 0 }
}

/** The last ~3 months of a series, for sparklines. */
function recent(points: ValuePoint[], days = 92) {
  if (!points.length) return points
  const last = new Date(`${points[points.length - 1].date}T00:00:00`)
  last.setDate(last.getDate() - days)
  const from = `${last.getFullYear()}-${String(last.getMonth() + 1).padStart(2, '0')}-${String(last.getDate()).padStart(2, '0')}`
  return points.filter((p) => p.date >= from)
}

/** Add US$ (converted at today's rate) to A$ day by day; each side is carried forward over the other's holidays. */
function combine(a: ValuePoint[], u: ValuePoint[], rate: number) {
  const days = [...new Set([...a, ...u].map((p) => p.date))].sort()
  const la = new Map(a.map((p) => [p.date, p.value]))
  const lu = new Map(u.map((p) => [p.date, p.value]))
  let lastA = 0
  let lastU = 0
  return days.map((d) => {
    lastA = la.get(d) ?? lastA
    lastU = lu.get(d) ?? lastU
    return { date: d, value: Math.round(lastA + lastU * rate) }
  })
}

function marketPill(m: SchedulerStatus['markets'][number]) {
  const time = (iso: string) => new Date(iso).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
  const name = m.code === 'US' ? 'US market' : 'ASX'
  if (m.open_now && m.today) return { open: true, text: `${name} open · closes ${time(m.today.close)}` }
  if (m.next_open) {
    const when = new Date(m.next_open)
    const sameDay = when.toDateString() === new Date().toDateString()
    return { open: false, text: `${name} opens ${sameDay ? '' : `${when.toLocaleDateString(undefined, { weekday: 'short' })} `}${time(m.next_open)}` }
  }
  return { open: false, text: `${name} closed` }
}

/** One money card: coloured top edge, value, today's change, 3-month trend line, then return and cash. */
function MoneyCard({ code, title, count, value, today, trend, color, footer, extra, testId, loading }: {
  code: string; title: string; count?: string; value: string; today: ReturnType<typeof dayChange>; trend: ValuePoint[]
  color: string; footer: { label: string; value: string; tone?: 'pos' | 'neg' }[]; extra?: React.ReactNode
  testId?: string; loading: boolean
}) {
  const sym = code === 'USD' ? 'US$' : 'A$'
  return (
    <div className="stat-card !p-0 overflow-hidden" data-testid={testId}>
      <div className="h-1" style={{ background: color }} />
      <div className="p-5 space-y-3">
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-2 text-sm font-semibold theme-text">
            <span className={`chip !py-0.5 ${code === 'AUD' ? 'chip-aud' : code === 'USD' ? 'chip-usd' : ''}`}>{code}</span>
            {title}
          </span>
          {count && <span className="num text-xs theme-text-muted">{count}</span>}
        </div>
        <div className="flex items-end justify-between gap-3">
          <div className="min-w-0">
            {loading ? <Shimmer className="h-9 w-40" /> : <p className="stat-value !text-3xl">{value}</p>}
            {today && (
              <p className={`num text-xs mt-1 ${today.amount >= 0 ? 'text-pos' : 'text-neg'}`}>
                {today.amount >= 0 ? '▲ +' : '▼ -'}{sym}{Math.abs(Math.round(today.amount)).toLocaleString()} today ({pct(today.pct)})
              </p>
            )}
          </div>
          <span className="shrink-0" title="Last 3 months"><Sparkline points={trend} color={color} width={110} height={38} /></span>
        </div>
        <div className="grid grid-cols-2 gap-3 pt-3 border-t theme-border text-xs">
          {footer.map((f) => (
            <div key={f.label}>
              <p className="theme-text-muted">{f.label}</p>
              <p className={`num font-semibold ${f.tone === 'pos' ? 'text-pos' : f.tone === 'neg' ? 'text-neg' : 'theme-text'}`}>{f.value}</p>
            </div>
          ))}
        </div>
        {extra}
      </div>
    </div>
  )
}

export default function Dashboard() {
  const { profile } = useProfile()
  const [portfolios, setPortfolios] = useState<Portfolio[]>([])
  const [summaries, setSummaries] = useState<PortfolioSummary[] | null>(null)
  const [histories, setHistories] = useState<AllHistories | null>(null)
  const [pending, setPending] = useState(0)
  const [orders, setOrders] = useState<PaperOrder[]>([])
  const [markets, setMarkets] = useState<SchedulerStatus['markets']>([])
  const [loading, setLoading] = useState(true)
  const [view, setView] = useState<View>('AUD')
  const [period, setPeriod] = useState<Period>('3M')
  const [now] = useState(() => new Date())

  useEffect(() => {
    portfolioApi.list().then((r) => setPortfolios(r.data)).catch(() => undefined).finally(() => setLoading(false))
    portfolioApi.summaries().then((r) => setSummaries(r.data)).catch(() => setSummaries([]))
    portfolioApi.histories().then((r) => setHistories(r.data)).catch(() => undefined)
    aiApi.listSignals('pending').then((r) => setPending(Array.isArray(r.data) ? r.data.length : 0)).catch(() => undefined)
    aiApi.scheduler().then((r) => setMarkets(r.data.markets ?? [])).catch(() => undefined)
    Promise.all([paperApi.orders().catch(() => null), liveApi.orders().catch(() => null)])
      .then((all) => setOrders(all.flatMap((r) => r?.data ?? []).filter((o) => WORKING.has(o.state))))
  }, [])

  const rate = histories?.aud_per_usd ?? null
  const combined = useMemo(() => histories?.combined ?? {}, [histories])
  const totals = useMemo(() => (['AUD', 'USD'] as const).map((currency) => {
    const mine = (summaries ?? []).filter((s) => s.currency === currency)
    const value = mine.reduce((a, s) => a + s.total_value, 0)
    const putIn = mine.reduce((a, s) => a + s.money_put_in, 0)
    const gain = mine.reduce((a, s) => a + s.total_return, 0)
    const cash = mine.reduce((a, s) => a + s.cash, 0)
    return { currency, count: mine.length, value, putIn, gain, cash, pct: putIn > 0 ? (gain / putIn) * 100 : 0 }
  }), [summaries])
  const [aud, usd] = totals
  const hasUsd = usd.count > 0
  const everything = aud.value + (rate ? usd.value * rate : 0)
  const everythingPutIn = aud.putIn + (rate ? usd.putIn * rate : 0)
  const everythingGain = everything - everythingPutIn
  const bothSeries = useMemo(() => combine(combined.AUD ?? [], combined.USD ?? [], rate ?? 0), [combined, rate])

  useEffect(() => {
    if (!hasUsd && view !== 'AUD') setView('AUD')
  }, [hasUsd, view])

  const series: Series[] = useMemo(() => {
    if (view === 'AUD') return [{ key: 'aud', label: 'A$ portfolios', color: 'var(--aud)', points: combined.AUD ?? [] }]
    if (view === 'USD') return [{ key: 'usd', label: 'US$ portfolios', color: 'var(--usd)', points: combined.USD ?? [] }]
    return [{ key: 'both', label: 'Everything in A$', color: 'var(--ink)', points: bothSeries }]
  }, [combined, view, bothSeries])

  const sparkFor = (id: number) => recent(histories?.portfolios.find((h) => h.portfolio_id === id)?.points ?? [])
  const summaryFor = (id: number) => summaries?.find((s) => s.portfolio_id === id)
  const toBuy = (summaries ?? []).flatMap((s) => s.holdings
    .filter((h) => (h.planned_quantity ?? 0) > h.quantity)
    .map((h) => ({ portfolio: s, symbol: h.symbol })))
  const missing = (summaries ?? []).filter((s) => s.prices_missing.length)
  const hour = now.getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'

  const attention: { to: string; title: string; detail: string; action: string }[] = []
  if (pending > 0) attention.push({ to: '/ai-inbox', action: 'Review', title: `${pending} trade proposal${pending === 1 ? '' : 's'} waiting`, detail: 'Approve or reject them in the AI Inbox.' })
  if (orders.length) attention.push({ to: '/paper-orders', action: 'View', title: `${orders.length} order${orders.length === 1 ? '' : 's'} working at IBKR`,
    detail: orders.slice(0, 3).map((o) => `${o.side === 'BUY' ? 'Buy' : 'Sell'} ${Number(o.quantity)} ${o.symbol.replace('.AX', '')}`).join(' · ') })
  if (toBuy.length) attention.push({ to: `/portfolios/${toBuy[0].portfolio.portfolio_id}`, action: 'Open',
    title: `${toBuy.length} planned stock${toBuy.length === 1 ? '' : 's'} not bought yet`,
    detail: `${toBuy.slice(0, 4).map((x) => x.symbol.replace('.AX', '')).join(', ')}. Press "Buy … & manage" again on the portfolio.` })
  if (missing.length) attention.push({ to: `/portfolios/${missing[0].portfolio_id}`, action: 'Open', title: 'Some prices are missing',
    detail: `${missing.flatMap((s) => s.prices_missing).slice(0, 4).join(', ')}: Yahoo didn't answer; valued at cost for now.` })

  return (
    <div className="max-w-7xl mx-auto space-y-5 animate-fade-in">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm theme-text-muted">{now.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}</p>
          <h1 className="page-title">{greeting}{profile?.display_name ? `, ${profile.display_name}` : ''}</h1>
          <p className="sr-only">Welcome back</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {markets.map((m) => {
            const pill = marketPill(m)
            return (
              <span key={m.code} className="chip !py-1.5 !px-3 border theme-border" style={{ background: 'var(--bg-card)' }}>
                <span className="w-2 h-2 rounded-full" style={{ background: pill.open ? 'var(--pos)' : 'var(--text-muted)' }} />
                {pill.text}
              </span>
            )
          })}
          <Link to="/auto-builder" className="btn-primary text-sm !py-2 !px-4">+ Build a portfolio</Link>
        </div>
      </div>

      {/* Money cards: A$ and US$ are kept apart; the third card converts US$ at today's rate. */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[aud, usd].map((t) => (
          <MoneyCard key={t.currency} code={t.currency} testId={`totals-${t.currency.toLowerCase()}`}
            title={t.currency === 'AUD' ? 'Australian shares' : 'US shares'}
            count={`${t.count} portfolio${t.count === 1 ? '' : 's'}`} loading={summaries === null}
            value={money(t.value, t.currency, 0)} today={dayChange(combined[t.currency] ?? [])}
            trend={recent(combined[t.currency] ?? [])} color={colorOf(t.currency)}
            footer={[
              { label: 'Total return', value: `${t.gain >= 0 ? '+' : '-'}${money(Math.abs(t.gain), t.currency, 0)} · ${pct(t.pct)}`,
                tone: t.gain >= 0 ? 'pos' : 'neg' },
              { label: 'Cash ready to invest', value: money(t.cash, t.currency, 0) },
            ]} />
        ))}
        <MoneyCard code="ALL" title="Everything, in A$" count={rate ? `US$1 = A$${rate.toFixed(2)}` : undefined}
          loading={summaries === null} value={money(everything, 'AUD', 0)} today={dayChange(bothSeries)}
          trend={recent(bothSeries)} color={colorOf('ALL')}
          footer={[
            { label: 'Total return', value: `${everythingGain >= 0 ? '+' : '-'}${money(Math.abs(everythingGain), 'AUD', 0)}`
              + (everythingPutIn > 0 ? ` · ${pct((everythingGain / everythingPutIn) * 100)}` : ''), tone: everythingGain >= 0 ? 'pos' : 'neg' },
            { label: 'Money put in', value: money(everythingPutIn, 'AUD', 0) },
          ]}
          extra={hasUsd && (rate && everything > 0 ? (
            <div className="space-y-1">
              <div className="flex h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--chip)' }}>
                <span style={{ width: `${(aud.value / everything) * 100}%`, background: 'var(--aud)' }} />
                <span style={{ width: `${((usd.value * rate) / everything) * 100}%`, background: 'var(--usd)' }} />
              </div>
              <div className="flex justify-between text-[11px] theme-text-muted">
                <span>A$ shares {Math.round((aud.value / everything) * 100)}%</span>
                <span>US$ shares {Math.round(((usd.value * rate) / everything) * 100)}%</span>
              </div>
            </div>
          ) : <p className="text-[11px] theme-text-muted">Exchange rate unavailable right now: US$ not included.</p>)} />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="card xl:col-span-2 space-y-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold theme-text">Value over time</h2>
              <p className="text-xs theme-text-muted">
                Rebuilt from your trades and daily closing prices{view === 'BOTH' ? '; US$ converted at today\'s rate' : ''}.
              </p>
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
          {attention.map((a, i) => (
            <div key={a.title} className="flex gap-3 rounded-xl p-3 surface-2">
              <span className="num w-6 h-6 shrink-0 rounded-md flex items-center justify-center text-xs font-semibold"
                style={{ background: 'var(--chip)' }}>{i + 1}</span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold theme-text">{a.title}</p>
                <p className="text-xs theme-text-muted">{a.detail}</p>
              </div>
              <Link to={a.to} className="btn-secondary !py-1 !px-3 text-xs self-start">{a.action}</Link>
            </div>
          ))}
          {!attention.length && (
            <p className="text-sm theme-text-muted py-4">Nothing right now. Sapient checks each portfolio twice a trading day.</p>
          )}
        </div>
      </div>

      <div className="card space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold theme-text">Your portfolios</h2>
          <Link to="/portfolios" className="text-sm font-medium theme-text-secondary hover:underline">See all</Link>
        </div>
        {loading ? <Shimmer className="h-32 w-full" /> : portfolios.length === 0 ? (
          <div className="text-center py-10 space-y-2">
            <Briefcase className="w-8 h-8 mx-auto theme-text-muted" />
            <p className="theme-text-secondary">No portfolios yet</p>
            <p className="text-sm theme-text-muted">Build one with the Auto, Manual or CAPM builder.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider theme-text-muted border-b theme-border">
                  <th className="py-2 font-semibold">Portfolio</th>
                  <th className="py-2 font-semibold hidden md:table-cell">How it's run</th>
                  <th className="py-2 font-semibold text-right">Value</th>
                  <th className="py-2 font-semibold text-right">Return</th>
                  <th className="py-2 font-semibold text-right hidden sm:table-cell">Last 3 months</th>
                </tr>
              </thead>
              <tbody>
                {portfolios.map((p) => {
                  const s = summaryFor(p.id)
                  const currency = currencyOf(p)
                  const up = (s?.total_return ?? 0) >= 0
                  const held = s ? s.holdings.filter((h) => h.quantity > 0).length : p.position_count ?? 0
                  return (
                    <tr key={p.id} className="border-b theme-border last:border-b-0">
                      <td className="py-3">
                        <Link to={`/portfolios/${p.id}`} className="flex items-stretch gap-3 group">
                          <span className="w-1 rounded-full shrink-0" style={{ background: colorOf(currency) }} />
                          <span className="min-w-0">
                            <span className="block font-semibold theme-text group-hover:underline truncate">{p.name}</span>
                            <span className="block text-xs theme-text-muted">
                              {currency === 'AUD' ? 'ASX' : 'US'} · {held} stock{held === 1 ? '' : 's'} · since {new Date(p.created_at).toLocaleDateString(undefined, { month: 'short', year: 'numeric' })}
                            </span>
                          </span>
                        </Link>
                      </td>
                      <td className="py-3 hidden md:table-cell">
                        <span className="flex flex-wrap gap-1.5">
                          <span className="chip">{p.strategy === 'factor' ? 'Model B' : 'Simple rules'}</span>
                          <span className="chip" style={p.trading_environment === 'live' ? { background: 'var(--neg-tint)', color: 'var(--neg)' } : undefined}>
                            {p.trading_environment === 'live' ? 'Live' : p.trading_environment === 'paper' ? 'Paper' : 'Research'}
                          </span>
                        </span>
                      </td>
                      <td className="py-3 text-right num font-semibold theme-text">
                        {s ? money(s.total_value, currency, 0) : summaries === null ? '…' : money(Number(p.initial_investment), currency, 0)}
                      </td>
                      <td className={`py-3 text-right num ${up ? 'text-pos' : 'text-neg'}`}>
                        {s ? `${up ? '▲ +' : '▼ '}${s.total_return_pct.toFixed(1)}%` : ''}
                      </td>
                      <td className="py-3 hidden sm:table-cell">
                        <span className="flex justify-end"><Sparkline points={sparkFor(p.id)} color={colorOf(currency)} /></span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
