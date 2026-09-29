import { useEffect, useState, ReactNode } from 'react'
import { brokerApi, BrokerCredentialsPayload } from '../lib/api'
import { useTheme } from '../lib/theme'
import { toast } from 'sonner'
import {
  ShieldCheck,
  Lock,
  ExternalLink,
  AlertTriangle,
  RefreshCw,
  CheckCircle2,
  Loader2,
  Trash2,
  Activity,
} from 'lucide-react'

type Environment = 'paper' | 'live'

interface BrokerStatus {
  connected: boolean
  environment: Environment | null
  consumer_key_masked: string | null
  connected_at: string | null
  last_test_at: string | null
  last_test_ok: boolean | null
  sim_mode: boolean
}

interface AccountSummary {
  account_id: string
  account_alias: string
  currency: string
  environment: string
  server_time: string
  is_paper: boolean
  sim: boolean
  cash_balance?: number
  buying_power?: number
  net_liquidation?: number
  unrealized_pnl?: number
  [key: string]: unknown
}

export default function BrokerageSettings() {
  const { theme } = useTheme()
  const isDark = theme === 'dark'

  const [status, setStatus] = useState<BrokerStatus | null>(null)
  const [account, setAccount] = useState<AccountSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [testing, setTesting] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [disconnecting, setDisconnecting] = useState(false)

  const [consumerKey, setConsumerKey] = useState('')
  const [accessToken, setAccessToken] = useState('')
  const [accessTokenSecret, setAccessTokenSecret] = useState('')
  const [privateKeyPem, setPrivateKeyPem] = useState('')
  const [environment, setEnvironment] = useState<Environment>('paper')

  useEffect(() => {
    loadStatus()
  }, [])

  const loadStatus = async () => {
    setLoading(true)
    try {
      const res = await brokerApi.getStatus()
      const s: BrokerStatus = res.data
      setStatus(s)
      if (s.connected) {
        await refreshAccount()
      }
    } catch (err) {
      console.error(err)
      toast.error('Failed to load brokerage status')
    } finally {
      setLoading(false)
    }
  }

  const refreshAccount = async () => {
    setRefreshing(true)
    try {
      const res = await brokerApi.account()
      setAccount(res.data)
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } }
      toast.error(e.response?.data?.detail || 'Failed to load account')
    } finally {
      setRefreshing(false)
    }
  }

  const handleSubmit = async () => {
    if (!consumerKey || !accessToken || !accessTokenSecret || !privateKeyPem) {
      toast.error('Please fill in all credential fields')
      return
    }
    const payload: BrokerCredentialsPayload = {
      consumer_key: consumerKey.trim(),
      access_token: accessToken.trim(),
      access_token_secret: accessTokenSecret.trim(),
      private_key_pem: privateKeyPem,
      environment,
    }
    setSubmitting(true)
    try {
      await brokerApi.saveCredentials(payload)
      toast.success('IBKR credentials saved securely')
      setConsumerKey('')
      setAccessToken('')
      setAccessTokenSecret('')
      setPrivateKeyPem('')
      await loadStatus()
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } }
      toast.error(e.response?.data?.detail || 'Failed to save credentials')
    } finally {
      setSubmitting(false)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    try {
      const res = await brokerApi.test()
      if (res.data?.ok) {
        toast.success(res.data.message || 'Connection successful')
      } else {
        toast.error(res.data?.message || 'Connection test failed')
      }
      await loadStatus()
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } }
      toast.error(e.response?.data?.detail || 'Connection test failed')
    } finally {
      setTesting(false)
    }
  }

  const handleDisconnect = async () => {
    if (!confirm('Disconnect IBKR? Your encrypted credentials will be removed.')) return
    setDisconnecting(true)
    try {
      await brokerApi.deleteCredentials()
      toast.success('IBKR disconnected')
      setStatus(null)
      setAccount(null)
      await loadStatus()
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } }
      toast.error(e.response?.data?.detail || 'Failed to disconnect')
    } finally {
      setDisconnecting(false)
    }
  }

  const fmtCurrency = (n: number | undefined, ccy: string = 'AUD') => {
    if (n === undefined || n === null || isNaN(n)) return '—'
    const sym = ccy === 'AUD' ? 'A$' : ccy === 'USD' ? 'US$' : `${ccy} `
    return `${sym}${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  }

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-sky-500"></div>
      </div>
    )
  }

  const connected = status?.connected === true

  return (
    <div className="max-w-4xl mx-auto space-y-6 animate-fade-in">
      <div className="page-header">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-gradient-to-br from-sky-500/20 to-indigo-500/20 border border-sky-500/30">
            <ShieldCheck className="w-6 h-6 text-sky-500" />
          </div>
          <div>
            <h1 className="page-title">Brokerage</h1>
            <p className="page-subtitle">
              Manage your Interactive Brokers credentials. Live and paper order execution are disabled.
            </p>
          </div>
        </div>
      </div>

      <div className={`flex items-start gap-3 px-4 py-3 rounded-xl border ${
          isDark
            ? 'bg-amber-500/10 border-amber-500/30 text-amber-200'
            : 'bg-amber-50 border-amber-200 text-amber-700'
        }`}>
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <p className="text-sm">
            <span className="font-medium">Execution disabled.</span>{' '}
            Eligible simulation requests may be queued as intents, not placed or filled. Paper and live
            broker orders are blocked regardless of the selected environment.
          </p>
      </div>

      {connected && (
        <div className="card p-0 overflow-hidden">
          <div className={`p-5 border-b flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 ${
            isDark ? 'border-slate-700/50 bg-slate-800/30' : 'border-slate-200 bg-slate-50'
          }`}>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-white flex items-center justify-center shadow-md">
                <span className="text-red-600 font-bold text-[10px] tracking-tight">IBKR</span>
              </div>
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className={`font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                    {account?.account_id || status?.consumer_key_masked || '—'}
                    {' · '}
                    {(status?.environment || 'paper').toUpperCase()}
                  </h3>
                  <span className="badge badge-emerald flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                    Credentials saved
                  </span>
                </div>
                <div className={`flex items-center gap-2 mt-1 text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                  {status?.last_test_at ? (
                    <span>Last test: {new Date(status.last_test_at).toLocaleString()}</span>
                  ) : (
                    <span>Not tested yet</span>
                  )}
                  <button
                    onClick={refreshAccount}
                    disabled={refreshing}
                    className="hover:text-sky-500 transition-colors disabled:opacity-40"
                    title="Refresh data"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
                  </button>
                </div>
              </div>
            </div>
            <button
              onClick={handleTest}
              disabled={testing}
              className="btn-secondary text-sm flex items-center gap-2"
            >
              {testing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Activity className="w-4 h-4" />}
              Test Connection
            </button>
          </div>

          <div className={`grid grid-cols-2 md:grid-cols-4 gap-px ${isDark ? 'bg-white/5' : 'bg-slate-200'}`}>
            <div className={`p-5 flex flex-col justify-center ${isDark ? 'bg-slate-900/95' : 'bg-white'}`}>
              <span className={`text-xs font-medium mb-1 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Cash Balance</span>
              <span className={`text-lg font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                {fmtCurrency(account?.cash_balance, account?.currency)}
              </span>
            </div>
            <div className={`p-5 flex flex-col justify-center ${isDark ? 'bg-slate-900/95' : 'bg-white'}`}>
              <span className={`text-xs font-medium mb-1 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Buying Power</span>
              <span className={`text-lg font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                {fmtCurrency(account?.buying_power, account?.currency)}
              </span>
            </div>
            <div className={`p-5 flex flex-col justify-center ${isDark ? 'bg-slate-900/95' : 'bg-white'}`}>
              <span className={`text-xs font-medium mb-1 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Net Liquidation</span>
              <span className={`text-lg font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                {fmtCurrency(account?.net_liquidation, account?.currency)}
              </span>
            </div>
            <div className={`p-5 flex flex-col justify-center ${isDark ? 'bg-slate-900/95' : 'bg-white'}`}>
              <span className={`text-xs font-medium mb-1 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Open P/L</span>
              <span className={`text-lg font-bold ${
                (account?.unrealized_pnl || 0) >= 0 ? 'text-emerald-500' : 'text-red-500'
              }`}>
                {(account?.unrealized_pnl || 0) >= 0 ? '+' : ''}
                {fmtCurrency(account?.unrealized_pnl, account?.currency)}
              </span>
            </div>
          </div>

          <div className={`px-5 py-4 border-t flex flex-wrap items-center gap-3 ${
            isDark ? 'border-slate-700/50 bg-slate-800/20' : 'border-slate-200 bg-slate-50/50'
          }`}>
            <span className={`text-xs font-medium ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
              Execution policy:
            </span>
            <span className="text-xs theme-text-muted">Broker order placement disabled; historical broker data remains available.</span>
          </div>

          <div className={`p-5 border-t flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 ${
            isDark ? 'border-slate-700/50 bg-slate-800/30' : 'border-slate-200 bg-slate-50'
          }`}>
            <p className={`text-xs px-3 py-1.5 rounded-lg border flex items-center gap-1.5 ${
              isDark
                ? 'text-amber-300 bg-amber-500/10 border-amber-500/20'
                : 'text-amber-700 bg-amber-50 border-amber-200'
            }`}>
              <AlertTriangle className="w-3.5 h-3.5" />
              {status?.environment === 'live'
                ? 'Live credentials selected; live orders remain blocked. No real-money execution is enabled.'
                : 'Paper credentials selected; paper orders remain blocked. Simulation intents are not broker orders.'}
            </p>
            <button
              onClick={handleDisconnect}
              disabled={disconnecting}
              className="text-xs font-medium text-red-500 hover:text-red-600 transition-colors flex items-center gap-1.5"
            >
              {disconnecting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
              Disconnect IBKR
            </button>
          </div>
        </div>
      )}

      {!connected && (
        <div className="card space-y-8">
          <div>
            <h2 className={`text-lg font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
              Setup Connection
            </h2>
            <p className="text-sm theme-text-muted mt-1">
              Generate API credentials in your IBKR account, then paste them below. Everything is
              encrypted at rest with Fernet (AES-128 + HMAC).
            </p>
          </div>

          <Step number={1} title="Generate API credentials in IBKR Client Portal" isDark={isDark}>
            <p className="text-sm theme-text-muted">
              Log in to your Interactive Brokers account to create an OAuth Consumer Key, generate
              an access token, and upload an RSA public key.
            </p>
            <a
              href="https://www.interactivebrokers.com/en/index.php?f=5041"
              target="_blank"
              rel="noreferrer"
              className="btn-secondary text-sm inline-flex items-center gap-2 mt-3"
            >
              Open IBKR Client Portal
              <ExternalLink className="w-4 h-4" />
            </a>
          </Step>

          <Step number={2} title="Paste your Consumer Key" isDark={isDark}>
            <input
              value={consumerKey}
              onChange={(e) => setConsumerKey(e.target.value)}
              type="text"
              placeholder="e.g. YOUR_CONSUMER_KEY_12345"
              className="input font-mono text-sm"
            />
          </Step>

          <Step number={3} title="Paste your Access Token & Secret" isDark={isDark}>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <input
                value={accessToken}
                onChange={(e) => setAccessToken(e.target.value)}
                type="text"
                placeholder="Access Token"
                className="input font-mono text-sm"
              />
              <input
                value={accessTokenSecret}
                onChange={(e) => setAccessTokenSecret(e.target.value)}
                type="password"
                placeholder="Access Token Secret"
                className="input font-mono text-sm"
              />
            </div>
          </Step>

          <Step number={4} title="Paste your RSA private key (.pem)" isDark={isDark}>
            <textarea
              value={privateKeyPem}
              onChange={(e) => setPrivateKeyPem(e.target.value)}
              rows={6}
              placeholder={'-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----'}
              className="input font-mono text-sm resize-y"
            />
            <div className="flex items-center gap-2 text-xs font-medium text-emerald-500 mt-2">
              <Lock className="w-3.5 h-3.5" />
              <span>Encrypted at rest with Fernet. Never leaves your account.</span>
            </div>
          </Step>

          <Step number={5} title="Choose environment" isDark={isDark}>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setEnvironment('paper')}
                className={`text-left p-4 rounded-xl border transition-all ${
                  environment === 'paper'
                    ? 'border-sky-500/60 bg-sky-500/10 shadow-[0_0_15px_rgba(56,189,248,0.15)]'
                    : isDark
                      ? 'border-slate-700/50 bg-slate-800/30 hover:border-slate-600'
                      : 'border-slate-200 bg-slate-50 hover:border-slate-300'
                }`}
              >
                <div className="flex items-start justify-between mb-2">
                  <span className={`font-medium ${environment === 'paper' ? 'text-sky-500' : isDark ? 'text-slate-200' : 'text-slate-700'}`}>
                    Paper trading
                  </span>
                  <span className="badge badge-sky">Sandbox</span>
                </div>
                <p className="text-xs theme-text-muted">
                  Credential environment only. Paper broker orders remain blocked.
                </p>
              </button>

              <button
                type="button"
                onClick={() => setEnvironment('live')}
                className={`text-left p-4 rounded-xl border transition-all ${
                  environment === 'live'
                    ? 'border-amber-500/60 bg-amber-500/10 shadow-[0_0_15px_rgba(245,158,11,0.15)]'
                    : isDark
                      ? 'border-slate-700/50 bg-slate-800/30 hover:border-slate-600'
                      : 'border-slate-200 bg-slate-50 hover:border-slate-300'
                }`}
              >
                <div className="flex items-start justify-between mb-2">
                  <span className={`font-medium ${environment === 'live' ? 'text-amber-500' : isDark ? 'text-slate-200' : 'text-slate-700'}`}>
                    Live trading
                  </span>
                  <span className="badge badge-amber flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3" />
                    Blocked
                  </span>
                </div>
                <p className="text-xs theme-text-muted">
                  Live credentials do not enable real-money order execution.
                </p>
              </button>
            </div>
          </Step>

          <div className={`pt-6 mt-2 border-t flex flex-col sm:flex-row items-center gap-3 ${
            isDark ? 'border-slate-700/50' : 'border-slate-200'
          }`}>
            <button
              onClick={handleSubmit}
              disabled={submitting}
              className="btn-primary w-full sm:w-auto px-6 flex items-center gap-2"
            >
              {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
              Connect to IBKR
            </button>
            <button
              onClick={handleTest}
              disabled={testing}
              className="btn-secondary w-full sm:w-auto px-6 flex items-center gap-2"
            >
              {testing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Activity className="w-4 h-4" />}
              Test connection
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function Step({
  number,
  title,
  isDark,
  children,
}: {
  number: number
  title: string
  isDark: boolean
  children: ReactNode
}) {
  return (
    <div className="flex gap-4">
      <div className={`shrink-0 w-8 h-8 rounded-full border flex items-center justify-center text-sm font-semibold ${
        isDark
          ? 'bg-slate-800 border-slate-700 text-slate-200'
          : 'bg-slate-100 border-slate-200 text-slate-700'
      }`}>
        {number}
      </div>
      <div className="flex-1 space-y-2">
        <h3 className={`text-base font-medium ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>{title}</h3>
        {children}
      </div>
    </div>
  )
}
