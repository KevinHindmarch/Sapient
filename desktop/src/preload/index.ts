// Runs in the sandboxed renderer before the UI. Exposes only what the UI needs:
// where the local engine listens, its per-launch key, and a safe link opener.

import { contextBridge, ipcRenderer } from 'electron'

const config = ipcRenderer.sendSync('sapient:config') as {
  apiBase: string
  apiToken: string
  appVersion: string
}

contextBridge.exposeInMainWorld('sapient', {
  apiBase: config.apiBase,
  apiToken: config.apiToken,
  appVersion: config.appVersion,
  openExternal: (url: string) => ipcRenderer.send('sapient:open-external', url),
  desktop: {
    settings: () => ipcRenderer.invoke('sapient:desktop-settings'),
    setCloseToTray: (value: boolean) => ipcRenderer.invoke('sapient:set-close-to-tray', value),
    setSetting: (key: 'closeToTray' | 'openAtLogin' | 'keepAwake', value: boolean) =>
      ipcRenderer.invoke('sapient:set-desktop-setting', key, value),
    emergencyStop: () => ipcRenderer.invoke('sapient:emergency-stop'),
  },
  updates: {
    check: () => ipcRenderer.invoke('sapient:update-check'),
    download: () => ipcRenderer.invoke('sapient:update-download'),
    install: () => ipcRenderer.send('sapient:update-install'),
    openReleases: () => ipcRenderer.send('sapient:open-releases'),
    tokenStatus: () => ipcRenderer.invoke('sapient:update-token-status'),
    setToken: (token: string | null) => ipcRenderer.invoke('sapient:update-set-token', token),
    onProgress: (callback: (progress: { percent: number; transferred: number; total: number }) => void) => {
      const listener = (_event: unknown, progress: { percent: number; transferred: number; total: number }) => callback(progress)
      ipcRenderer.on('sapient:update-progress', listener)
      return () => { ipcRenderer.removeListener('sapient:update-progress', listener) }
    },
  },
})

// Used only by the built-in "couldn't start" page.
contextBridge.exposeInMainWorld('sapientShell', {
  retry: () => ipcRenderer.send('sapient:retry'),
  openLogs: () => ipcRenderer.send('sapient:open-logs'),
})
