import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useAuth } from '../lib/auth'
import { useTheme } from '../lib/theme'
import { toast } from 'sonner'
import { Eye, EyeOff } from 'lucide-react'

const loginSchema = z.object({
  email: z.string().email('Invalid email address'),
  password: z.string().min(6, 'Password must be at least 6 characters'),
})

type LoginForm = z.infer<typeof loginSchema>

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const { theme } = useTheme()
  const isDark = theme === 'dark'
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
  })

  const onSubmit = async (data: LoginForm) => {
    setLoading(true)
    try {
      await login(data.email, data.password)
      toast.success('Welcome back!')
      navigate('/')
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } }
      toast.error(err.response?.data?.detail || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 relative overflow-hidden">
      <div 
        className="absolute inset-0" 
        style={{ 
          background: isDark 
            ? 'linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%)' 
            : 'linear-gradient(135deg, #f8fafc 0%, #e2e8f0 50%, #f8fafc 100%)' 
        }} 
      />
      <div className="absolute inset-0" style={{ opacity: isDark ? 0.3 : 0.15 }}>
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-sky-500/20 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-indigo-500/20 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
        <div className="absolute top-1/2 left-1/2 w-64 h-64 bg-purple-500/10 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '2s' }} />
      </div>

      <div className="w-full max-w-md relative z-10 animate-fade-in">
        <div className="text-center mb-8">
          <div className="relative inline-block">
            <img 
              src="/logo.png" 
              alt="Sapient" 
              className="w-32 h-32 mx-auto rounded-2xl"
              style={{ 
                filter: 'drop-shadow(0 0 20px rgba(56, 189, 248, 0.4))',
                animation: 'float 3s ease-in-out infinite, glow-pulse 2s ease-in-out infinite'
              }}
            />
          </div>
          <h1 className="text-4xl font-bold gradient-text mt-4">Welcome Back</h1>
          <p className={`mt-2 text-sm tracking-wide ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Smart Portfolios, Smarter Returns</p>
        </div>

        <div 
          className="rounded-2xl p-8 border animate-fade-in"
          style={{ 
            background: isDark ? 'rgba(15, 23, 42, 0.8)' : 'rgba(255, 255, 255, 0.9)',
            borderColor: isDark ? 'rgba(148, 163, 184, 0.1)' : 'rgba(148, 163, 184, 0.3)',
            backdropFilter: 'blur(24px)',
            WebkitBackdropFilter: 'blur(24px)',
            boxShadow: isDark ? '0 8px 32px rgba(0, 0, 0, 0.4)' : '0 8px 32px rgba(0, 0, 0, 0.1)',
            animationDelay: '0.2s'
          }}
        >
          <h2 className={`text-2xl font-bold mb-6 text-center ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Sign In</h2>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
            <div>
              <label className="label">Email</label>
              <input
                type="email"
                {...register('email')}
                className="input"
                placeholder="you@example.com"
              />
              {errors.email && <p className={`text-sm mt-1 ${isDark ? 'text-red-400' : 'text-red-500'}`}>{errors.email.message}</p>}
            </div>

            <div>
              <label className="label">Password</label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  {...register('password')}
                  className="input pr-12"
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className={`absolute right-3 top-1/2 -translate-y-1/2 transition-colors ${
                    isDark 
                      ? 'text-slate-400 hover:text-slate-200' 
                      : 'text-slate-500 hover:text-slate-700'
                  }`}
                >
                  {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                </button>
              </div>
              {errors.password && <p className={`text-sm mt-1 ${isDark ? 'text-red-400' : 'text-red-500'}`}>{errors.password.message}</p>}
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full py-3 text-base font-semibold"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Signing in...
                </span>
              ) : 'Sign In'}
            </button>
          </form>

          <p className={`text-center mt-6 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
            Don't have an account?{' '}
            <Link to="/register" className="text-sky-400 hover:text-sky-300 font-medium transition-colors">
              Create one
            </Link>
          </p>
        </div>
      </div>

      <style>{`
        @keyframes float {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(-10px); }
        }
      `}</style>
    </div>
  )
}
