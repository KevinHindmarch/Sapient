import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { money, portfolioApi, PortfolioSummary } from '../lib/api'
import { Portfolio } from '../types'
import { useTheme } from '../lib/theme'
import { useProfile } from '../lib/profile'
import { Briefcase, TrendingUp, TrendingDown, Wand2, Wrench, ArrowRight, Sparkles, RefreshCw } from 'lucide-react'


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
  const [loadingReturns, setLoadingReturns] = useState(false)
  const [loadingProgress, setLoadingProgress] = useState({ done: 0, total: 0 })
  const [summaries, setSummaries] = useState<PortfolioSummary[]>([])

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

  // The engine values every portfolio in one call (cash and realised profit included).
  // Australian and US portfolios are totalled separately: there is no currency conversion.
  const loadRealReturns = async (portfolioList: Portfolio[]) => {
    setLoadingReturns(true)
    setLoadingProgress({ done: 0, total: portfolioList.length })
    try {
      const response = await portfolioApi.summaries()
      setSummaries(response.data)
      setLoadingProgress({ done: portfolioList.length, total: portfolioList.length })
    } catch (error) {
      console.error('Failed to load returns:', error)
    } finally {
      setLoadingReturns(false)
    }
  }

  // One row of totals per currency that has portfolios (A$ shown when there are none at all).
  const totalsByCurrency = (['AUD', 'USD'] as const).flatMap((currency) => {
    const mine = summaries.filter((x) => x.currency === currency)
    const listed = portfolios.filter((p) => ((p.market || 'ASX') === 'US' ? 'USD' : 'AUD') === currency)
    if (!listed.length && !(currency === 'AUD' && !portfolios.length)) return []
    const putIn = mine.length ? mine.reduce((sum, x) => sum + x.money_put_in, 0)
      : listed.reduce((sum, p) => sum + Number(p.initial_investment), 0)
    const gain = mine.length ? mine.reduce((sum, x) => sum + x.total_return, 0) : null
    return [{ currency, putIn, gain, pct: gain !== null && putIn > 0 ? (gain / putIn) * 100 : null }]
  })
  const summaryFor = (id: number) => summaries.find((x) => x.portfolio_id === id)

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
          Your portfolios at a glance. Australian and US portfolios are totalled separately (A$ and US$), never converted.
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

      {totalsByCurrency.map((t) => (
        <TotalsRow key={t.currency} {...t} loading={loadingReturns} isDark={isDark}
          label={totalsByCurrency.length > 1 ? (t.currency === 'USD' ? 'US portfolios (US$)' : 'Australian portfolios (A$)') : null} />
      ))}

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
                    {(() => {
                      const sum = summaryFor(portfolio.id)
                      const currency = (portfolio.market || 'ASX') === 'US' ? 'USD' : 'AUD'
                      return (
                        <>
                          <p className={`font-medium ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                            {money(sum ? sum.total_value : Number(portfolio.initial_investment), currency, 0)}
                          </p>
                          {loadingReturns ? (
                            <SkeletonPulse className="h-3 w-20 mt-1 ml-auto" />
                          ) : sum ? (
                            <p className={`text-sm ${sum.total_return >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                              {sum.total_return >= 0 ? '+' : ''}{sum.total_return_pct.toFixed(2)}%
                              {' '}({sum.total_return >= 0 ? '+' : '-'}{money(Math.abs(sum.total_return), currency, 0)})
                            </p>
                          ) : null}
                        </>
                      )
                    })()}
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

/** Money put in, gain and return for one currency (A$ and US$ are never added together). */
function TotalsRow({ currency, putIn, gain, pct, loading, isDark, label }: {
  currency: 'AUD' | 'USD'; putIn: number; gain: number | null; pct: number | null; loading: boolean
  isDark: boolean; label: string | null
}) {
  const down = !loading && gain !== null && gain < 0
  const tone = down ? 'text-red-400' : 'text-emerald-400'
  const badge = down ? 'bg-gradient-to-br from-red-500 to-rose-600' : 'bg-gradient-to-br from-emerald-500 to-teal-600'
  const Trend = down ? TrendingDown : TrendingUp
  const muted = isDark ? 'text-slate-400' : 'text-slate-600'
  const skeleton = (
    <div className="space-y-2 mt-1">
      <SkeletonPulse className="h-8 w-28" />
      <p className={`text-xs ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>Loading live data…</p>
    </div>
  )
  const card = { boxShadow: '0 8px 32px rgba(0, 0, 0, 0.3)' }
  return (
    <div className="space-y-2" data-testid={`totals-${currency.toLowerCase()}`}>
      {label && <h2 className={`text-sm font-semibold ${muted}`}>{label}</h2>}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="stat-card" style={card}>
          <div className="flex items-center gap-4">
            <div className="p-4 bg-gradient-to-br from-sky-500 to-indigo-600 rounded-2xl shadow-lg shrink-0">
              <Briefcase className="w-7 h-7 text-white" />
            </div>
            <div className="min-w-0">
              <p className={`text-sm font-medium ${muted}`}>Money put in</p>
              <p className={`text-3xl font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>{money(putIn, currency, 0)}</p>
            </div>
          </div>
        </div>
        <div className="stat-card" style={card}>
          <div className="flex items-center gap-4">
            <div className={`p-4 rounded-2xl shadow-lg shrink-0 ${badge}`}><Trend className="w-7 h-7 text-white" /></div>
            <div className="min-w-0">
              <p className={`text-sm font-medium ${muted}`}>Total gain</p>
              {loading ? skeleton : gain !== null ? (
                <p className={`text-3xl font-bold ${tone}`}>{gain >= 0 ? '+' : '-'}{money(Math.abs(gain), currency, 0)}</p>
              ) : <p className={`text-3xl font-bold ${muted}`}>--</p>}
            </div>
          </div>
        </div>
        <div className="stat-card" style={card}>
          <div className="flex items-center gap-4">
            <div className={`p-4 rounded-2xl shadow-lg shrink-0 ${badge}`}><Trend className="w-7 h-7 text-white" /></div>
            <div className="min-w-0">
              <p className={`text-sm font-medium ${muted}`}>Return</p>
              {loading ? skeleton : pct !== null ? (
                <p className={`text-3xl font-bold ${tone}`}>{pct >= 0 ? '+' : ''}{pct.toFixed(2)}%</p>
              ) : <p className={`text-3xl font-bold ${muted}`}>--</p>}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
