; Show the installer's step-by-step detail list instead of hiding it.
!macro customHeader
  ShowInstDetails show
  ShowUninstDetails show
!macroend

!macro customInstall
  DetailPrint "Installed: Sapient application (user interface)"
  DetailPrint "Installed: Sapient engine (Python runtime and analysis libraries)"
  DetailPrint "Created: Start menu and desktop shortcuts"
  DetailPrint "Your data will be kept in: $APPDATA\Sapient"
  DetailPrint "Next: open Sapient and follow Brokerage > Set up TWS to connect Interactive Brokers."
!macroend

!macro customUnInstall
  DetailPrint "Your portfolios and settings in $APPDATA\Sapient were kept."
!macroend
