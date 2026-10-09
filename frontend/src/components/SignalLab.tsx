import { useState } from 'react'
import { toast } from 'sonner'
import { apiErrorMessage, SignalLabResult, signalsApi } from '../lib/api'

const pct = (v: number) => `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`

/**
 * Signal lab: which signals really beat simply holding each stock (5 years of daily prices, after costs,
 * significant after correcting for testing many at once, and still working lately), and the switch that
 * makes AI Trading use only those for this portfolio.
 */
export default function SignalLab({ portfolioId, strategy, onStrategy }: {
  portfolioId: number; strategy: 'rules' | 'signals'; onStrategy: (s: 'rules' | 'signals') => void
}) {
  const [lab, setLab] = useState<SignalLabResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [saving, setSaving] = useState(false)

  const run = async () => {
    setBusy(true)
    try {
      setLab((await signalsApi.portfolio(portfolioId)).data)
    } catch (err) {
      toast.error(apiErrorMessage(err, 'The signal lab could not run'))
    } finally {
      setBusy(false)
    }
  }

  const choose = async (next: 'rules' | 'signals') => {
    setSaving(true)
    try {
      await signalsApi.setStrategy(portfolioId, next)
      onStrategy(next)
      toast.success(next === 'signals' ? 'AI Trading now uses only signals that passed the lab for this portfolio.'
        : 'AI Trading uses the simple RSI + MACD rules for this portfolio.')
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Could not change how AI Trading decides'))
    } finally {
      setSaving(false)
    }
  }

  const symbols = lab ? [...new Set(lab.tests.map((t) => t.symbol))] : []
  return (
    <div className="card space-y-3" data-testid="signal-lab">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold theme-text">Signal lab</h3>
          <p className="text-xs theme-text-secondary mt-0.5 max-w-2xl">
            Tests 7 well-known trading signals on each holding over 5 years of daily prices and keeps only those that
            beat simply holding the stock after trading costs, are statistically significant (after correcting for
            testing many at once) and still worked in the last 2 years. Past results don't guarantee future ones —
            no strategy wins every day.
          </p>
        </div>
        <button className="btn-secondary text-sm" onClick={run} disabled={busy} data-testid="run-lab">
          {busy ? 'Testing…' : lab ? 'Run again' : 'Run the signal lab'}
        </button>
      </div>

      <fieldset className="text-sm space-y-1">
        <legend className="theme-text font-medium mb-1">How should AI Trading decide for this portfolio?</legend>
        <label className="flex items-start gap-2 theme-text">
          <input type="radio" name={`strategy-${portfolioId}`} className="mt-1" checked={strategy === 'rules'}
            disabled={saving} onChange={() => choose('rules')} />
          <span><strong>Simple rules:</strong> RSI (with MACD) — buy a little when oversold, sell some when overbought.</span>
        </label>
        <label className="flex items-start gap-2 theme-text">
          <input type="radio" name={`strategy-${portfolioId}`} className="mt-1" checked={strategy === 'signals'}
            disabled={saving} onChange={() => choose('signals')} data-testid="strategy-signals" />
          <span><strong>Signal lab:</strong> only signals that passed vote (stronger evidence counts more). When the vote
            says out, Sapient sells the whole holding; when it says hold again, it buys the planned shares back. Stocks
            with no passing signal are simply held. Stop-loss and take-profit always apply. Re-tested at every check.</span>
        </label>
      </fieldset>

      {lab && (
        <div className="space-y-4">
          {Object.entries(lab.errors).map(([s, e]) => (
            <p key={s} className="text-sm text-amber-600">{s}: {e}</p>
          ))}
          {symbols.map((symbol) => {
            const vote = lab.votes.find((v) => v.symbol === symbol)
            const rows = lab.tests.filter((t) => t.symbol === symbol)
            return (
              <div key={symbol}>
                <p className="text-sm font-semibold theme-text">
                  {symbol}{' '}
                  <span className={`text-xs font-normal ${vote ? (vote.says === 'out' ? 'text-red-500' : vote.says === 'hold' ? 'text-emerald-600' : 'theme-text-secondary') : 'theme-text-secondary'}`}>
                    {vote ? `— vote today: ${vote.says} (score ${vote.score.toFixed(2)})` : '— no signal passed: held as is'}
                  </span>
                </p>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs mt-1">
                    <thead>
                      <tr className="text-left theme-text-secondary">
                        <th className="py-1 pr-2">Signal</th><th className="pr-2 text-right">vs holding / yr</th>
                        <th className="pr-2 text-right">last {lab.recent_years} yrs</th><th className="pr-2 text-right">p-value</th>
                        <th className="pr-2 text-right">trades</th><th className="pr-2">says now</th><th>result</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((t) => (
                        <tr key={t.signal} className="border-t theme-border theme-text">
                          <td className="py-1 pr-2">{t.label}</td>
                          <td className={`pr-2 text-right ${t.edge_per_year >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>{pct(t.edge_per_year)}</td>
                          <td className={`pr-2 text-right ${t.recent_edge_per_year >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>{pct(t.recent_edge_per_year)}</td>
                          <td className="pr-2 text-right">{t.p_value.toFixed(3)}</td>
                          <td className="pr-2 text-right">{t.trades}</td>
                          <td className="pr-2">{t.holding_now ? 'hold' : 'out'}</td>
                          <td className={t.passed ? 'text-emerald-600 font-medium' : 'theme-text-secondary'}>
                            {t.passed ? '✓ passes' : t.verdict}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )
          })}
          <p className="text-xs theme-text-muted">
            Costs assumed: {(lab.cost_per_trade * 100).toFixed(2)}% per buy or sell. Significance: Benjamini–Hochberg at a
            {' '}{(lab.fdr * 100).toFixed(0)}% false discovery rate across every stock × signal above. Yahoo prices are
            research data.
          </p>
        </div>
      )}
    </div>
  )
}
