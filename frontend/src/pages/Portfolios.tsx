import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { portfolioApi } from '../lib/api'
import { Portfolio } from '../types'
import { Briefcase, ArrowRight, Calendar, TrendingUp, Shield } from 'lucide-react'
import { format } from 'date-fns'

export default function Portfolios() {
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

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-sky-500"></div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">My Portfolios</h1>
          <p className="text-slate-600 mt-1">Track and manage your optimized portfolios</p>
        </div>
        <Link to="/auto-builder" className="btn-primary flex items-center gap-2">
          <TrendingUp className="w-5 h-5" />
          New Portfolio
        </Link>
      </div>

      {portfolios.length === 0 ? (
        <div className="card text-center py-12">
          <Briefcase className="w-16 h-16 text-slate-300 mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-slate-900">No portfolios yet</h2>
          <p className="text-slate-600 mt-2 max-w-md mx-auto">
            Create your first portfolio using the Manual or Auto Portfolio Builder to start tracking your investments.
          </p>
          <div className="flex gap-4 justify-center mt-6">
            <Link to="/manual-builder" className="btn-secondary">
              Manual Builder
            </Link>
            <Link to="/auto-builder" className="btn-primary">
              Auto Builder
            </Link>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {portfolios.map((portfolio) => (
            <Link
              key={portfolio.id}
              to={`/portfolios/${portfolio.id}`}
              className="card hover:shadow-md transition-shadow group"
            >
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h3 className="text-lg font-semibold text-slate-900 group-hover:text-sky-600">
                    {portfolio.name}
                  </h3>
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
                  </div>
                </div>
                <ArrowRight className="w-5 h-5 text-slate-400 group-hover:text-sky-500 group-hover:translate-x-1 transition-all" />
              </div>

              <div className="space-y-3">
                <div className="flex items-center gap-3 text-sm">
                  <div className="p-2 bg-slate-100 rounded">
                    <Briefcase className="w-4 h-4 text-slate-600" />
                  </div>
                  <div>
                    <p className="text-slate-500">Investment</p>
                    <p className="font-medium text-slate-900">
                      ${Number(portfolio.initial_investment).toLocaleString()}
                    </p>
                  </div>
                </div>

                {portfolio.expected_return && (
                  <div className="flex items-center gap-3 text-sm">
                    <div className="p-2 bg-emerald-100 rounded">
                      <TrendingUp className="w-4 h-4 text-emerald-600" />
                    </div>
                    <div>
                      <p className="text-slate-500">Expected Return</p>
                      <p className="font-medium text-emerald-600">
                        +{(Number(portfolio.expected_return) * 100).toFixed(1)}%
                      </p>
                    </div>
                  </div>
                )}

                {portfolio.expected_sharpe && (
                  <div className="flex items-center gap-3 text-sm">
                    <div className="p-2 bg-sky-100 rounded">
                      <Shield className="w-4 h-4 text-sky-600" />
                    </div>
                    <div>
                      <p className="text-slate-500">Sharpe Ratio</p>
                      <p className="font-medium text-sky-600">
                        {Number(portfolio.expected_sharpe).toFixed(2)}
                      </p>
                    </div>
                  </div>
                )}

                <div className="flex items-center gap-3 text-sm">
                  <div className="p-2 bg-slate-100 rounded">
                    <Calendar className="w-4 h-4 text-slate-600" />
                  </div>
                  <div>
                    <p className="text-slate-500">Created</p>
                    <p className="font-medium text-slate-900">
                      {format(new Date(portfolio.created_at), 'MMM d, yyyy')}
                    </p>
                  </div>
                </div>
              </div>

              <div className="mt-4 pt-4 border-t border-slate-100 text-sm text-slate-500">
                {portfolio.position_count} positions
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
