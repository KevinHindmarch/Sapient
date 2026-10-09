// Small self-contained status pages shown while the engine starts or fails.

const STYLE = `
  :root { color-scheme: light dark; --bg:#f8fafc; --fg:#0f172a; --muted:#475569; --accent:#0ea5e9; --card:#ffffff; --border:#e2e8f0; }
  @media (prefers-color-scheme: dark) { :root { --bg:#020617; --fg:#e2e8f0; --muted:#94a3b8; --card:#0f172a; --border:#1e293b; } }
  body { margin:0; height:100vh; display:flex; align-items:center; justify-content:center; background:var(--bg); color:var(--fg);
         font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
  .card { max-width:520px; padding:32px; border-radius:16px; background:var(--card); border:1px solid var(--border); text-align:center; }
  h1 { font-size:22px; margin:12px 0 8px; }
  p { color:var(--muted); line-height:1.5; margin:6px 0; }
  img { width:72px; height:72px; }
  .spinner { width:28px; height:28px; margin:18px auto 0; border:3px solid var(--border); border-top-color:var(--accent);
             border-radius:50%; animation:spin 0.9s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  button { margin:16px 6px 0; padding:10px 18px; border-radius:10px; border:1px solid var(--border); background:var(--card);
           color:var(--fg); font-size:14px; cursor:pointer; }
  button.primary { background:var(--accent); border-color:var(--accent); color:white; }
  code { font-size:12px; color:var(--muted); word-break:break-all; }
`

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)
}

function page(title: string, body: string): string {
  return `<!doctype html><html><head><meta charset="utf-8"><title>${title}</title>
<style>${STYLE}</style></head><body><div class="card">${body}</div></body></html>`
}

export function loadingPage(message: string): string {
  return page('Sapient', `<img src="app://sapient/favicon.png" alt=""><h1>Starting Sapient…</h1>
<p>${escapeHtml(message)}</p><div class="spinner"></div>`)
}

export function errorPage(message: string, logFile: string): string {
  return page('Sapient', `<img src="app://sapient/favicon.png" alt=""><h1>Sapient couldn't start</h1>
<p>${escapeHtml(message)}</p>
<p>Details are in the log file:</p><code>${escapeHtml(logFile)}</code><br>
<button class="primary" id="retry">Try again</button>
<button id="logs">Open log folder</button>
<script src="app://sapient/__shell.js"></script>`)
}

// Served as app://sapient/__shell.js (inline handlers are blocked by the CSP).
export const SHELL_SCRIPT = `
document.getElementById('retry')?.addEventListener('click', () => window.sapientShell.retry())
document.getElementById('logs')?.addEventListener('click', () => window.sapientShell.openLogs())
`
