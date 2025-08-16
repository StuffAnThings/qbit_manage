; Custom NSIS installer hook to set installation directory to %APPDATA%\qbit-manage
; This overrides the default installation path

!macro customInit
  ; Set the installation directory to %APPDATA%\qbit-manage
  StrCpy $INSTDIR "$APPDATA\qbit-manage"
!macroend

!macro customInstall
  ; Additional custom installation logic can go here if needed
!macroend

!macro customUnInstall
  ; Custom uninstallation logic can go here if needed
!macroend
