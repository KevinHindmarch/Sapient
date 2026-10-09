// Connection details for the local Sapient API.
// In the desktop app the Electron preload script provides window.sapient.
// In development (`run_dev.py`) Vite proxies /api and injects the token.

export interface SapientBridge {
  apiBase: string
  apiToken: string
  appVersion?: string
  openExternal?: (url: string) => void
}

declare global {
  interface Window {
    sapient?: SapientBridge
  }
}

export const apiBase: string = window.sapient?.apiBase ?? '/api'
export const apiToken: string = window.sapient?.apiToken ?? import.meta.env.VITE_SAPIENT_API_TOKEN ?? ''
