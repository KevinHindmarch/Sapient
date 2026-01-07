import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { portfolioApi, stocksApi } from '../lib/api'
import { Portfolio, Position, Transaction } from '../types'
import { toast } from 'sonner'
import { ArrowLeft, TrendingUp, TrendingDown, DollarSign } from 'lucide-react'
import { format } from 'date-fns'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts'

const COLORS = ['#0ea5e9', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#6366f1', '#14b8a6']

interface PortfolioData {
  portfolio: Portfolio
  positions: Position[]
  snapshots: Record<string, unknown>[]
  transactions: Transaction[]
}

export default function PortfolioDetail() {
  const { id } = useParams<{ id: string }>()
  const [data, setData] = useState<PortfolioData | null>(null)
  const [loading, setLoading] = useState(true)
  const [currentPrices, setCurrentPrices] = useState<Record<string, number>>({})

  useEffect(() => {
    if (id) {
      loadPortfolio()
    }
  }, [id])

  const loadPortfolio = async () => {
    try {
      const response = await portfolioApi.detail(Number(id))
      setData(response.data)
      
      const symbols = response.data.positions.map((p: Position) => p.symbol)
      if (symbols.length > 0) {
        loadCurrentPrices(symbols)
      }
    } catch (error) {
      toast.error('Failed to load portfolio')
    } finally {
      setLoading(false)
    }
  }

  const loadCurrentPrices = async (symbols: string[]) => {
    const prices: Record<string, number> = {}
    for (const symbol of symbols) {
      try {
        const response = await stocksApi.info(symbol)
        prices[symbol] = response.data.current_price
      } catch {
        prices[symbol] = 0
      }
    }
    setCurrentPrices(prices)
  }

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-sky-500"></div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="text-center py-12">
        <p className="text-slate-600">Portfolio not found</p>
        <Link to="/portfolios" className="text-sky-500 hover:text-sky-600 mt-2 inline-block">
          Back to portfolios
        </Link>
      </div>
    )
  }

  const { portfolio, positions, transactions } = data

  const chartData = positions
    .filter((p) => p.status === 'active')
    .map((p) => ({
      name: p.symbol.replace('.AX', ''),
      value: Number(p.allocation_amount) || 0,
    }))

  const totalValue = positions.reduce((sum, p) => {
    if (p.status !== 'active') return sum
    const price = currentPrices[p.symbol] || Number(p.avg_cost)
    return sum + (price * Number(p.quantity))
  }, 0)

  const totalReturn = totalValue - Number(portfolio.initial_investment)
  const totalReturnPct = (totalReturn / Number(portfolio.initial_investment)) * 100

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link to="/portfolios" className="p-2 hover:bg-slate-100 rounded-lg transition-colors">
          <ArrowLeft className="w-5 h-5 text-slate-600" />
        </Link>
        <div>
          <h1 className="text-3xl font-bold text-slate-900">{portfolio.name}</h1>
          <div className="flex items-center gap-2 mt-1">
            <span className={`text-xs px-2 py-0.5 rounded-full ${
              portfolio.mode === 'auto' 
                ? 'bg-purple-100 text-purple-700' 
                : 'bg-sky-100 text-sky-700'
            }`}>
              {portfolio.mode === 'auto' ? 'Auto' : 'Manual'}
            </span>
            <span className={`text-xs px-2 py-0.5 rounded-full ${
              portfolio.risk_tolerance === 'conservative'
                ? 'bg-green-100 text-green-700'
                : portfolio.risk_tolerance === 'aggressive'
                ? 'bg-red-100 text-red-700'
                : 'bg-amber-100 text-amber-700'
            }`}>
              {portfolio.risk_tolerance}
            </span>
            <span className="text-sm text-slate-500">
              Created {format(new Date(portfolio.created_at), 'MMM d, yyyy')}
            </span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="card">
          <p className="text-sm text-slate-600">Initial Investment</p>
          <p className="text-2xl font-bold text-slate-900">
            ${Number(portfolio.initial_investment).toLocaleString()}
          </p>
        </div>
        <div className="card">
          <p className="text-sm text-slate-600">Current Value</p>
          <p className="text-2xl font-bold text-slate-900">
            ${totalValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </p>
        </div>
        <div className="card">
          <p className="text-sm text-slate-600">Total Return</p>
          <p className={`text-2xl font-bold flex items-center gap-1 ${
            totalReturn >= 0 ? 'text-emerald-600' : 'text-red-600'
          }`}>
            {totalReturn >= 0 ? <TrendingUp className="w-5 h-5" /> : <TrendingDown className="w-5 h-5" />}
            {totalReturn >= 0 ? '+' : ''}{totalReturnPct.toFixed(2)}%
          </p>
        </div>
        <div className="card">
          <p className="text-sm text-slate-600">Expected Sharpe</p>
          <p className="text-2xl font-bold text-sky-600">
            {Number(portfolio.expected_sharpe || 0).toFixed(2)}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 card">
          <h2 className="text-lg font-semibold text-slate-900 mb-4">Positions</h2>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left text-sm text-slate-500 border-b">
                  <th className="pb-3 font-medium">Symbol</th>
                  <th className="pb-3 font-medium">Quantity</th>
                  <th className="pb-3 font-medium">Avg Cost</th>
                  <th className="pb-3 font-medium">Current</th>
                  <th className="pb-3 font-medium">Value</th>
                  <th className="pb-3 font-medium">P/L</th>
                </tr>
              </thead>
              <tbody>
                {positions.filter(p => p.status === 'active').map((position) => {
                  const currentPrice = currentPrices[position.symbol] || Number(position.avg_cost)
                  const marketValue = currentPrice * Number(position.quantity)
                  const costBasis = Number(position.avg_cost) * Number(position.quantity)
                  const pl = marketValue - costBasis
                  const plPct = (pl / costBasis) * 100

                  return (
                    <tr key={position.id} className="border-b last:border-b-0">
                      <td className="py-3 font-medium">{position.symbol.replace('.AX', '')}</td>
                      <td className="py-3">{Number(position.quantity).toFixed(2)}</td>
                      <td className="py-3">${Number(position.avg_cost).toFixed(2)}</td>
                      <td className="py-3">${currentPrice.toFixed(2)}</td>
                      <td className="py-3">${marketValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                      <td className={`py-3 font-medium ${pl >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                        {pl >= 0 ? '+' : ''}{plPct.toFixed(1)}%
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <h2 className="text-lg font-semibold text-slate-900 mb-4">Allocation</h2>
          {chartData.length > 0 && (
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie
                  data={chartData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                >
                  {chartData.map((_, index) => (
                    <Cell key={index} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(value: number) => `$${value.toLocaleString()}`} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      <div className="card">
        <h2 className="text-lg font-semibold text-slate-900 mb-4">Recent Transactions</h2>
        {transactions.length === 0 ? (
          <p className="text-slate-500 text-center py-4">No transactions yet</p>
        ) : (
          <div className="space-y-3">
            {transactions.slice(0, 10).map((txn) => (
              <div key={txn.id} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                <div className="flex items-center gap-3">
                  <div className={`p-2 rounded ${
                    txn.txn_type === 'buy' ? 'bg-emerald-100' : 'bg-red-100'
                  }`}>
                    <DollarSign className={`w-4 h-4 ${
                      txn.txn_type === 'buy' ? 'text-emerald-600' : 'text-red-600'
                    }`} />
                  </div>
                  <div>
                    <p className="font-medium">
                      {txn.txn_type.toUpperCase()} {txn.symbol.replace('.AX', '')}
                    </p>
                    <p className="text-sm text-slate-500">
                      {Number(txn.quantity).toFixed(2)} @ ${Number(txn.price).toFixed(2)}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="font-medium">${Number(txn.total_amount).toLocaleString()}</p>
                  <p className="text-sm text-slate-500">
                    {format(new Date(txn.txn_time), 'MMM d, h:mm a')}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
