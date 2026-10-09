# Installation and first-run setup — user experience spec

Date: 2026-10-09. Status: **design, built in migration Phases D (installer) and
E (TWS setup + connection test).** Parent plan:
[desktop-migration-plan.md](desktop-migration-plan.md).

Goal: a non-technical user can install Sapient, see exactly what is being
installed, and get Interactive Brokers Trader Workstation (TWS) connected with
clear step-by-step guidance and a one-click **Test connection**.

## 1. Windows installer (`Sapient-Setup-x.y.z.exe`)

Built with electron-builder NSIS in **assisted** mode (`oneClick: false`), per-user
(no admin rights). Everything ships inside the installer: no downloads during
install, so progress is real and the install works offline.

| Page | Content |
|---|---|
| Welcome | What Sapient is; "this installs on your PC only — your data stays here" |
| Important notice | Trading risk disclaimer; Sapient never stores your IBKR password |
| Install location | Default `%LOCALAPPDATA%\Programs\Sapient`, shows disk space needed (~500 MB) |
| Installing | Progress bar **plus a named step list** that ticks as each finishes: 1) Sapient application 2) Sapient engine (Python runtime + analysis libraries) 3) TWS connector 4) Shortcuts (Start menu, optional desktop) 5) Uninstaller. Live detail line shows the file being copied |
| Finished | "Launch Sapient" ticked; link to the setup guide |

Uninstaller asks whether to keep your data (`%APPDATA%\Sapient`: database,
backups, logs). Default: keep. Upgrades preserve data and settings.
Code-signed (open question Q4) so Windows doesn't show "unknown publisher".

## 2. First launch — setup wizard (in the app)

A full-screen guided wizard with a step tracker on the left
(✓ done / ● current / ○ to do). Every step has **Back**, **Skip for now**
where safe, and **Help** (opens the detailed guide). The wizard can be
re-opened any time from **Settings → TWS connection**.

1. **Welcome** — what the next steps are and roughly how long (10–15 minutes
   if TWS isn't installed yet).
2. **System check** (automatic, with ticks): engine started, data folder
   writable, internet reachable, Yahoo Finance reachable. Plain-language fix for
   any failure (e.g. "Your firewall may be blocking Sapient").
3. **How do you want to use Sapient?**
   - *Research only* (no broker) → finish now, IBKR can be set up later.
   - *Connect Interactive Brokers* → continue.
4. **Install Trader Workstation** — detects an existing install (`C:\Jts\…\tws.exe`)
   and a running TWS. If missing, shows the steps in §3.1 with an
   **Open IBKR download page** button (opens in the normal browser).
5. **Log in to Paper Trading** — explains paper vs live, how to pick
   *Paper Trading* on the TWS login screen, and that Sapient starts with paper only.
6. **Turn on the API in TWS** — the checklist in §3.2 with screenshots, one
   item per row, each with a "Done" tick. Recommended values are shown with
   **Copy** buttons (port `7497`, `127.0.0.1`).
7. **Install the IBKR API software** — detects `C:\TWS API\source\pythonclient`
   and its version; if missing, shows §3.3 with **Open download page**.
   (Sapient can't ship this itself because of IBKR's licence terms.)
8. **Connection settings** — prefilled: host `127.0.0.1` (fixed), port `7497`,
   client ID `71`, your paper account ID (e.g. `DU1234567`). Advanced options hidden.
9. **Test connection** — see §4. Must pass before continuing; failures show the fix.
10. **Done** — summary card: TWS build, API version, account, *TWS PAPER* badge,
    Read-Only on. Buttons: *Go to dashboard*, *Build my first portfolio*.

## 3. Guide content shown in the wizard

### 3.1 Download and install TWS
1. Click **Open IBKR download page** (interactivebrokers.com → Trading →
   Trader Workstation → Download).
2. Choose **TWS Latest** or **TWS Stable** for Windows (Sapient is tested with
   TWS 10.51; the wizard shows the exact tested build).
3. Run the downloaded installer and accept the defaults.
4. Start TWS from the Start menu.

### 3.2 Enable the API in TWS (paper session)
1. Log in and choose **Paper Trading** on the login screen.
2. Open **File → Global Configuration** (on some layouts **Edit → Global Configuration**).
3. In the left panel choose **API → Settings**.
4. Tick **Enable ActiveX and Socket Clients**.
5. Keep **Read-Only API** ticked. (Sapient only reads at this stage. You will
   be asked separately, much later, before any paper order is allowed.)
6. Set **Socket port** to **7497** (TWS default for paper; live is normally 7496).
7. Tick **Allow connections from localhost only**.
8. Leave **Master API client ID** empty.
9. Optional: tick **Create API message log file** (helps support).
10. Click **Apply**, then **OK**.
11. Recommended: **Lock and Exit** → set the daily auto-restart time to a time
    you're not trading (TWS restarts daily and needs you to log in weekly; Sapient
    will show "TWS needs you to log in" when that happens).
12. If TWS shows "Accept incoming connection?" the first time Sapient connects,
    click **Yes**.

### 3.3 Install the IBKR API software
1. Click **Open download page** (interactivebrokers.github.io).
2. Download the **Windows** installer for the version shown by Sapient
   (matched to your TWS version).
3. Run it with defaults (installs to `C:\TWS API`).
4. Back in Sapient click **Check again**.

## 4. Test connection

Runs the read-only diagnostic (based on `scripts/tws_readonly_check.py`) and shows
each stage live with ✓ / ✗ and elapsed time. No orders are ever sent.

| # | Check | If it fails, Sapient says |
|---|---|---|
| 1 | IBKR API software found and version recorded | "Install the IBKR API software (step 7)." |
| 2 | Something is listening on `127.0.0.1:<port>` | "TWS isn't running, the API isn't enabled, or the port is different. Check step 6." |
| 3 | API handshake + `nextValidId` received | "TWS refused the connection. Make sure *Enable ActiveX and Socket Clients* is ticked and click *Yes* on the TWS prompt." |
| 4 | Client ID accepted | "Another program is using client ID 71. Close it or pick another ID." (never auto-switched) |
| 5 | TWS connected to IBKR servers (no 1100) | "TWS is open but not connected to IBKR. Check your internet or log in again." |
| 6 | Exactly one managed account, matches what you entered | "TWS shows account XXX, but you entered YYY." |
| 7 | Account summary, positions, executions snapshots complete | "TWS didn't send complete account data in time. Try again." |
| 8 | Market data for one test stock (type: live/delayed) | "No market data permission for ASX/US. Delayed data will be used for checks." (warning, not failure) |
| 9 | Disconnect and reconnect cleanly | "Reconnect failed — restart TWS and test again." |

Result card: overall pass/fail, the versions and account seen, a **Copy
diagnostics** button (sanitised — no account values, no credentials) and a saved
report under `%APPDATA%\Sapient\diagnostics\`. Paper identity is still confirmed by
you (the wizard asks you to confirm TWS shows the *Paper Trading* banner), because
a port number or `DU` prefix alone doesn't prove paper.

## 5. After setup

- Status bar always shows: Sapient engine ✓, TWS connector ✓, TWS ✓,
  IBKR servers ✓, last update time, and the `SIMULATION / TWS PAPER / TWS LIVE` badge.
- Clicking any red item opens the matching wizard step and fix.
- **Settings → TWS connection**: re-run wizard, Test connection, view last report.
- Help menu: this guide, open logs folder, copy diagnostics.
