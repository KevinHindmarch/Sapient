import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'
import { apiErrorMessage, factorsApi, FactorPlan } from '../lib/api'

/**
 * How AI Trading decides for this portfolio: simple RSI + MACD rules, or Model B (re-ranked and re-optimised
 * every month: keep holdings still in the top 40, sell the rest, buy the best new stocks), with this month's plan.
 */
export default function FactorStrategy({ portfolioId, strategy, onStrategy }: {
  portfolioId: number; strategy: 'rules' | 'factor'; onStrategy: (s: 'rules' | 'factor') => void
}) {
  const [plan, setPlan] = useState<FactorPlan | null>(null)
  const [keepWithin, setKeepWithin] = useState(40)
  const [saving, setSaving] = useState(false)

  const load = useCallback(() => {
    factorsApi.plan(portfolioId).then((res) => { setPlan(res.data.plan); setKeepWithin(res.data.keep_within) })
      .catch(() => undefined)
  }, [portfolioId])
  useEffect(() => { load() }, [load, strategy])

  const choose = async (next: 'rules' | 'factor') => {
    setSaving(true)
    try {
      await factorsApi.setStrategy(portfolioId, next)
      onStrategy(next)
      toast.success(next === 'factor'
        ? 'Model B now manages this portfolio. It keeps the current holdings this month and re-ranks next month.'
        : 'AI Trading uses the simple RSI + MACD rules for this portfolio.')
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Could not change how AI Trading decides'))
    } finally {
      setSaving(false)
    }
  }

  const target = Object.entries(plan?.target ?? {}).sort(([a], [b]) => (plan?.ranks?.[a] ?? 999) - (plan?.ranks?.[b] ?? 999))
  return (
    <div className="card space-y-3" data-testid="factor-strategy">
      <h3 className="text-sm font-semibold theme-text">How should AI Trading decide for this portfolio?</h3>
      <fieldset className="text-sm space-y-1">
        <label className="flex items-start gap-2 theme-text">
          <input type="radio" name={`strategy-${portfolioId}`} className="mt-1" checked={strategy === 'rules'}
            disabled={saving} onChange={() => choose('rules')} />
          <span><strong>Simple rules:</strong> RSI (with MACD) — buy a little when oversold, sell some when overbought.</span>
        </label>
        <label className="flex items-start gap-2 theme-text">
          <input type="radio" name={`strategy-${portfolioId}`} className="mt-1" checked={strategy === 'factor'}
            disabled={saving} onChange={() => choose('factor')} data-testid="strategy-factor" />
          <span><strong>Model B (factors):</strong> every month Sapient re-ranks the market on momentum, profitability,
            value, investment and size. Holdings still in the top {keepWithin} are kept, the rest are sold, the best new
            stocks are bought (up to 20) and the max-Sharpe optimiser sets the weights. Stop-loss and take-profit still
            apply between rebalances. Needs AI Trading on; fully automatic trades without asking.</span>
        </label>
      </fieldset>
      {strategy === 'factor' && plan && (
        <div className="text-sm space-y-2">
          <p className="theme-text-secondary">
            {plan.adopted ? `Plan for ${plan.month}: the portfolio as built (the first re-ranking is next month).`
              : `Plan for ${plan.month}: re-ranked and re-optimised. Sapient trades toward it at its checks.`}
          </p>
          {target.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead><tr className="text-left theme-text-secondary"><th className="py-1 pr-2">Stock</th>
                  <th className="pr-2 text-right">Rank</th><th className="pr-2 text-right">Target shares</th><th>Why</th></tr></thead>
                <tbody>{target.map(([symbol, shares]) => (
                  <tr key={symbol} className="border-t theme-border theme-text">
                    <td className="py-1 pr-2 font-mono">{symbol.replace('.AX', '')}</td>
                    <td className="pr-2 text-right">{plan.ranks?.[symbol] ?? '—'}</td>
                    <td className="pr-2 text-right">{shares}</td>
                    <td className="theme-text-secondary">{plan.reasons?.[symbol] ?? ''}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
          {Object.entries(plan.reasons ?? {}).filter(([s]) => !(s in (plan.target ?? {}))).map(([s, why]) => (
            <p key={s} className="text-xs theme-text-secondary"><span className="font-mono">{s.replace('.AX', '')}</span>: {why}</p>
          ))}
        </div>
      )}
      {strategy === 'factor' && !plan && (
        <p className="text-sm theme-text-secondary">The plan is made at the next scheduled check (AI Trading must be on).</p>
      )}
    </div>
  )
}
