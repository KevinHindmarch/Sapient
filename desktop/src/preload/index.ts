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
})

// Used only by the built-in "couldn't start" page.
contextBridge.exposeInMainWorld('sapientShell', {
  retry: () => ipcRenderer.send('sapient:retry'),
  openLogs: () => ipcRenderer.send('sapient:open-logs'),
})
