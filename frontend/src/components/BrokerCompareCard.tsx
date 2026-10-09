import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { apiErrorMessage, BrokerCompare, paperApi, twsApi } from '../lib/api'

const STATUS = {
  match: { text: 'Matches', tone: 'text-emerald-500' },
  differs: { text: 'Different', tone: 'text-amber-500' },
  model_only: { text: 'Only in Sapient', tone: 'text-amber-500' },
  broker_only: { text: 'Only at IBKR', tone: 'theme-text-secondary' },
}

// Read-only: the portfolio's model holdings next to what Interactive Brokers reports.
export default function BrokerCompareCard({ portfolioId }: { portfolioId: number }) {
  const [data, setData] = useState<BrokerCompare | null>(null)
  const [paperOn, setPaperOn] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [starting, setStarting] = useState(false)
  const [results, setResults] = useState<{ symbol: string; ok: boolean; quantity?: number; message?: string }[] | null>(null)

  const load = useCallback(() => {
    twsApi.compare(portfolioId).then((res) => setData(res.data)).catch(() => setData(null))
    paperApi.status().then((res) => setPaperOn(res.data.binding.enabled && !!res.data.binding.authorised_at)).catch(() => undefined)
  }, [portfolioId])

  useEffect(() => { load() }, [load])

  const start = async () => {
    setStarting(true)
    try {
      const res = await paperApi.startPortfolio(portfolioId)
      setResults(res.data.results)
      toast[res.data.started ? 'success' : 'error'](res.data.started
        ? 'Paper buy orders queued for this portfolio' : 'No paper orders could be queued')
      load()
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Could not start paper trading'))
    } finally {
      setStarting(false)
      setConfirming(false)
    }
  }

  if (!data) return null
  return (
    <div className="card" data-testid="broker-compare">
      <h2 className="text-lg font-semibold theme-text">Sapient vs Interactive Brokers</h2>
      <p className="text-sm theme-text-secondary mt-1">
        The holdings above are Sapient's <strong>model</strong>. This compares them with the shares your IBKR
        account actually holds{data.account ? ` (${data.account})` : ''}. Your account can also hold shares that belong
        to no Sapient portfolio. Nothing here changes your account.
      </p>
      {data.paper_started_at ? (
        <p className="text-sm text-emerald-600 mt-3" data-testid="paper-started">
          Trading on paper since {new Date(data.paper_started_at).toLocaleDateString()}: paper fills update this
          portfolio's holdings automatically.
        </p>
      ) : paperOn && (
        <div className="mt-3 rounded-xl border theme-border p-3 text-sm space-y-2">
          <p className="theme-text">
            <strong>Start paper trading this portfolio:</strong> Sapient buys the holdings listed above in your paper account
            (whole shares, cautious limit orders at TWS's delayed price). After that, paper fills keep this portfolio in
            step with your paper account and AI Trading can manage it, including fully automatically if you allow it.
          </p>
          {!confirming ? (
            <button className="btn-secondary" onClick={() => setConfirming(true)}>Start paper trading this portfolio…</button>
          ) : (
            <div className="flex flex-wrap gap-2">
              <button className="btn-primary" disabled={starting} onClick={start}>Yes, place the paper buy orders</button>
              <button className="btn-secondary" disabled={starting} onClick={() => setConfirming(false)}>Not now</button>
            </div>
          )}
        </div>
      )}
      {results && (
        <ul className="text-sm mt-2 space-y-1">
          {results.map((r) => (
            <li key={r.symbol} className={r.ok ? 'text-emerald-600' : 'text-amber-600'}>
              {r.symbol}: {r.ok ? `buy ${r.quantity} queued` : r.message}
            </li>
          ))}
        </ul>
      )}
      {!data.available ? (
        <p className="text-sm theme-text-secondary mt-3">
          No positions from TWS yet. <Link to="/brokerage" className="text-sky-500 hover:underline">Connect TWS</Link> to
          see this comparison.
        </p>
      ) : data.rows.length === 0 ? (
        <p className="text-sm theme-text-secondary mt-3">Neither Sapient nor IBKR shows any holdings for this portfolio.</p>
      ) : (
        <div className="overflow-x-auto mt-3">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left theme-text-muted">
                <th className="py-2 pr-4">Stock</th>
                <th className="py-2 pr-4 text-right">Sapient model</th>
                <th className="py-2 pr-4 text-right">IBKR account</th>
                <th className="py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row) => (
                <tr key={row.symbol} className="border-t theme-border">
                  <td className="py-2 pr-4 font-medium theme-text">{row.symbol}</td>
                  <td className="py-2 pr-4 text-right theme-text">{row.model_quantity ?? '—'}</td>
                  <td className="py-2 pr-4 text-right theme-text">{row.broker_quantity ?? '—'}</td>
                  <td className={`py-2 ${STATUS[row.status].tone}`}>{STATUS[row.status].text}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.positions_taken_at && (
            <p className="text-xs theme-text-muted mt-2">IBKR positions as of {new Date(data.positions_taken_at).toLocaleString()}</p>
          )}
        </div>
      )}
    </div>
  )
}
