// Connection details for the local Sapient API.
// In the desktop app the Electron preload script provides window.sapient.
// In development (`run_dev.py`) Vite proxies /api and injects the token.

export type UpdateCheck =
  | { status: 'unavailable'; currentVersion: string; message: string }
  | { status: 'up-to-date'; currentVersion: string }
  | { status: 'available'; currentVersion: string; version: string; releaseDate?: string; notes?: string }

export interface UpdateProgress {
  percent: number
  transferred: number
  total: number
}

export interface SapientBridge {
  apiBase: string
  apiToken: string
  appVersion?: string
  openExternal?: (url: string) => void
  updates?: {
    check: () => Promise<UpdateCheck>
    download: () => Promise<{ downloaded: boolean }>
    install: () => void
    openReleases: () => void
    tokenStatus: () => Promise<{ configured: boolean; encryptionAvailable: boolean }>
    setToken: (token: string | null) => Promise<{ configured: boolean }>
    onProgress: (callback: (progress: UpdateProgress) => void) => () => void
  }
}

declare global {
  interface Window {
    sapient?: SapientBridge
  }
}

export const apiBase: string = window.sapient?.apiBase ?? '/api'
export const apiToken: string = window.sapient?.apiToken ?? import.meta.env.VITE_SAPIENT_API_TOKEN ?? ''
