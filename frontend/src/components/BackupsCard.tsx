import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { DatabaseBackup, AlertTriangle } from 'lucide-react'
import { apiErrorMessage, backupsApi, BackupsInfo } from '../lib/api'

// Settings → Backups: Sapient backs the database up once a day (after checking it is healthy)
// and can put any backup back the next time it starts.
export default function BackupsCard() {
  const [info, setInfo] = useState<BackupsInfo | null>(null)
  const [busy, setBusy] = useState(false)
  const load = () => backupsApi.list().then((res) => setInfo(res.data)).catch(() => setInfo(null))
  useEffect(() => { void load() }, [])
  if (!info) return null

  const run = async (action: () => Promise<unknown>, done: string) => {
    setBusy(true)
    try {
      await action()
      toast.success(done)
      await load()
    } catch (err) {
      toast.error(apiErrorMessage(err, 'That did not work'))
    } finally {
      setBusy(false)
    }
  }
  const when = (iso?: string) => (iso ? new Date(iso).toLocaleString() : 'never')

  return (
    <div className="card space-y-3" data-testid="backups-card">
      <div className="flex items-start gap-3">
        <div className="p-2 rounded-lg bg-gradient-to-br from-sky-500/20 to-indigo-500/20 border border-sky-500/30">
          <DatabaseBackup className="w-5 h-5 text-sky-500" />
        </div>
        <div className="flex-1">
          <h3 className="font-semibold theme-text">Backups</h3>
          <p className="text-sm theme-text-secondary mt-1">
            Sapient checks its database and keeps a copy every day (the last 7 days, plus a copy before each
            update). Last backup: <strong>{when(info.status.last_backup_at)}</strong>.
          </p>
          {info.status.last_check_ok === false && (
            <p className="text-sm text-red-600 flex items-center gap-2 mt-2"><AlertTriangle className="w-4 h-4" />
              The last check found a problem ({info.status.last_check_detail}). Restore a backup below.</p>
          )}
          {info.pending_restore && (
            <p className="text-sm text-amber-600 mt-2">
              {info.pending_restore.backup} will be restored the next time Sapient starts (quit and reopen it).{' '}
              <button className="underline" disabled={busy}
                onClick={() => run(() => backupsApi.cancelRestore(), 'Restore cancelled')}>Cancel</button>
            </p>
          )}
        </div>
      </div>
      <button className="btn-secondary text-sm" disabled={busy}
        onClick={() => run(() => backupsApi.now(), 'Backup made')}>Back up now</button>
      {info.backups.length > 0 && (
        <ul className="text-sm divide-y theme-border max-h-56 overflow-y-auto">
          {info.backups.map((b) => (
            <li key={b.name} className="py-2 flex items-center justify-between gap-2">
              <span className="theme-text">{new Date(b.modified_at).toLocaleString()}
                <span className="theme-text-secondary"> · {b.kind} · {(b.size / 1024 / 1024).toFixed(1)} MB</span></span>
              <button className="text-xs underline theme-text-secondary" disabled={busy}
                onClick={() => run(() => backupsApi.restore(b.name),
                  'Quit Sapient (tray → Quit) and open it again to restore this backup')}>
                Restore this
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
