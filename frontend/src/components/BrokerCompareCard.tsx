import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { BrokerCompare, twsApi } from '../lib/api'

const STATUS = {
  match: { text: 'Matches', tone: 'text-emerald-500' },
  differs: { text: 'Different', tone: 'text-amber-500' },
  model_only: { text: 'Only in Sapient', tone: 'text-amber-500' },
  broker_only: { text: 'Only at IBKR', tone: 'theme-text-secondary' },
}

// Read-only: the portfolio's model holdings next to what Interactive Brokers reports.
export default function BrokerCompareCard({ portfolioId }: { portfolioId: number }) {
  const [data, setData] = useState<BrokerCompare | null>(null)

  useEffect(() => {
    twsApi.compare(portfolioId).then((res) => setData(res.data)).catch(() => setData(null))
  }, [portfolioId])

  if (!data) return null
  return (
    <div className="card" data-testid="broker-compare">
      <h2 className="text-lg font-semibold theme-text">Sapient vs Interactive Brokers</h2>
      <p className="text-sm theme-text-secondary mt-1">
        The holdings above are Sapient's <strong>model</strong>. This compares them with the shares your IBKR
        account actually holds{data.account ? ` (${data.account})` : ''}. Your account can also hold shares that belong
        to no Sapient portfolio. Nothing here changes your account.
      </p>
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
