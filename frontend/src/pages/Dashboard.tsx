import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { portfolioApi, stocksApi } from '../lib/api'
import { Portfolio, Position } from '../types'
import { useTheme } from '../lib/theme'
import { useProfile } from '../lib/profile'
import { Briefcase, TrendingUp, TrendingDown, Wand2, Wrench, ArrowRight, Sparkles, RefreshCw } from 'lucide-react'

interface PortfolioWithPositions {
  portfolio: Portfolio
  positions: Position[]
}

function SkeletonPulse({ className }: { className?: string }) {
  return (
    <div className={`animate-pulse rounded-lg bg-slate-500/20 ${className ?? ''}`} />
  )
}

export default function Dashboard() {
  const { profile } = useProfile()
  const { theme } = useTheme()
  const isDark = theme === 'dark'
  const [portfolios, setPortfolios] = useState<Portfolio[]>([])
  const [loading, setLoading] = useState(true)
  const [totalReturn, setTotalReturn] = useState<number | null>(null)
  const [totalCurrentValue, setTotalCurrentValue] = useState<number>(0)
  const [loadingReturns, setLoadingReturns] = useState(false)
  const [loadingProgress, setLoadingProgress] = useState({ done: 0, total: 0 })

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

    // Count total symbols for progress tracking
    let totalSymbols = 0
    for (const p of portfolioList) {
      try {
        const detail = await portfolioApi.detail(p.id)
        const positions = detail.data.positions as Position[]
        totalSymbols += positions.filter(pos => pos.status === 'active').length
      } catch { /* ignore */ }
    }
    setLoadingProgress({ done: 0, total: totalSymbols })

    try {
      let allInvestment = 0
      let allCurrentValue = 0
      let symbolsDone = 0

      for (const p of portfolioList) {
        const detail = await portfolioApi.detail(p.id)
        const positions = detail.data.positions as Position[]
        allInvestment += Number(p.initial_investment)

        const activePositions = positions.filter(pos => pos.status === 'active')
        const prices: Record<string, number> = {}

        for (const pos of activePositions) {
          try {
            const info = await stocksApi.info(pos.symbol)
            prices[pos.symbol] = info.data.current_price
          } catch {
            prices[pos.symbol] = 0
          }
          symbolsDone++
          setLoadingProgress({ done: symbolsDone, total: totalSymbols })
        }

        const portfolioValue = activePositions.reduce((sum, pos) => {
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
            Welcome back, <span className="gradient-text">{profile?.display_name || 'Investor'}</span>!
          </h1>
        </div>
        <p className="page-subtitle">
          Manage your ASX portfolio with intelligent optimization
        </p>
      </div>

      {/* Live price loading banner */}
      {loadingReturns && (
        <div className={`flex items-center gap-3 px-4 py-3 rounded-xl border ${
          isDark
            ? 'bg-sky-500/10 border-sky-500/30 text-sky-300'
            : 'bg-sky-50 border-sky-200 text-sky-700'
        }`}>
          <RefreshCw className="w-4 h-4 animate-spin shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium">Fetching live prices…</p>
            {loadingProgress.total > 0 && (
              <div className="flex items-center gap-2 mt-1">
                <div className={`flex-1 h-1.5 rounded-full ${isDark ? 'bg-slate-700' : 'bg-sky-100'}`}>
                  <div
                    className="h-1.5 rounded-full bg-gradient-to-r from-sky-500 to-indigo-500 transition-all duration-500"
                    style={{ width: `${(loadingProgress.done / loadingProgress.total) * 100}%` }}
                  />
                </div>
                <span className="text-xs shrink-0 tabular-nums">
                  {loadingProgress.done} / {loadingProgress.total}
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Total Invested */}
        <div className="stat-card group hover:border-sky-500/30 transition-all duration-300" style={{ boxShadow: '0 8px 32px rgba(0, 0, 0, 0.3)' }}>
          <div className="flex items-center gap-4">
            <div className="p-4 bg-gradient-to-br from-sky-500 to-indigo-600 rounded-2xl shadow-lg shrink-0" style={{ boxShadow: '0 0 20px rgba(56, 189, 248, 0.3)' }}>
              <Briefcase className="w-7 h-7 text-white" />
            </div>
            <div className="min-w-0">
              <p className={`text-sm font-medium ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Total Invested</p>
              <p className={`text-3xl font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                ${totalInvestment.toLocaleString()}
              </p>
            </div>
          </div>
        </div>

        {/* Total Gain */}
        <div className="stat-card group hover:border-emerald-500/30 transition-all duration-300" style={{ boxShadow: '0 8px 32px rgba(0, 0, 0, 0.3)' }}>
          <div className="flex items-center gap-4">
            <div className={`p-4 rounded-2xl shadow-lg shrink-0 ${
              !loadingReturns && totalReturn !== null && totalReturn < 0
                ? 'bg-gradient-to-br from-red-500 to-rose-600'
                : 'bg-gradient-to-br from-emerald-500 to-teal-600'
            }`} style={{ boxShadow: !loadingReturns && totalReturn !== null && totalReturn < 0 ? '0 0 20px rgba(248, 113, 113, 0.3)' : '0 0 20px rgba(52, 211, 153, 0.3)' }}>
              {!loadingReturns && totalReturn !== null && totalReturn < 0
                ? <TrendingDown className="w-7 h-7 text-white" />
                : <TrendingUp className="w-7 h-7 text-white" />
              }
            </div>
            <div className="min-w-0">
              <p className={`text-sm font-medium ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Total Gain</p>
              {loadingReturns ? (
                <div className="space-y-2 mt-1">
                  <SkeletonPulse className="h-8 w-28" />
                  <p className={`text-xs ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>Loading live data…</p>
                </div>
              ) : totalReturn !== null ? (
                <p className={`text-3xl font-bold ${totalReturn >= 0 ? 'text-emerald-400' : 'text-red-400'}`}
                  style={{ textShadow: totalReturn >= 0 ? '0 0 10px rgba(52, 211, 153, 0.3)' : '0 0 10px rgba(248, 113, 113, 0.3)' }}>
                  {totalReturn >= 0 ? '+' : ''}${Math.abs(Math.round(totalReturn)).toLocaleString()}
                </p>
              ) : (
                <p className={`text-3xl font-bold ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>$0</p>
              )}
            </div>
          </div>
        </div>

        {/* Current Return % */}
        <div className="stat-card group hover:border-emerald-500/30 transition-all duration-300" style={{ boxShadow: '0 8px 32px rgba(0, 0, 0, 0.3)' }}>
          <div className="flex items-center gap-4">
            <div className={`p-4 rounded-2xl shadow-lg shrink-0 ${
              !loadingReturns && totalReturn !== null && totalReturn < 0
                ? 'bg-gradient-to-br from-red-500 to-rose-600'
                : 'bg-gradient-to-br from-emerald-500 to-teal-600'
            }`} style={{ boxShadow: !loadingReturns && totalReturn !== null && totalReturn < 0 ? '0 0 20px rgba(248, 113, 113, 0.3)' : '0 0 20px rgba(52, 211, 153, 0.3)' }}>
              {!loadingReturns && totalReturn !== null && totalReturn < 0
                ? <TrendingDown className="w-7 h-7 text-white" />
                : <TrendingUp className="w-7 h-7 text-white" />
              }
            </div>
            <div className="min-w-0">
              <p className={`text-sm font-medium ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Current Return</p>
              {loadingReturns ? (
                <div className="space-y-2 mt-1">
                  <SkeletonPulse className="h-8 w-20" />
                  <p className={`text-xs ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>Loading live data…</p>
                </div>
              ) : totalReturn !== null ? (
                <p className={`text-3xl font-bold ${totalReturn >= 0 ? 'text-emerald-400' : 'text-red-400'}`}
                  style={{ textShadow: totalReturn >= 0 ? '0 0 10px rgba(52, 211, 153, 0.3)' : '0 0 10px rgba(248, 113, 113, 0.3)' }}>
                  {totalReturn >= 0 ? '+' : ''}{returnPct.toFixed(2)}%
                </p>
              ) : (
                <p className={`text-3xl font-bold ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>--</p>
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
              <h3 className={`text-lg font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'} group-hover:text-purple-300 transition-colors`}>
                Auto Portfolio Builder
              </h3>
              <p className={`${isDark ? 'text-slate-400' : 'text-slate-600'} mt-1`}>
                Let Sapient automatically select the best stocks from ASX200 for maximum Sharpe ratio.
              </p>
            </div>
            <ArrowRight className={`w-5 h-5 ${isDark ? 'text-slate-500' : 'text-slate-500'} group-hover:text-purple-400 group-hover:translate-x-1 transition-all`} />
          </div>
        </Link>

        <Link to="/manual-builder" className="card card-hover group">
          <div className="flex items-start gap-4">
            <div className="p-3 bg-gradient-to-br from-sky-500/20 to-cyan-500/20 rounded-xl border border-sky-500/30 group-hover:border-sky-400/50 transition-colors" style={{ boxShadow: '0 0 15px rgba(56, 189, 248, 0.2)' }}>
              <Wrench className="w-6 h-6 text-sky-400" />
            </div>
            <div className="flex-1">
              <h3 className={`text-lg font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'} group-hover:text-sky-300 transition-colors`}>
                Manual Portfolio Builder
              </h3>
              <p className={`${isDark ? 'text-slate-400' : 'text-slate-600'} mt-1`}>
                Select specific ASX stocks and optimise your portfolio with custom risk settings.
              </p>
            </div>
            <ArrowRight className={`w-5 h-5 ${isDark ? 'text-slate-500' : 'text-slate-500'} group-hover:text-sky-400 group-hover:translate-x-1 transition-all`} />
          </div>
        </Link>
      </div>

      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <h2 className={`text-xl font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Active Portfolios</h2>
            {loadingReturns && (
              <span className={`inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border ${
                isDark
                  ? 'bg-sky-500/10 border-sky-500/30 text-sky-400'
                  : 'bg-sky-50 border-sky-200 text-sky-600'
              }`}>
                <RefreshCw className="w-3 h-3 animate-spin" />
                Refreshing
              </span>
            )}
          </div>
          <Link to="/portfolios" className="text-sky-600 dark:text-sky-400 hover:text-sky-700 dark:hover:text-sky-300 text-sm font-medium transition-colors">
            View all
          </Link>
        </div>

        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map(i => (
              <div key={i} className={`p-4 rounded-xl border ${isDark ? 'border-slate-700/50' : 'border-slate-200'}`}>
                <div className="flex items-center justify-between">
                  <div className="space-y-2">
                    <SkeletonPulse className="h-4 w-36" />
                    <SkeletonPulse className="h-3 w-24" />
                  </div>
                  <div className="space-y-2 items-end flex flex-col">
                    <SkeletonPulse className="h-4 w-20" />
                    <SkeletonPulse className="h-3 w-16" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : portfolios.length === 0 ? (
          <div className="text-center py-8">
            <div className={`w-16 h-16 mx-auto mb-4 rounded-2xl ${isDark ? 'bg-slate-800/50' : 'bg-slate-100'} flex items-center justify-center`}>
              <Briefcase className="w-8 h-8 text-slate-600" />
            </div>
            <p className={`${isDark ? 'text-slate-400' : 'text-slate-600'}`}>No portfolios yet</p>
            <p className={`text-sm ${isDark ? 'text-slate-500' : 'text-slate-500'} mt-1`}>
              Create your first portfolio using the builders above
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {portfolios.slice(0, 3).map((portfolio) => (
              <Link
                key={portfolio.id}
                to={`/portfolios/${portfolio.id}`}
                className={`block p-4 rounded-xl transition-all duration-300 border ${isDark ? 'border-slate-700/50' : 'border-slate-200'} hover:border-sky-500/30`}
                style={{ background: isDark ? 'rgba(30, 41, 59, 0.5)' : 'rgba(241, 245, 249, 0.8)' }}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <h3 className={`font-medium truncate ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>{portfolio.name}</h3>
                    <p className={`text-sm ${isDark ? 'text-slate-500' : 'text-slate-500'}`}>
                      {portfolio.position_count} positions • {portfolio.risk_tolerance}
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className={`font-medium ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                      ${Number(portfolio.initial_investment).toLocaleString()}
                    </p>
                    {loadingReturns ? (
                      <SkeletonPulse className="h-3 w-20 mt-1 ml-auto" />
                    ) : portfolio.expected_return ? (
                      <p className="text-sm text-emerald-400">
                        +{(Number(portfolio.expected_return) * 100).toFixed(1)}% expected
                      </p>
                    ) : null}
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
