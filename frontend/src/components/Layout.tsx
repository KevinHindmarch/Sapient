import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { 
  LayoutDashboard, 
  Wrench, 
  Wand2, 
  Briefcase, 
  LineChart, 
  LogOut,
  Menu,
  X
} from 'lucide-react'
import { useState } from 'react'

const navItems = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/manual-builder', label: 'Manual Builder', icon: Wrench },
  { path: '/auto-builder', label: 'Auto Builder', icon: Wand2 },
  { path: '/portfolios', label: 'My Portfolios', icon: Briefcase },
  { path: '/analysis', label: 'Stock Analysis', icon: LineChart },
]

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="min-h-screen flex">
      <aside className="hidden lg:flex lg:flex-col lg:w-64 bg-gradient-to-b from-slate-900 via-slate-900 to-slate-800 text-white">
        <div className="p-4 border-b border-slate-700/50">
          <div className="flex items-center gap-0.5">
            <img src="/logo.png" alt="Sapient" className="w-24 h-24 rounded-xl -mr-2" />
            <h1 className="text-2xl font-bold bg-gradient-to-r from-sky-400 to-cyan-300 bg-clip-text text-transparent">Sapient</h1>
          </div>
        </div>
        
        <nav className="flex-1 p-4 space-y-1">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                  isActive
                    ? 'bg-sky-500 text-white'
                    : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                }`
              }
            >
              <item.icon className="w-5 h-5" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="p-4 border-t border-slate-700/50">
          <div className="flex items-center gap-3 px-4 py-3 mb-2 bg-slate-800/50 rounded-xl">
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-sky-400 to-cyan-500 flex items-center justify-center text-sm font-bold shadow-lg">
              {user?.display_name?.[0] || user?.email?.[0] || 'U'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold truncate text-white">{user?.display_name || user?.email}</p>
              <p className="text-xs text-slate-400">Investor</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="flex items-center gap-3 px-4 py-2 w-full text-slate-300 hover:bg-slate-800 hover:text-white rounded-lg transition-colors"
          >
            <LogOut className="w-5 h-5" />
            Sign Out
          </button>
        </div>
      </aside>

      <div className="flex-1 flex flex-col">
        <header className="lg:hidden bg-white border-b border-slate-200 px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="p-2 -ml-2 text-slate-600"
            >
              {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
            </button>
            <img src="/logo.png" alt="Sapient" className="w-9 h-9 rounded" />
            <h1 className="text-xl font-bold text-sky-500 -ml-1">Sapient</h1>
          </div>
        </header>

        {mobileMenuOpen && (
          <div className="lg:hidden bg-white border-b border-slate-200 px-4 py-2">
            {navItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.path === '/'}
                onClick={() => setMobileMenuOpen(false)}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                    isActive
                      ? 'bg-sky-50 text-sky-600'
                      : 'text-slate-600 hover:bg-slate-50'
                  }`
                }
              >
                <item.icon className="w-5 h-5" />
                {item.label}
              </NavLink>
            ))}
            <button
              onClick={handleLogout}
              className="flex items-center gap-3 px-4 py-3 w-full text-slate-600 hover:bg-slate-50 rounded-lg"
            >
              <LogOut className="w-5 h-5" />
              Sign Out
            </button>
          </div>
        )}

        <main className="flex-1 p-6 bg-slate-50 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
