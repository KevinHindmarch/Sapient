import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { portfolioApi, stocksApi } from '../lib/api'
import { Portfolio, Position } from '../types'
import { useAuth } from '../lib/auth'
import { Briefcase, TrendingUp, TrendingDown, Wand2, Wrench, ArrowRight, Loader2 } from 'lucide-react'

interface PortfolioWithPositions {
  portfolio: Portfolio
  positions: Position[]
}

export default function Dashboard() {
  const { user } = useAuth()
  const [portfolios, setPortfolios] = useState<Portfolio[]>([])
  const [loading, setLoading] = useState(true)
  const [totalReturn, setTotalReturn] = useState<number | null>(null)
  const [totalCurrentValue, setTotalCurrentValue] = useState<number>(0)
  const [loadingReturns, setLoadingReturns] = useState(false)

  useEffect(() => {
    loadPortfolios()
  }, [])

  const loadPortfolios = async () => {
    try {
      const response = await portfolioApi.list()
      setPortfolios(response.data)
      
      if (response.data.length > 0) {
        loadRealReturns(response.data)
      }
    } catch (error) {
      console.error('Failed to load portfolios:', error)
    } finally {
      setLoading(false)
    }
  }

  const loadRealReturns = async (portfolioList: Portfolio[]) => {
    setLoadingReturns(true)
    try {
      let allInvestment = 0
      let allCurrentValue = 0
      
      for (const p of portfolioList) {
        const detail = await portfolioApi.detail(p.id)
        const positions = detail.data.positions as Position[]
        allInvestment += Number(p.initial_investment)
        
        const symbols = positions.filter(pos => pos.status === 'active').map(pos => pos.symbol)
        const prices: Record<string, number> = {}
        
        for (const symbol of symbols) {
          try {
            const info = await stocksApi.info(symbol)
            prices[symbol] = info.data.current_price
          } catch {
            prices[symbol] = 0
          }
        }
        
        const portfolioValue = positions
          .filter(pos => pos.status === 'active')
          .reduce((sum, pos) => {
            const price = prices[pos.symbol] || Number(pos.avg_cost)
            return sum + (price * Number(pos.quantity))
          }, 0)
        
        allCurrentValue += portfolioValue
      }
      
      setTotalCurrentValue(allCurrentValue)
      setTotalReturn(allCurrentValue - allInvestment)
    } catch (error) {
      console.error('Failed to load returns:', error)
    } finally {
      setLoadingReturns(false)
    }
  }

  const totalInvestment = portfolios.reduce((sum, p) => sum + Number(p.initial_investment), 0)
  const returnPct = totalInvestment > 0 && totalReturn !== null ? (totalReturn / totalInvestment) * 100 : 0

  return (
    <div className="space-y-6">
      <div className="page-header">
        <h1 className="page-title">
          Welcome back, <span className="gradient-text">{user?.display_name || 'Investor'}</span>!
        </h1>
        <p className="page-subtitle">
          Manage your ASX portfolio with intelligent optimization
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="stat-card">
          <div className="flex items-center gap-4">
            <div className="p-4 bg-gradient-to-br from-sky-400 to-sky-600 rounded-2xl shadow-lg">
              <Briefcase className="w-7 h-7 text-white" />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-500">Total Portfolios</p>
              <p className="stat-value">{portfolios.length}</p>
            </div>
          </div>
        </div>

        <div className="stat-card">
          <div className="flex items-center gap-4">
            <div className="p-4 bg-gradient-to-br from-emerald-400 to-emerald-600 rounded-2xl shadow-lg">
              <TrendingUp className="w-7 h-7 text-white" />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-500">Total Invested</p>
              <p className="stat-value">
                ${totalInvestment.toLocaleString()}
              </p>
            </div>
          </div>
        </div>

        <div className="stat-card">
          <div className="flex items-center gap-4">
            <div className={`p-4 rounded-2xl shadow-lg ${
              totalReturn !== null && totalReturn >= 0 
                ? 'bg-gradient-to-br from-emerald-400 to-emerald-600' 
                : 'bg-gradient-to-br from-red-400 to-red-600'
            }`}>
              {totalReturn !== null && totalReturn >= 0 
                ? <TrendingUp className="w-7 h-7 text-white" />
                : <TrendingDown className="w-7 h-7 text-white" />
              }
            </div>
            <div>
              <p className="text-sm font-medium text-slate-500">Current Return</p>
              {loadingReturns ? (
                <div className="flex items-center gap-2">
                  <Loader2 className="w-5 h-5 animate-spin text-slate-400" />
                  <span className="text-sm text-slate-400">Fetching prices...</span>
                </div>
              ) : totalReturn !== null ? (
                <p className={`stat-value ${totalReturn >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                  {totalReturn >= 0 ? '+' : ''}{returnPct.toFixed(2)}%
                </p>
              ) : (
                <p className="stat-value text-slate-400">--</p>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Link to="/auto-builder" className="card hover:shadow-md transition-shadow group">
          <div className="flex items-start gap-4">
            <div className="p-3 bg-slate-100 rounded-lg group-hover:bg-purple-100 transition-colors">
              <Wand2 className="w-6 h-6 text-slate-600 group-hover:text-purple-600" />
            </div>
            <div className="flex-1">
              <h3 className="text-lg font-semibold text-slate-900 group-hover:text-purple-600">
                Auto Portfolio Builder
              </h3>
              <p className="text-slate-600 mt-1">
                Let Sapient automatically select the best stocks from ASX200 for maximum Sharpe ratio.
              </p>
            </div>
            <ArrowRight className="w-5 h-5 text-slate-400 group-hover:text-purple-500 group-hover:translate-x-1 transition-all" />
          </div>
        </Link>

        <Link to="/manual-builder" className="card hover:shadow-md transition-shadow group">
          <div className="flex items-start gap-4">
            <div className="p-3 bg-slate-100 rounded-lg group-hover:bg-sky-100 transition-colors">
              <Wrench className="w-6 h-6 text-slate-600 group-hover:text-sky-600" />
            </div>
            <div className="flex-1">
              <h3 className="text-lg font-semibold text-slate-900 group-hover:text-sky-600">
                Manual Portfolio Builder
              </h3>
              <p className="text-slate-600 mt-1">
                Select specific ASX stocks and optimize your portfolio with custom risk settings.
              </p>
            </div>
            <ArrowRight className="w-5 h-5 text-slate-400 group-hover:text-sky-500 group-hover:translate-x-1 transition-all" />
          </div>
        </Link>
      </div>

      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-slate-900">Active Portfolios</h2>
          <Link to="/portfolios" className="text-sky-500 hover:text-sky-600 text-sm font-medium">
            View all
          </Link>
        </div>

        {loading ? (
          <div className="flex justify-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-sky-500"></div>
          </div>
        ) : portfolios.length === 0 ? (
          <div className="text-center py-8">
            <Briefcase className="w-12 h-12 text-slate-300 mx-auto mb-3" />
            <p className="text-slate-600">No portfolios yet</p>
            <p className="text-sm text-slate-500 mt-1">
              Create your first portfolio using the builders above
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {portfolios.slice(0, 3).map((portfolio) => (
              <Link
                key={portfolio.id}
                to={`/portfolios/${portfolio.id}`}
                className="block p-4 bg-slate-50 rounded-lg hover:bg-slate-100 transition-colors"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-medium text-slate-900">{portfolio.name}</h3>
                    <p className="text-sm text-slate-500">
                      {portfolio.position_count} positions • {portfolio.risk_tolerance}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="font-medium text-slate-900">
                      ${Number(portfolio.initial_investment).toLocaleString()}
                    </p>
                    {portfolio.expected_return && (
                      <p className="text-sm text-emerald-600">
                        +{(Number(portfolio.expected_return) * 100).toFixed(1)}% expected
                      </p>
                    )}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
