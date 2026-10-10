import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { apiErrorMessage, BrokerCompare, liveApi, paperApi, tradingApiFor, TradingEnv } from '../lib/api'

type Mode = 'suggestions' | 'autonomous'

/**
 * "Buy on paper & manage" / "Buy for real & manage": buys the portfolio's holdings once in the chosen
 * account and sets how Sapient manages it afterwards (you approve each trade, or fully automatic).
 */
export default function BuyAndManage({ portfolioId, data, onDone }: {
  portfolioId: number; data: BrokerCompare; onDone: () => void
}) {
  const [available, setAvailable] = useState<Record<TradingEnv, boolean>>({ paper: false, live: false })
  const [env, setEnv] = useState<TradingEnv | null>(null)
  const [mode, setMode] = useState<Mode>('suggestions')
  const modelB = data.strategy === 'factor'
  const [entry, setEntry] = useState<'now' | 'rsi_dip' | 'staged'>(modelB ? 'staged' : 'now')
  const onDip = entry === 'rsi_dip'
  const [rsiBelow, setRsiBelow] = useState(30)
  const [deadlineDays, setDeadlineDays] = useState(20)
  const [understood, setUnderstood] = useState(false)
  const [busy, setBusy] = useState(false)
  const [results, setResults] = useState<{ symbol: string; ok: boolean; waiting?: boolean; quantity?: number; message?: string }[] | null>(null)

  useEffect(() => {
    const on = (b: { enabled: boolean; authorised_at: string | null; halted: boolean }) => b.enabled && !!b.authorised_at && !b.halted
    Promise.all([paperApi.status(), liveApi.status()])
      .then(([p, l]) => setAvailable({ paper: on(p.data.binding), live: on(l.data.binding) }))
      .catch(() => undefined)
  }, [])

  if (data.trading_environment) {
    const live = data.trading_environment === 'live'
    const since = live ? data.live_started_at : data.paper_started_at
    return (
      <p className={`text-sm mt-3 ${live ? 'text-red-600' : 'text-emerald-600'}`} data-testid="paper-started">
        {live ? 'Trading with REAL MONEY' : 'Trading on paper'}{since ? ` since ${new Date(since).toLocaleDateString()}` : ''} ·{' '}
        {data.ai_mode === 'autonomous' ? 'fully automatic' : data.ai_mode === 'suggestions' ? 'you approve each trade' : 'AI Trading off'}.
        Fills update this portfolio's holdings automatically. Change how it is managed with the AI Trading Mode above.
        {data.waiting.length > 0 && (
          <span className="block mt-1 text-amber-600" data-testid="entry-waiting">
            Waiting to buy {data.waiting.join(', ')} when RSI is below {data.entry_rsi_below ?? 30}
            {data.entry_deadline ? ` (until ${new Date(data.entry_deadline).toLocaleDateString()}; then skipped)` : ''}.
            Checked twice each trading day{data.ai_mode === 'off' ? ' — switch AI Trading on, or nothing is bought' : ''}.
          </span>
        )}
        {data.entry_mode === 'staged' && (
          <span className="block mt-1 theme-text-secondary" data-testid="entry-staged">
            Model B is buying this portfolio a third at a time: one slice at the next check, the others in the next two
            months{data.ai_mode === 'off' ? ' — switch AI Trading on, or nothing is bought' : ''}.
          </span>
        )}
        {data.skipped.length > 0 && (
          <span className="block mt-1 theme-text-secondary">Skipped (no RSI dip by the deadline): {data.skipped.join(', ')}.</span>
        )}
      </p>
    )
  }
  if (!available.paper && !available.live) {
    return (
      <p className="text-sm theme-text-secondary mt-3">
        To buy this portfolio through Interactive Brokers, first authorise paper or real-money trading in{' '}
        <Link to="/brokerage" className="text-sky-500 hover:underline">Brokerage → Step 4</Link>.
      </p>
    )
  }

  const go = async () => {
    if (!env) return
    setBusy(true)
    try {
      const res = await tradingApiFor(env).startPortfolio(portfolioId, mode,
        onDip ? { entry: 'rsi_dip', rsi_below: rsiBelow, deadline_days: deadlineDays } : { entry })
      setResults(res.data.results)
      toast[res.data.started ? 'success' : 'error'](!res.data.started
        ? 'No orders could be queued; see the reasons below.'
        : res.data.entry === 'rsi_dip'
          ? `Sapient will buy each stock when its RSI drops below ${rsiBelow} (checked twice each trading day).`
          : res.data.entry === 'staged'
            ? 'Model B will buy the first third at its next check and the rest over the next two months.'
          : `${env === 'live' ? 'REAL-MONEY' : 'Paper'} buy orders queued. Sapient manages this portfolio from now on.`)
      onDone()
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Could not start'))
    } finally {
      setBusy(false)
    }
  }

  const live = env === 'live'
  return (
    <div className={`mt-3 rounded-xl border p-3 text-sm space-y-3 ${live ? 'border-red-500/50' : 'theme-border'}`} data-testid="buy-and-manage">
      <p className="theme-text"><strong>Buy this portfolio and let Sapient manage it.</strong> Sapient buys the holdings
        listed above (whole shares) and then, during market hours, buys and sells them for you within your limits.</p>
      <div className="flex flex-wrap gap-2">
        <button className={env === 'paper' ? 'btn-primary' : 'btn-secondary'} disabled={!available.paper}
          onClick={() => { setEnv('paper'); setUnderstood(false) }} data-testid="choose-paper">Buy on paper & manage</button>
        <button className={env === 'live' ? 'btn-primary !bg-red-600 !from-red-600 !to-red-700' : 'btn-secondary'}
          disabled={!available.live} onClick={() => { setEnv('live'); setUnderstood(false) }} data-testid="choose-live"
          title={available.live ? '' : 'Authorise real-money trading first (Brokerage → Live → Step 4)'}>
          Buy for real & manage</button>
      </div>
      {env && (
        <>
          <fieldset className="space-y-1">
            <legend className="theme-text font-medium mb-1">How should Sapient manage it?</legend>
            <label className="flex items-start gap-2 theme-text">
              <input type="radio" name="mode" className="mt-1" checked={mode === 'suggestions'} onChange={() => setMode('suggestions')} />
              <span><strong>Semi-automatic:</strong> Sapient finds buys and sells and asks you first (pop-up and AI Inbox).</span>
            </label>
            <label className="flex items-start gap-2 theme-text">
              <input type="radio" name="mode" className="mt-1" checked={mode === 'autonomous'} onChange={() => setMode('autonomous')} />
              <span><strong>Fully automatic:</strong> Sapient trades on its own within your limits and tells you after each trade
                (needs “Allow fully automatic {live ? 'real-money' : 'paper'} orders” ticked in Brokerage, automatic checks on and
                AI Trading mode Autonomous; the checklist on the AI Trading page shows what is missing).</span>
            </label>
          </fieldset>
          <fieldset className="space-y-1">
            <legend className="theme-text font-medium mb-1">When should Sapient buy?</legend>
            {modelB && (
              <label className="flex items-start gap-2 theme-text">
                <input type="radio" name="entry" className="mt-1" checked={entry === 'staged'} onChange={() => setEntry('staged')}
                  data-testid="entry-staged-choice" />
                <span><strong>Over three months (recommended for Model B):</strong> buy a third of the holdings at the next
                  check and the rest in the next two months. Each third is re-checked against Model B's ranking when its turn
                  comes, so you don't put everything in on one day.</span>
              </label>
            )}
            <label className="flex items-start gap-2 theme-text">
              <input type="radio" name="entry" className="mt-1" checked={entry === 'now'} onChange={() => setEntry('now')} />
              <span><strong>Now:</strong> buy all the holdings straight away.</span>
            </label>
            <label className="flex items-start gap-2 theme-text">
              <input type="radio" name="entry" className="mt-1" checked={onDip} onChange={() => setEntry('rsi_dip')}
                data-testid="entry-dip" />
              <span><strong>When each stock is cheap:</strong> buy a stock only when its RSI drops below{' '}
                <input type="number" min={5} max={50} value={rsiBelow} onChange={(e) => setRsiBelow(Number(e.target.value))}
                  className="input-field !w-16 !py-0.5 inline-block" aria-label="RSI level" />{' '}
                (checked twice each trading day). If it hasn't by{' '}
                <input type="number" min={1} max={120} value={deadlineDays} onChange={(e) => setDeadlineDays(Number(e.target.value))}
                  className="input-field !w-16 !py-0.5 inline-block" aria-label="Deadline in trading days" />{' '}
                trading days, that stock is skipped.</span>
            </label>
          </fieldset>
          {live && (
            <label className="flex items-start gap-2 text-red-600">
              <input type="checkbox" className="mt-1" checked={understood} onChange={(e) => setUnderstood(e.target.checked)}
                data-testid="live-understood" />
              <span>I understand Sapient will spend <strong>my real money</strong> buying these shares
                {onDip ? ' when their RSI dips' : entry === 'staged' ? ' over the next three months' : ' now'}, and will keep
                buying and selling them {mode === 'autonomous' ? 'without asking me' : 'when I approve'}.</span>
            </label>
          )}
          <button className={live ? 'btn-primary !bg-red-600 !from-red-600 !to-red-700' : 'btn-primary'}
            disabled={busy || (live && !understood)} onClick={go}>
            {onDip ? (live ? 'Buy with real money on RSI dips' : 'Buy on paper on RSI dips')
              : entry === 'staged' ? (live ? 'Buy with real money over three months' : 'Buy on paper over three months')
                : (live ? 'Buy with real money now' : 'Buy on paper now')}
          </button>
        </>
      )}
      {results && (
        <ul className="space-y-1">
          {results.map((r) => (
            <li key={r.symbol} className={r.ok ? 'text-emerald-600' : 'text-amber-600'}>
              {r.symbol}: {r.ok ? (r.waiting ? r.message : `buy ${r.quantity} queued`) : r.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
