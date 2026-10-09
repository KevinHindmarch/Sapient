; Sapient installer customisations (included by electron-builder's NSIS script).

; Only the installer uses this (the uninstaller is compiled from the same
; script, and an unused variable is a build error there).
!ifndef BUILD_UNINSTALLER
  Var SapientPreviousVersion
!endif

; Show the installer's step-by-step detail list instead of hiding it.
!macro customHeader
  ShowInstDetails show
  ShowUninstDetails show
!macroend

; Detect an existing installation so the user knows this is an upgrade.
!macro customInit
  StrCpy $SapientPreviousVersion ""
  !ifdef UNINSTALL_APP_KEY
    ReadRegStr $SapientPreviousVersion HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${UNINSTALL_APP_KEY}" "DisplayVersion"
  !endif
  StrCmp $SapientPreviousVersion "" sapient_fresh_install
    MessageBox MB_OK|MB_ICONINFORMATION "Sapient $SapientPreviousVersion is already installed.$\r$\n$\r$\nThis will upgrade it to version ${VERSION}. Your portfolios, settings and history are kept, and your data is backed up automatically the first time the new version starts." /SD IDOK
  sapient_fresh_install:
!macroend

!macro customInstall
  StrCmp $SapientPreviousVersion "" 0 +3
    DetailPrint "Installed: Sapient ${VERSION}"
    Goto +2
    DetailPrint "Upgraded: Sapient $SapientPreviousVersion -> ${VERSION}"
  DetailPrint "Installed: Sapient application (user interface)"
  DetailPrint "Installed: Sapient engine (Python runtime and analysis libraries)"
  DetailPrint "Created: Start menu and desktop shortcuts"
  DetailPrint "Your data is kept in: $APPDATA\Sapient"
  DetailPrint "Next: open Sapient and follow Brokerage > Set up TWS to connect Interactive Brokers."
!macroend

!macro customUnInstall
  DetailPrint "Your portfolios and settings in $APPDATA\Sapient were kept."
!macroend
