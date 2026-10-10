import { Outlet, NavLink } from 'react-router-dom'
import logo from '../assets/logo.png'
import { useTheme } from '../lib/theme'
import { useProfile } from '../lib/profile'
import { 
  LayoutDashboard, 
  Wrench, 
  Wand2, 
  Activity,
  Briefcase, 
  LineChart, 
  Menu,
  X,
  Settings,
  Moon,
  Sun,
  HelpCircle,
  Sparkles,
  ShieldCheck,
  ClipboardList,
} from 'lucide-react'
import { useState } from 'react'
import HelpModal from './HelpModal'
import TwsStatusPill from './TwsStatusPill'

const navItems = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/manual-builder', label: 'Manual Builder', icon: Wrench },
  { path: '/auto-builder', label: 'Auto Builder', icon: Wand2 },
  { path: '/capm-builder', label: 'CAPM Builder', icon: Activity },
  { path: '/portfolios', label: 'My Portfolios', icon: Briefcase },
  { path: '/analysis', label: 'Stock Analysis', icon: LineChart },
  { path: '/ai-inbox', label: 'AI Trading', icon: Sparkles },
]

const tradingNavItems = [
  { path: '/brokerage', label: 'Brokerage', icon: ShieldCheck },
  { path: '/paper-orders', label: 'Orders', icon: ClipboardList },
  { path: '/ai-trading', label: 'AI Settings', icon: Sparkles },
]

export default function Layout() {
  const { theme, toggleTheme } = useTheme()
  const { profile } = useProfile()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [showHelp, setShowHelp] = useState(false)

  const isDark = theme === 'dark'

  return (
    <div className="min-h-screen flex">
      <aside 
        className={`hidden lg:flex lg:flex-col lg:w-72 lg:sticky lg:top-0 lg:h-screen lg:overflow-y-auto border-r transition-colors duration-300 ${
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
            <img src={logo} alt="Sapient" className="w-20 h-20 rounded-xl" />
            <h1 className="text-2xl font-bold gradient-text -ml-2">Sapient</h1>
          </div>
          <p className={`text-xs mt-1 ml-1 ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
            Smart Portfolios, Smarter Returns
          </p>
        </div>
        
        <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
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

          <div className={`my-2 border-t ${isDark ? 'border-slate-700/30' : 'border-slate-200/70'}`} />

          <button
            onClick={() => setShowHelp(true)}
            className={`flex items-center gap-3 px-4 py-3 w-full rounded-xl transition-all duration-300 ${
              isDark 
                ? 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
            }`}
          >
            <HelpCircle className="w-5 h-5" />
            Help & Glossary
          </button>
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
              {(profile?.display_name || 'S').slice(0, 1).toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <p className={`text-sm font-semibold truncate ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                {profile?.display_name || 'Local profile'}
              </p>
              <p className={`text-xs ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>Data stays on this PC</p>
            </div>
          </div>
          
          <div className="space-y-1">
            <TwsStatusPill />
            <TwsStatusPill profile="live" />
            {tradingNavItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
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
                <item.icon className="w-5 h-5" />
                {item.label}
              </NavLink>
            ))}

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
            <img src={logo} alt="Sapient" className="w-20 h-20 rounded-lg" />
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

            <div className={`my-1 border-t ${isDark ? 'border-slate-700/30' : 'border-slate-200/70'}`} />

            <button
              onClick={() => { setShowHelp(true); setMobileMenuOpen(false) }}
              className={`flex items-center gap-3 px-4 py-3 w-full rounded-xl transition-all duration-300 ${
                isDark
                  ? 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                  : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
              }`}
            >
              <HelpCircle className="w-5 h-5" />
              Help & Glossary
            </button>

            <TwsStatusPill />
            <TwsStatusPill profile="live" />
            {tradingNavItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
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
          </div>
        )}

        <main className="flex-1 p-3 sm:p-6 overflow-x-hidden overflow-y-auto">
          <Outlet />
        </main>
      </div>

      {showHelp && <HelpModal onClose={() => setShowHelp(false)} />}
    </div>
  )
}
