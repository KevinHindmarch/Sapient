import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { useTheme } from '../lib/theme'
import { 
  LayoutDashboard, 
  Wrench, 
  Wand2, 
  Briefcase, 
  LineChart, 
  LogOut,
  Menu,
  X,
  Settings,
  Moon,
  Sun
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
  const { theme, toggleTheme } = useTheme()
  const navigate = useNavigate()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const isDark = theme === 'dark'

  return (
    <div className="min-h-screen flex">
      <aside 
        className={`hidden lg:flex lg:flex-col lg:w-72 border-r transition-colors duration-300 ${
          isDark ? 'border-slate-700/50' : 'border-slate-200'
        }`}
        style={{
          background: isDark 
            ? 'linear-gradient(180deg, rgba(15, 23, 42, 0.95) 0%, rgba(30, 27, 75, 0.9) 100%)'
            : 'linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)',
          backdropFilter: 'blur(20px)'
        }}
      >
        <div className={`p-5 border-b transition-colors duration-300 ${isDark ? 'border-slate-700/30' : 'border-slate-200/50'}`}>
          <div className="flex items-center gap-1">
            <img src="/logo.png" alt="Sapient" className="w-20 h-20 rounded-xl" />
            <h1 className="text-2xl font-bold gradient-text -ml-2">Sapient</h1>
          </div>
          <p className={`text-xs mt-1 ml-1 ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
            Smart Portfolios, Smarter Returns
          </p>
        </div>
        
        <nav className="flex-1 p-4 space-y-1">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-300 ${
                  isActive
                    ? 'bg-gradient-to-r from-sky-500/20 to-indigo-500/20 text-sky-500 border border-sky-500/30'
                    : isDark 
                      ? 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                }`
              }
              style={({ isActive }) => isActive ? { boxShadow: '0 0 20px rgba(56, 189, 248, 0.15)' } : {}}
            >
              <item.icon className="w-5 h-5" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className={`p-4 border-t transition-colors duration-300 ${isDark ? 'border-slate-700/30' : 'border-slate-200/50'}`}>
          <div 
            className="flex items-center gap-3 px-4 py-3 mb-3 rounded-xl transition-colors duration-300"
            style={{
              background: isDark ? 'rgba(56, 189, 248, 0.1)' : 'rgba(56, 189, 248, 0.05)',
              border: `1px solid ${isDark ? 'rgba(56, 189, 248, 0.2)' : 'rgba(56, 189, 248, 0.15)'}`
            }}
          >
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-sky-400 to-indigo-500 flex items-center justify-center text-sm font-bold text-white shadow-lg">
              {user?.display_name?.[0] || user?.email?.[0] || 'U'}
            </div>
            <div className="flex-1 min-w-0">
              <p className={`text-sm font-semibold truncate ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                {user?.display_name || user?.email}
              </p>
              <p className={`text-xs ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>Premium Investor</p>
            </div>
          </div>
          
          <div className="space-y-1">
            <NavLink
              to="/settings"
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-2.5 w-full rounded-xl transition-all duration-300 ${
                  isActive
                    ? 'bg-gradient-to-r from-sky-500/20 to-indigo-500/20 text-sky-500'
                    : isDark 
                      ? 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                }`
              }
            >
              <Settings className="w-5 h-5" />
              Settings
            </NavLink>
            
            <button
              onClick={toggleTheme}
              className={`flex items-center gap-3 px-4 py-2.5 w-full rounded-xl transition-all duration-300 ${
                isDark 
                  ? 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                  : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
              }`}
            >
              {isDark ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
              {isDark ? 'Light Mode' : 'Dark Mode'}
            </button>
            
            <button
              onClick={handleLogout}
              className={`flex items-center gap-3 px-4 py-2.5 w-full rounded-xl transition-all duration-300 ${
                isDark 
                  ? 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                  : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
              }`}
            >
              <LogOut className="w-5 h-5" />
              Sign Out
            </button>
          </div>
        </div>
      </aside>

      <div className="flex-1 flex flex-col">
        <header 
          className={`lg:hidden border-b px-4 py-3 flex items-center justify-between transition-colors duration-300 ${
            isDark ? 'border-slate-700/50' : 'border-slate-200'
          }`}
          style={{
            background: isDark ? 'rgba(15, 23, 42, 0.9)' : 'rgba(255, 255, 255, 0.9)',
            backdropFilter: 'blur(20px)'
          }}
        >
          <div className="flex items-center gap-3">
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className={`p-2 -ml-2 transition-colors ${isDark ? 'text-slate-400 hover:text-slate-200' : 'text-slate-600 hover:text-slate-900'}`}
            >
              {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
            </button>
            <img src="/logo.png" alt="Sapient" className="w-20 h-20 rounded-lg" />
            <h1 className="text-xl font-bold gradient-text -ml-4">Sapient</h1>
          </div>
          <button
            onClick={toggleTheme}
            className={`p-2 rounded-lg transition-colors ${isDark ? 'text-slate-400 hover:text-slate-200 hover:bg-slate-800' : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'}`}
          >
            {isDark ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
          </button>
        </header>

        {mobileMenuOpen && (
          <div 
            className={`lg:hidden border-b px-4 py-3 transition-colors duration-300 ${isDark ? 'border-slate-700/50' : 'border-slate-200'}`}
            style={{
              background: isDark ? 'rgba(15, 23, 42, 0.95)' : 'rgba(255, 255, 255, 0.95)',
              backdropFilter: 'blur(20px)'
            }}
          >
            {navItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.path === '/'}
                onClick={() => setMobileMenuOpen(false)}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-300 ${
                    isActive
                      ? 'bg-gradient-to-r from-sky-500/20 to-indigo-500/20 text-sky-500'
                      : isDark
                        ? 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                        : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                  }`
                }
              >
                <item.icon className="w-5 h-5" />
                {item.label}
              </NavLink>
            ))}
            <NavLink
              to="/settings"
              onClick={() => setMobileMenuOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-300 ${
                  isActive
                    ? 'bg-gradient-to-r from-sky-500/20 to-indigo-500/20 text-sky-500'
                    : isDark
                      ? 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                }`
              }
            >
              <Settings className="w-5 h-5" />
              Settings
            </NavLink>
            <button
              onClick={handleLogout}
              className={`flex items-center gap-3 px-4 py-3 w-full rounded-xl transition-all ${
                isDark
                  ? 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                  : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
              }`}
            >
              <LogOut className="w-5 h-5" />
              Sign Out
            </button>
          </div>
        )}

        <main className="flex-1 p-6 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
