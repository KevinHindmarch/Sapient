import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { portfolioApi, stocksApi } from '../lib/api'
import { Portfolio, Position } from '../types'
import { useAuth } from '../lib/auth'
import { Briefcase, TrendingUp, TrendingDown, Wand2, Wrench, ArrowRight, Loader2, Sparkles } from 'lucide-react'

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
    <div className="space-y-6 animate-fade-in">
      <div className="page-header">
        <div className="flex items-center gap-2">
          <Sparkles className="w-8 h-8 text-sky-400" />
          <h1 className="page-title">
            Welcome back, <span className="gradient-text">{user?.display_name || 'Investor'}</span>!
          </h1>
        </div>
        <p className="page-subtitle">
          Manage your ASX portfolio with intelligent optimization
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="stat-card group hover:border-sky-500/30 transition-all duration-300" style={{ boxShadow: '0 8px 32px rgba(0, 0, 0, 0.3)' }}>
          <div className="flex items-center gap-4">
            <div className="p-4 bg-gradient-to-br from-sky-500 to-indigo-600 rounded-2xl shadow-lg" style={{ boxShadow: '0 0 20px rgba(56, 189, 248, 0.3)' }}>
              <Briefcase className="w-7 h-7 text-white" />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-400">Total Invested</p>
              <p className="text-3xl font-bold text-slate-100">
                ${totalInvestment.toLocaleString()}
              </p>
            </div>
          </div>
        </div>

        <div className="stat-card group hover:border-emerald-500/30 transition-all duration-300" style={{ boxShadow: '0 8px 32px rgba(0, 0, 0, 0.3)' }}>
          <div className="flex items-center gap-4">
            <div className={`p-4 rounded-2xl shadow-lg ${
              totalReturn !== null && totalReturn >= 0 
                ? 'bg-gradient-to-br from-emerald-500 to-teal-600' 
                : 'bg-gradient-to-br from-red-500 to-rose-600'
            }`} style={{ boxShadow: totalReturn !== null && totalReturn >= 0 ? '0 0 20px rgba(52, 211, 153, 0.3)' : '0 0 20px rgba(248, 113, 113, 0.3)' }}>
              {totalReturn !== null && totalReturn >= 0 
                ? <TrendingUp className="w-7 h-7 text-white" />
                : <TrendingDown className="w-7 h-7 text-white" />
              }
            </div>
            <div>
              <p className="text-sm font-medium text-slate-400">Total Gain</p>
              {loadingReturns ? (
                <div className="flex items-center gap-2">
                  <Loader2 className="w-5 h-5 animate-spin text-slate-500" />
                  <span className="text-sm text-slate-500">Calculating...</span>
                </div>
              ) : totalReturn !== null ? (
                <p className={`text-3xl font-bold ${totalReturn >= 0 ? 'text-emerald-400' : 'text-red-400'}`} style={{ textShadow: totalReturn >= 0 ? '0 0 10px rgba(52, 211, 153, 0.3)' : '0 0 10px rgba(248, 113, 113, 0.3)' }}>
                  {totalReturn >= 0 ? '+' : ''}${Math.abs(Math.round(totalReturn)).toLocaleString()}
                </p>
              ) : (
                <p className="text-3xl font-bold text-slate-500">$0</p>
              )}
            </div>
          </div>
        </div>

        <div className="stat-card group hover:border-emerald-500/30 transition-all duration-300" style={{ boxShadow: '0 8px 32px rgba(0, 0, 0, 0.3)' }}>
          <div className="flex items-center gap-4">
            <div className={`p-4 rounded-2xl shadow-lg ${
              totalReturn !== null && totalReturn >= 0 
                ? 'bg-gradient-to-br from-emerald-500 to-teal-600' 
                : 'bg-gradient-to-br from-red-500 to-rose-600'
            }`} style={{ boxShadow: totalReturn !== null && totalReturn >= 0 ? '0 0 20px rgba(52, 211, 153, 0.3)' : '0 0 20px rgba(248, 113, 113, 0.3)' }}>
              {totalReturn !== null && totalReturn >= 0 
                ? <TrendingUp className="w-7 h-7 text-white" />
                : <TrendingDown className="w-7 h-7 text-white" />
              }
            </div>
            <div>
              <p className="text-sm font-medium text-slate-400">Current Return</p>
              {loadingReturns ? (
                <div className="flex items-center gap-2">
                  <Loader2 className="w-5 h-5 animate-spin text-slate-500" />
                  <span className="text-sm text-slate-500">Fetching prices...</span>
                </div>
              ) : totalReturn !== null ? (
                <p className={`text-3xl font-bold ${totalReturn >= 0 ? 'text-emerald-400' : 'text-red-400'}`} style={{ textShadow: totalReturn >= 0 ? '0 0 10px rgba(52, 211, 153, 0.3)' : '0 0 10px rgba(248, 113, 113, 0.3)' }}>
                  {totalReturn >= 0 ? '+' : ''}{returnPct.toFixed(2)}%
                </p>
              ) : (
                <p className="text-3xl font-bold text-slate-500">--</p>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Link to="/auto-builder" className="card card-hover group">
          <div className="flex items-start gap-4">
            <div className="p-3 bg-gradient-to-br from-purple-500/20 to-indigo-500/20 rounded-xl border border-purple-500/30 group-hover:border-purple-400/50 transition-colors" style={{ boxShadow: '0 0 15px rgba(168, 85, 247, 0.2)' }}>
              <Wand2 className="w-6 h-6 text-purple-400" />
            </div>
            <div className="flex-1">
              <h3 className="text-lg font-semibold text-slate-100 group-hover:text-purple-300 transition-colors">
                Auto Portfolio Builder
              </h3>
              <p className="text-slate-400 mt-1">
                Let Sapient automatically select the best stocks from ASX200 for maximum Sharpe ratio.
              </p>
            </div>
            <ArrowRight className="w-5 h-5 text-slate-500 group-hover:text-purple-400 group-hover:translate-x-1 transition-all" />
          </div>
        </Link>

        <Link to="/manual-builder" className="card card-hover group">
          <div className="flex items-start gap-4">
            <div className="p-3 bg-gradient-to-br from-sky-500/20 to-cyan-500/20 rounded-xl border border-sky-500/30 group-hover:border-sky-400/50 transition-colors" style={{ boxShadow: '0 0 15px rgba(56, 189, 248, 0.2)' }}>
              <Wrench className="w-6 h-6 text-sky-400" />
            </div>
            <div className="flex-1">
              <h3 className="text-lg font-semibold text-slate-100 group-hover:text-sky-300 transition-colors">
                Manual Portfolio Builder
              </h3>
              <p className="text-slate-400 mt-1">
                Select specific ASX stocks and optimize your portfolio with custom risk settings.
              </p>
            </div>
            <ArrowRight className="w-5 h-5 text-slate-500 group-hover:text-sky-400 group-hover:translate-x-1 transition-all" />
          </div>
        </Link>
      </div>

      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-slate-100">Active Portfolios</h2>
          <Link to="/portfolios" className="text-sky-400 hover:text-sky-300 text-sm font-medium transition-colors">
            View all
          </Link>
        </div>

        {loading ? (
          <div className="flex justify-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-2 border-sky-500/30 border-t-sky-500"></div>
          </div>
        ) : portfolios.length === 0 ? (
          <div className="text-center py-8">
            <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-slate-800/50 flex items-center justify-center">
              <Briefcase className="w-8 h-8 text-slate-600" />
            </div>
            <p className="text-slate-400">No portfolios yet</p>
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
                className="block p-4 rounded-xl transition-all duration-300 border border-slate-700/50 hover:border-sky-500/30"
                style={{
                  background: 'rgba(30, 41, 59, 0.5)',
                }}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-medium text-slate-100">{portfolio.name}</h3>
                    <p className="text-sm text-slate-500">
                      {portfolio.position_count} positions • {portfolio.risk_tolerance}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="font-medium text-slate-100">
                      ${Number(portfolio.initial_investment).toLocaleString()}
                    </p>
                    {portfolio.expected_return && (
                      <p className="text-sm text-emerald-400">
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
