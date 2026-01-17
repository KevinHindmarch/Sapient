import { useTheme } from '../lib/theme'
import { useAuth } from '../lib/auth'
import { Moon, Sun, User, Palette } from 'lucide-react'

export default function Settings() {
  const { theme, setTheme } = useTheme()
  const { user } = useAuth()

  return (
    <div className="max-w-2xl mx-auto space-y-6 animate-fade-in">
      <div className="page-header">
        <h1 className="page-title">Settings</h1>
        <p className="page-subtitle">Customize your Sapient experience</p>
      </div>

      <div className="card">
        <div className="flex items-center gap-3 mb-6 pb-6 border-b theme-border">
          <div className="p-3 rounded-xl bg-gradient-to-br from-sky-500/20 to-indigo-500/20 border border-sky-500/30">
            <User className="w-6 h-6 text-sky-500" />
          </div>
          <div>
            <h2 className="text-lg font-semibold theme-text">Profile</h2>
            <p className="text-sm theme-text-secondary">{user?.email}</p>
          </div>
        </div>

        <div className="space-y-6">
          <div>
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 rounded-lg bg-gradient-to-br from-purple-500/20 to-pink-500/20 border border-purple-500/30">
                <Palette className="w-5 h-5 text-purple-500" />
              </div>
              <div>
                <h3 className="font-semibold theme-text">Appearance</h3>
                <p className="text-sm theme-text-muted">Choose your preferred theme</p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <button
                onClick={() => setTheme('light')}
                className={`p-4 rounded-xl border-2 transition-all duration-300 ${
                  theme === 'light'
                    ? 'border-sky-500 bg-sky-500/10'
                    : 'border-transparent hover:border-sky-500/30'
                }`}
                style={{
                  background: theme === 'light' ? 'rgba(56, 189, 248, 0.1)' : 'var(--bg-card)',
                  boxShadow: theme === 'light' ? 'var(--glow-sky)' : 'none'
                }}
              >
                <div className="flex flex-col items-center gap-3">
                  <div className={`p-4 rounded-xl ${
                    theme === 'light' 
                      ? 'bg-gradient-to-br from-amber-400 to-orange-500' 
                      : 'bg-slate-200 dark:bg-slate-700'
                  }`}>
                    <Sun className={`w-6 h-6 ${theme === 'light' ? 'text-white' : 'text-slate-400'}`} />
                  </div>
                  <div className="text-center">
                    <p className={`font-semibold ${theme === 'light' ? 'text-sky-600 dark:text-sky-400' : 'theme-text-secondary'}`}>
                      Light Mode
                    </p>
                    <p className="text-xs theme-text-muted mt-1">Clean & bright</p>
                  </div>
                  {theme === 'light' && (
                    <span className="badge-sky text-xs">Active</span>
                  )}
                </div>
              </button>

              <button
                onClick={() => setTheme('dark')}
                className={`p-4 rounded-xl border-2 transition-all duration-300 ${
                  theme === 'dark'
                    ? 'border-indigo-500 bg-indigo-500/10'
                    : 'border-transparent hover:border-indigo-500/30'
                }`}
                style={{
                  background: theme === 'dark' ? 'rgba(99, 102, 241, 0.1)' : 'var(--bg-card)',
                  boxShadow: theme === 'dark' ? 'var(--glow-purple)' : 'none'
                }}
              >
                <div className="flex flex-col items-center gap-3">
                  <div className={`p-4 rounded-xl ${
                    theme === 'dark' 
                      ? 'bg-gradient-to-br from-indigo-500 to-purple-600' 
                      : 'bg-slate-200 dark:bg-slate-700'
                  }`}>
                    <Moon className={`w-6 h-6 ${theme === 'dark' ? 'text-white' : 'text-slate-400'}`} />
                  </div>
                  <div className="text-center">
                    <p className={`font-semibold ${theme === 'dark' ? 'text-indigo-400' : 'theme-text-secondary'}`}>
                      Dark Mode
                    </p>
                    <p className="text-xs theme-text-muted mt-1">Premium & sleek</p>
                  </div>
                  {theme === 'dark' && (
                    <span className="badge-purple text-xs">Active</span>
                  )}
                </div>
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <h3 className="font-semibold theme-text mb-2">About Sapient</h3>
        <p className="text-sm theme-text-secondary mb-4">
          Smart Portfolios, Smarter Returns. Sapient uses Modern Portfolio Theory to optimize your ASX investments for maximum risk-adjusted returns.
        </p>
        <div className="flex items-center gap-2 text-xs theme-text-muted">
          <span>Version 2.0</span>
          <span>•</span>
          <span>Premium Edition</span>
        </div>
      </div>
    </div>
  )
}
