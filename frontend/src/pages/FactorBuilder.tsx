import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { Layers } from 'lucide-react'
import { apiErrorMessage, factorsApi, FactorBuild, FactorKey, money, portfolioApi } from '../lib/api'

const FACTORS: FactorKey[] = ['MOM', 'RMW', 'HML', 'CMA', 'SMB']
const SHORT: Record<FactorKey, string> = { MOM: 'Momentum', RMW: 'Profit', HML: 'Value', CMA: 'Investment', SMB: 'Size' }
const pct = (v: number) => `${(v * 100).toFixed(1)}%`

/**
 * Factor Builder (Model B): rank the market on Fama-French five factors + momentum, take the top stocks,
 * then weight them with the max-Sharpe optimiser. Saved portfolios are managed monthly with Model B.
 */
export default function FactorBuilder() {
  const navigate = useNavigate()
  const [market, setMarket] = useState<'ASX' | 'US'>('ASX')
  const [amount, setAmount] = useState(20000)
  const [risk, setRisk] = useState('moderate')
  const [topN, setTopN] = useState(20)
  const [undervaluedOnly, setUndervaluedOnly] = useState(true)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<FactorBuild | null>(null)
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const currency = market === 'US' ? 'USD' : 'AUD'

  const run = async () => {
    setBusy(true)
    setResult(null)
    try {
      setResult((await factorsApi.build(market, amount, risk, topN, undervaluedOnly)).data)
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Could not build the Model B portfolio'))
    } finally {
      setBusy(false)
    }
  }

  const save = async () => {
    if (!result || !name.trim()) return
    setSaving(true)
    try {
      const saved = await portfolioApi.save(name.trim(), result.optimization, amount, 'factor', risk, market)
      if (saved.data.warning) toast.warning(saved.data.warning)
      toast.success('Saved. Buy it on the portfolio page; with AI Trading on, Model B manages it every month.')
      if (saved.data.portfolio_id) navigate(`/portfolios/${saved.data.portfolio_id}`)
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Could not save the portfolio'))
    } finally {
      setSaving(false)
    }
  }

  const weights = result?.optimization.weights ?? {}
  return (
    <div className="space-y-6 animate-fade-in">
      <div className="page-header">
        <div className="flex items-center gap-2">
          <Layers className="w-8 h-8 text-sky-400" />
          <h1 className="page-title">Auto Builder · Model B</h1>
        </div>
        <p className="page-subtitle">
          Ranks every stock in the {market === 'US' ? 'S&P 500' : 'ASX 200'} list on five Fama-French factors plus
          momentum, keeps the undervalued ones (book-to-market above the market average), takes the best of those and
          weights them with the max-Sharpe optimiser. With AI Trading on, it re-ranks every month: holdings still in the
          top 40 are kept, the rest are sold, and the best new undervalued stocks are bought.
        </p>
      </div>

      <div className="card space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
          <label className="block"><span className="label">Market</span>
            <select className="input-field" value={market} onChange={(e) => setMarket(e.target.value as 'ASX' | 'US')}>
              <option value="ASX">ASX (A$)</option><option value="US">US (US$)</option>
            </select></label>
          <label className="block"><span className="label">Amount ({currency === 'USD' ? 'US$' : 'A$'})</span>
            <input className="input-field" type="number" min={1000} step={1000} value={amount}
              onChange={(e) => setAmount(Number(e.target.value))} /></label>
          <label className="block"><span className="label">Risk</span>
            <select className="input-field" value={risk} onChange={(e) => setRisk(e.target.value)}>
              <option value="conservative">Conservative (max 25% per stock)</option>
              <option value="moderate">Moderate (max 40% per stock)</option>
              <option value="aggressive">Aggressive (max 60% per stock)</option>
            </select></label>
          <label className="block"><span className="label">Stocks to pick</span>
            <input className="input-field" type="number" min={5} max={40} value={topN}
              onChange={(e) => setTopN(Math.min(40, Math.max(5, Number(e.target.value) || 20)))} /></label>
        </div>
        <label className="flex items-start gap-2 text-sm theme-text">
          <input type="checkbox" className="mt-1" checked={undervaluedOnly} onChange={(e) => setUndervaluedOnly(e.target.checked)}
            data-testid="undervalued-only" />
          <span><strong>Only undervalued stocks:</strong> book-to-market above the market average (cheaper than
            average for the assets they own). Untick to take the best scores regardless of price.</span>
        </label>
        <p className="text-xs theme-text-secondary">
          Score = 35% momentum + 25% profitability + 20% value + 10% investment + 10% size, each standardised across the
          market. The first ranking of a market takes a few minutes (it reads every company); later ones are cached.
          Long-run tests favoured this model most in Australia; in the US it has trailed the S&amp;P 500 since 2010.
        </p>
        <button className="btn-primary" onClick={run} disabled={busy || amount < 1000} data-testid="factor-build">
          {busy ? 'Ranking the market and optimising…' : 'Rank & optimise'}
        </button>
      </div>

      {result && (
        <>
          <div className="card space-y-3">
            <h2 className="text-lg font-semibold theme-text">Optimised portfolio</h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
              <div><p className="theme-text-secondary">Expected return</p><p className="theme-text font-semibold">{pct(result.optimization.expected_return)}</p></div>
              <div><p className="theme-text-secondary">Volatility</p><p className="theme-text font-semibold">{pct(result.optimization.volatility)}</p></div>
              <div><p className="theme-text-secondary">Sharpe ratio</p><p className="theme-text font-semibold">{result.optimization.sharpe_ratio.toFixed(2)}</p></div>
              <div><p className="theme-text-secondary">Stocks with weight</p><p className="theme-text font-semibold">{Object.values(weights).filter((w) => w > 0).length}</p></div>
            </div>
            <p className="text-xs theme-text-muted">Expected return and Sharpe come from the last 2 years of prices: a description of the past, not a forecast.</p>
            <div className="flex flex-wrap gap-2 items-end">
              <label className="block grow"><span className="label">Portfolio name</span>
                <input className="input-field" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. ASX Model B" /></label>
              <button className="btn-primary" onClick={save} disabled={saving || !name.trim()}>{saving ? 'Saving…' : 'Save portfolio'}</button>
            </div>
          </div>

          <div className="card">
            <h2 className="text-lg font-semibold theme-text mb-1">Model B picks ({result.ranking.length})</h2>
            <p className="text-xs theme-text-secondary mb-2">
              {result.ranked} stocks ranked{result.undervalued_only ? `, ${result.undervalued} of them undervalued` : ''}.
              The # column is each stock's rank in the whole market.</p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="text-left theme-text-secondary">
                  <th className="py-1 pr-2">#</th><th className="pr-2">Stock</th><th className="pr-2 text-right">Weight</th>
                  <th className="pr-2 text-right">Amount</th><th className="pr-2 text-right">Score</th>
                  {FACTORS.map((f) => <th key={f} className="pr-2 text-right" title={result.labels[f]}>{SHORT[f]}</th>)}
                </tr></thead>
                <tbody>{result.ranking.map((r) => {
                  const w = weights[r.symbol] ?? 0
                  return (
                    <tr key={r.symbol} className={`border-t theme-border ${w > 0 ? 'theme-text' : 'theme-text-muted'}`}>
                      <td className="py-1 pr-2">{r.rank}</td>
                      <td className="pr-2"><span className="font-mono">{r.symbol.replace('.AX', '')}</span>{' '}
                        <span className="text-xs theme-text-secondary">{r.name ?? ''}</span></td>
                      <td className="pr-2 text-right">{w > 0 ? pct(w) : '—'}</td>
                      <td className="pr-2 text-right">{w > 0 ? money(w * amount, currency, 0) : '—'}</td>
                      <td className="pr-2 text-right">{r.score.toFixed(2)}</td>
                      {FACTORS.map((f) => {
                        const z = r.z[f]
                        return <td key={f} className={`pr-2 text-right ${z === undefined ? '' : z >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
                          {z === undefined ? '—' : z.toFixed(1)}</td>
                      })}
                    </tr>
                  )
                })}</tbody>
              </table>
            </div>
            <p className="text-xs theme-text-muted mt-2">Factor columns are z-scores (0 = market average, +1 = one standard deviation better). Stocks the optimiser gave no weight are greyed out.</p>
          </div>
        </>
      )}
    </div>
  )
}
