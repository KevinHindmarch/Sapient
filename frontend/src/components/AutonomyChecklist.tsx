import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { CheckCircle2, Circle } from 'lucide-react'
import { AutonomyChecklist as Checklist, paperApi } from '../lib/api'

function Item({ ok, text }: { ok: boolean; text: string }) {
  return (
    <li className="flex items-start gap-2">
      {ok ? <CheckCircle2 className="w-4 h-4 mt-0.5 text-emerald-500 shrink-0" /> : <Circle className="w-4 h-4 mt-0.5 theme-text-muted shrink-0" />}
      <span className={ok ? 'theme-text' : 'theme-text-secondary'}>{text}</span>
    </li>
  )
}

// What must be switched on for Sapient to trade a portfolio on paper without asking.
export default function AutonomyChecklist() {
  const [data, setData] = useState<Checklist | null>(null)

  useEffect(() => {
    const load = () => paperApi.autonomy().then((res) => setData(res.data)).catch(() => undefined)
    load()
    const timer = window.setInterval(load, 15000)
    return () => window.clearInterval(timer)
  }, [])

  if (!data) return null
  return (
    <section className="card space-y-4" data-testid="autonomy-checklist">
      <div>
        <h2 className="text-xl font-semibold theme-text">Fully automatic trading</h2>
        <p className="text-sm theme-text-muted mt-1">
          When everything below is ticked, Sapient manages that portfolio on its own: during market hours it checks the
          rules, places paper buy and sell orders within your limits, and updates the portfolio from the fills. You get a
          notification after each trade and can press Emergency stop (tray icon) at any time. Each portfolio trades either on
          paper or with real money, whichever you chose when you bought it.
        </p>
      </div>
      <ul className="space-y-1.5 text-sm">
        {data.shared.map((item) => <Item key={item.key} ok={item.ok} text={item.text} />)}
      </ul>
      {data.portfolios.length === 0 ? (
        <p className="text-sm theme-text-secondary">No portfolios yet.</p>
      ) : (
        <div className="grid md:grid-cols-2 gap-3">
          {data.portfolios.map((p) => (
            <div key={p.portfolio_id} className="rounded-xl border theme-border p-3 text-sm">
              <div className="flex items-center justify-between gap-2 mb-2">
                <span className="flex items-center gap-2">
                  <Link to={`/portfolios/${p.portfolio_id}`} className="font-semibold text-sky-500 hover:underline">{p.name}</Link>
                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${p.environment === 'live'
                    ? 'bg-red-500/15 text-red-600 border-red-500/40' : 'bg-slate-500/10 theme-text-secondary theme-border'}`}>
                    {p.environment === 'live' ? 'REAL MONEY' : 'PAPER'}</span>
                </span>
                <span className={`text-xs font-bold px-2 py-0.5 rounded-md border ${p.autonomous
                  ? 'bg-emerald-500/15 text-emerald-600 border-emerald-500/30' : 'bg-slate-500/10 theme-text-secondary theme-border'}`}>
                  {p.autonomous ? 'TRADING AUTOMATICALLY' : 'NOT AUTOMATIC'}
                </span>
              </div>
              <ul className="space-y-1">{p.items.map((item) => <Item key={item.key} ok={item.ok} text={item.text} />)}</ul>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
