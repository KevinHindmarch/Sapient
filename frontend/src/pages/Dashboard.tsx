import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { portfolioApi } from '../lib/api'
import { Portfolio } from '../types'
import { useAuth } from '../lib/auth'
import { Briefcase, TrendingUp, Wand2, Wrench, ArrowRight } from 'lucide-react'

export default function Dashboard() {
  const { user } = useAuth()
  const [portfolios, setPortfolios] = useState<Portfolio[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadPortfolios()
  }, [])

  const loadPortfolios = async () => {
    try {
      const response = await portfolioApi.list()
      setPortfolios(response.data)
    } catch (error) {
      console.error('Failed to load portfolios:', error)
    } finally {
      setLoading(false)
    }
  }

  const totalInvestment = portfolios.reduce((sum, p) => sum + Number(p.initial_investment), 0)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-slate-900">
          Welcome back, {user?.display_name || 'Investor'}!
        </h1>
        <p className="text-slate-600 mt-1">
          Manage your ASX portfolio with intelligent optimization
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-sky-100 rounded-lg">
              <Briefcase className="w-6 h-6 text-sky-600" />
            </div>
            <div>
              <p className="text-sm text-slate-600">Total Portfolios</p>
              <p className="text-2xl font-bold text-slate-900">{portfolios.length}</p>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-emerald-100 rounded-lg">
              <TrendingUp className="w-6 h-6 text-emerald-600" />
            </div>
            <div>
              <p className="text-sm text-slate-600">Total Invested</p>
              <p className="text-2xl font-bold text-slate-900">
                ${totalInvestment.toLocaleString()}
              </p>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-purple-100 rounded-lg">
              <Wand2 className="w-6 h-6 text-purple-600" />
            </div>
            <div>
              <p className="text-sm text-slate-600">Active Positions</p>
              <p className="text-2xl font-bold text-slate-900">
                {portfolios.reduce((sum, p) => sum + (p.position_count || 0), 0)}
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
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
      </div>

      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-slate-900">Recent Portfolios</h2>
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
