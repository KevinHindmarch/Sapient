# Sapient

Portfolio research and optimisation for ASX and US shares, running entirely on
your Windows PC, with an Interactive Brokers (TWS) connection being added step
by step behind safety checks. Personal app for Kevin and family.

## Install

1. Open the [Releases page](https://github.com/KevinHindmarch/Sapient/releases)
   (sign in to GitHub — the repository is private).
2. Under the newest release, download **`Sapient-Setup-x.y.z.exe`**.
3. Run it. Windows may show **"Windows protected your PC"** because the app is
   not code-signed: click **More info → Run anyway**.
4. Follow the installer (it shows each step), then open **Sapient** from the
   Start menu or desktop.
5. To connect Interactive Brokers later, open **Brokerage** in Sapient and follow
   the TWS setup steps.

Your data (portfolios, settings, history) lives in `%APPDATA%\Sapient` on your
PC only. Uninstalling keeps it.

## Update

Either:

- **In Sapient:** Settings → Updates → **Check for updates** → **Download update**
  → **Restart & install**. Only the changed parts are downloaded when possible.
  Because the repository is private, paste a read-only GitHub token once
  (instructions are on that screen).
- **Or by hand:** download the newer `Sapient-Setup-x.y.z.exe` from Releases and
  run it. It detects the installed version and upgrades it in place, keeping
  your data. Sapient backs up its database before upgrading it.

## Publish a new version (Kevin)

GitHub → **Actions → Release → Run workflow**, type the new version (for example
`0.2.0`, higher than the last one) and optional notes. The workflow runs the
tests, builds the installer, installs and checks it on Windows, then publishes
the release.

## For developers

See [CLAUDE.md](CLAUDE.md) for the architecture, commands and safety rules, and
[docs/](docs/) for the migration plan, trading workflow and IBKR design.
