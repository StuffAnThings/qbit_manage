; Custom NSIS installer hook to set installation directory to %APPDATA%\qbit-manage
; This overrides the default installation path

!macro preInit
  ; Set the installation directory to %APPDATA%\qbit-manage
  StrCpy $INSTDIR "$APPDATA\qbit-manage"
!macroend
