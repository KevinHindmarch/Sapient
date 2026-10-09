// Manual updates from GitHub Releases. Nothing is checked or downloaded unless
// the user asks: Settings → Updates → Check → Download → Restart & install.
// electron-updater fetches only the changed blocks of the new installer when
// it can (blockmap differential download), otherwise the whole installer.

import { app, BrowserWindow, ipcMain, safeStorage } from 'electron'
import { autoUpdater, ProgressInfo, UpdateInfo } from 'electron-updater'
import fs from 'node:fs'
import path from 'node:path'

export const RELEASES_URL = 'https://github.com/KevinHindmarch/Sapient/releases'
const OWNER = 'KevinHindmarch'
const REPO = 'Sapient'
// GitHub personal access tokens: classic (ghp_) or fine-grained (github_pat_).
const TOKEN_PATTERN = /^(ghp_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})$/

// The repository is public today, so no token is needed. If it is made private,
// downloads need a read-only GitHub token: stored only on this PC, encrypted
// with Windows DPAPI (Electron safeStorage), never sent to the UI or engine.
function tokenFile(): string {
  return path.join(app.getPath('userData'), 'github-update-token.bin')
}

function loadToken(): string | null {
  try {
    if (!safeStorage.isEncryptionAvailable() || !fs.existsSync(tokenFile())) return null
    return safeStorage.decryptString(fs.readFileSync(tokenFile()))
  } catch {
    return null
  }
}

function applyFeed(token: string | null): void {
  if (token) {
    autoUpdater.setFeedURL({ provider: 'github', owner: OWNER, repo: REPO, private: true, token })
  } else {
    autoUpdater.setFeedURL({ provider: 'github', owner: OWNER, repo: REPO })
  }
}

export type UpdateCheck =
  | { status: 'unavailable'; currentVersion: string; message: string }
  | { status: 'up-to-date'; currentVersion: string }
  | { status: 'available'; currentVersion: string; version: string; releaseDate?: string; notes?: string }

function notesText(info: UpdateInfo): string | undefined {
  const notes = info.releaseNotes
  if (!notes) return undefined
  if (typeof notes === 'string') return notes
  return notes.map((n) => n.note ?? '').join('\n')
}

export function registerUpdater(getWindow: () => BrowserWindow | null, logDir: string): void {
  autoUpdater.autoDownload = false
  autoUpdater.autoInstallOnAppQuit = false
  autoUpdater.allowPrerelease = false
  autoUpdater.allowDowngrade = false
  const logFile = path.join(logDir, 'updates.log')
  const log = (level: string) => (message: unknown) => {
    fs.mkdirSync(logDir, { recursive: true })
    fs.appendFileSync(logFile, `[${new Date().toISOString()}] ${level} ${String(message)}\n`)
  }
  autoUpdater.logger = { info: log('info'), warn: log('warn'), error: log('error'), debug: () => undefined }

  if (app.isPackaged) applyFeed(loadToken())

  ipcMain.handle('sapient:update-token-status', () => ({
    configured: loadToken() !== null,
    encryptionAvailable: safeStorage.isEncryptionAvailable(),
  }))

  ipcMain.handle('sapient:update-set-token', (_event, token: unknown) => {
    if (token === null) {
      fs.rmSync(tokenFile(), { force: true })
      if (app.isPackaged) applyFeed(null)
      return { configured: false }
    }
    if (typeof token !== 'string' || !TOKEN_PATTERN.test(token.trim())) {
      throw new Error('That does not look like a GitHub access token.')
    }
    if (!safeStorage.isEncryptionAvailable()) {
      throw new Error('Secure storage is not available on this PC.')
    }
    fs.mkdirSync(path.dirname(tokenFile()), { recursive: true })
    fs.writeFileSync(tokenFile(), safeStorage.encryptString(token.trim()))
    if (app.isPackaged) applyFeed(token.trim())
    return { configured: true }
  })

  autoUpdater.on('download-progress', (progress: ProgressInfo) => {
    getWindow()?.webContents.send('sapient:update-progress', {
      percent: progress.percent, transferred: progress.transferred, total: progress.total,
    })
  })

  ipcMain.handle('sapient:update-check', async (): Promise<UpdateCheck> => {
    const currentVersion = app.getVersion()
    if (!app.isPackaged) {
      return { status: 'unavailable', currentVersion, message: 'Updates are only available in the installed app.' }
    }
    try {
      const result = await autoUpdater.checkForUpdates()
      const info = result?.updateInfo
      if (!result || !info || !result.isUpdateAvailable) return { status: 'up-to-date', currentVersion }
      return { status: 'available', currentVersion, version: info.version, releaseDate: info.releaseDate, notes: notesText(info) }
    } catch (error) {
      log('error')(error)
      const text = String(error)
      if (/\b(401|403|404)\b/.test(text)) {
        return {
          status: 'unavailable', currentVersion,
          message: loadToken()
            ? 'GitHub refused the access token. It may have expired: create a new one and save it below.'
            : 'GitHub did not allow the update check. If the Sapient repository is private, add a GitHub access token below.',
        }
      }
      return { status: 'unavailable', currentVersion, message: 'Could not reach GitHub to check for updates. Check your internet connection.' }
    }
  })

  ipcMain.handle('sapient:update-download', async () => {
    await autoUpdater.downloadUpdate()
    return { downloaded: true }
  })

  ipcMain.on('sapient:update-install', () => {
    // Runs the downloaded installer, which upgrades in place and keeps your data.
    autoUpdater.quitAndInstall(false, true)
  })
}
