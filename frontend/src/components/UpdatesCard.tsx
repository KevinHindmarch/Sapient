import { useEffect, useState } from 'react'
import { Download, RefreshCw, RotateCcw, ExternalLink, CheckCircle2, Loader2, KeyRound } from 'lucide-react'
import { toast } from 'sonner'
import type { UpdateCheck, UpdateProgress } from '../lib/runtime'

type Phase =
  | { kind: 'idle' }
  | { kind: 'checking' }
  | { kind: 'result'; check: UpdateCheck }
  | { kind: 'downloading'; version: string; progress: UpdateProgress | null }
  | { kind: 'ready'; version: string }
  | { kind: 'error'; message: string }

function megabytes(bytes: number) {
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export default function UpdatesCard() {
  const updates = window.sapient?.updates
  const version = window.sapient?.appVersion
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' })
  const [tokenConfigured, setTokenConfigured] = useState(false)
  const [tokenInput, setTokenInput] = useState('')

  useEffect(() => {
    updates?.tokenStatus().then((status) => setTokenConfigured(status.configured)).catch(() => undefined)
  }, [updates])

  const saveToken = async (value: string | null) => {
    if (!updates) return
    try {
      const result = await updates.setToken(value)
      setTokenConfigured(result.configured)
      setTokenInput('')
      toast.success(result.configured ? 'GitHub access saved on this PC' : 'GitHub access removed')
    } catch (error) {
      toast.error(String((error as Error).message ?? error).replace(/^Error invoking remote method[^:]*: (Error: )?/, ''))
    }
  }

  useEffect(() => {
    if (!updates) return
    return updates.onProgress((progress) =>
      setPhase((current) => (current.kind === 'downloading' ? { ...current, progress } : current)))
  }, [updates])

  const openReleases = () => {
    if (updates) updates.openReleases()
    else window.open('https://github.com/KevinHindmarch/Sapient/releases', '_blank', 'noopener,noreferrer')
  }

  const check = async () => {
    if (!updates) return
    setPhase({ kind: 'checking' })
    setPhase({ kind: 'result', check: await updates.check() })
  }

  const download = async (target: string) => {
    if (!updates) return
    setPhase({ kind: 'downloading', version: target, progress: null })
    try {
      await updates.download()
      setPhase({ kind: 'ready', version: target })
    } catch {
      setPhase({ kind: 'error', message: 'The download failed. Check your internet connection and try again.' })
    }
  }

  return (
    <div className="card">
      <h3 className="font-semibold theme-text mb-1">Updates</h3>
      <p className="text-sm theme-text-secondary mb-4">
        {version ? <>You have Sapient <strong>{version}</strong>. </> : null}
        Updates are only installed when you choose to. Your portfolios and settings are kept, and your database is
        backed up automatically before it is upgraded.
      </p>

      {!updates && (
        <p className="text-sm theme-text-secondary mb-3">Checking for updates works in the installed desktop app.</p>
      )}

      {phase.kind === 'result' && phase.check.status === 'up-to-date' && (
        <p className="text-sm text-emerald-600 flex items-center gap-2 mb-3">
          <CheckCircle2 className="w-4 h-4" /> You have the latest version.
        </p>
      )}
      {phase.kind === 'result' && phase.check.status === 'unavailable' && (
        <p className="text-sm text-amber-600 mb-3">{phase.check.message}</p>
      )}
      {phase.kind === 'result' && phase.check.status === 'available' && (
        <div className="mb-3 text-sm theme-text-secondary">
          <p className="theme-text font-semibold">Version {phase.check.version} is available.</p>
          {phase.check.notes && (
            <div className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap text-xs p-3 rounded-lg border theme-border">
              {phase.check.notes.replace(/<[^>]+>/g, '')}
            </div>
          )}
        </div>
      )}
      {phase.kind === 'downloading' && (
        <div className="mb-3 text-sm theme-text-secondary">
          <p>Downloading version {phase.version}… only the changed parts are fetched when possible.</p>
          <div className="mt-2 h-2 rounded-full bg-slate-500/20 overflow-hidden">
            <div className="h-full bg-sky-500 transition-all" style={{ width: `${phase.progress?.percent ?? 0}%` }} />
          </div>
          {phase.progress && (
            <p className="text-xs mt-1">{megabytes(phase.progress.transferred)} of {megabytes(phase.progress.total)}</p>
          )}
        </div>
      )}
      {phase.kind === 'ready' && (
        <p className="text-sm theme-text-secondary mb-3">
          Version {phase.version} is ready. Sapient will close, install the update and reopen.
        </p>
      )}
      {phase.kind === 'error' && <p className="text-sm text-red-600 mb-3">{phase.message}</p>}

      <div className="flex flex-wrap gap-2">
        {phase.kind === 'result' && phase.check.status === 'available' ? (
          <button className="btn-primary inline-flex items-center gap-2" onClick={() => download((phase.check as { version: string }).version)}>
            <Download className="w-4 h-4" /> Download update
          </button>
        ) : phase.kind === 'ready' ? (
          <button className="btn-primary inline-flex items-center gap-2" onClick={() => updates?.install()}>
            <RotateCcw className="w-4 h-4" /> Restart &amp; install
          </button>
        ) : (
          <button className="btn-primary inline-flex items-center gap-2" disabled={!updates || phase.kind === 'checking' || phase.kind === 'downloading'} onClick={check}>
            {phase.kind === 'checking' ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            Check for updates
          </button>
        )}
        <button className="btn-secondary inline-flex items-center gap-2" onClick={openReleases}>
          <ExternalLink className="w-4 h-4" /> Open downloads page
        </button>
      </div>

      {updates && (
        <div className="mt-6 pt-5 border-t theme-border text-sm theme-text-secondary">
          <h4 className="font-semibold theme-text flex items-center gap-2 mb-1">
            <KeyRound className="w-4 h-4" /> GitHub access {tokenConfigured ? '(saved)' : '(optional)'}
          </h4>
          <p className="mb-2">
            Not needed today. If the Sapient repository is ever made private, checking for updates needs a read-only
            GitHub access token. It is stored only on this PC, encrypted by Windows.
          </p>
          {!tokenConfigured && (
            <details className="mb-3 text-xs"><summary className="cursor-pointer">How to create a token</summary><ol className="list-decimal ml-5 space-y-1 mt-2">
              <li>On github.com open <strong>Settings → Developer settings → Personal access tokens → Fine-grained tokens</strong>.</li>
              <li>Click <strong>Generate new token</strong>; choose an expiry (e.g. 1 year).</li>
              <li>Repository access: <strong>Only select repositories → KevinHindmarch/Sapient</strong>.</li>
              <li>Permissions: <strong>Contents → Read-only</strong> (nothing else).</li>
              <li>Generate, copy the token (starts with <span className="font-mono">github_pat_</span>) and paste it here.</li>
            </ol></details>
          )}
          <div className="flex flex-wrap gap-2">
            <input
              type="password"
              autoComplete="off"
              className="input flex-1 min-w-[16rem]"
              placeholder={tokenConfigured ? 'Paste a new token to replace the saved one' : 'github_pat_…'}
              value={tokenInput}
              onChange={(event) => setTokenInput(event.target.value)}
            />
            <button className="btn-secondary" disabled={!tokenInput.trim()} onClick={() => saveToken(tokenInput.trim())}>Save</button>
            {tokenConfigured && <button className="btn-secondary" onClick={() => saveToken(null)}>Remove</button>}
          </div>
        </div>
      )}
    </div>
  )
}
