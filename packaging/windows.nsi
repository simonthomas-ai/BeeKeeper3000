; Hornet3000 Wächter – Windows-Installer (NSIS 3, Unicode). Keine Administratorrechte nötig.
; Aufruf: makensis -DVERSION=1.3.0 -DSTAGE=<Ordner mit python\ und app\> -DICON=<hornet3000.ico> -DOUT=<Ausgabedatei> windows.nsi
Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"

!ifndef VERSION
  !define VERSION "1.3.0"
!endif
!define NAME "Hornet3000 Wächter"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\Hornet3000"
!define STARTMENU "$SMPROGRAMS\${NAME}"

Name "${NAME} ${VERSION}"
OutFile "${OUT}"
InstallDir "$LOCALAPPDATA\Programs\Hornet3000"
InstallDirRegKey HKCU "Software\Hornet3000" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 96
ShowInstDetails nevershow
BrandingText "Hornet3000 ${VERSION}"
Icon "${ICON}"
UninstallIcon "${ICON}"

VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=1031 "ProductName" "${NAME}"
VIAddVersionKey /LANG=1031 "FileDescription" "Installation von ${NAME}"
VIAddVersionKey /LANG=1031 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=1031 "LegalCopyright" "Enthält Software Dritter, siehe LICENSES.txt"

!define MUI_ICON "${ICON}"
!define MUI_UNICON "${ICON}"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchApp
!define MUI_FINISHPAGE_RUN_TEXT "Oberfläche jetzt öffnen (startet Hornet3000 im Hintergrund)"
!define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\app\README.txt"
!define MUI_FINISHPAGE_SHOWREADME_TEXT "Anleitung (README) anzeigen"
!define MUI_COMPONENTSPAGE_SMALLDESC

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "German"

Function LaunchApp
  SetOutPath "$INSTDIR\app"
  Exec '"$INSTDIR\python\pythonw.exe" -I "$INSTDIR\app\hornet_run.py" open'
FunctionEnd

Function StopRunning
  ${If} ${FileExists} "$INSTDIR\python\python.exe"
  ${AndIf} ${FileExists} "$INSTDIR\app\hornet_run.py"
    nsExec::Exec '"$INSTDIR\python\python.exe" -I "$INSTDIR\app\hornet_run.py" stop'
    Pop $0
    Sleep 1500
  ${EndIf}
FunctionEnd

Section "Hornet3000 Wächter (erforderlich)" SecMain
  SectionIn RO
  Call StopRunning
  ; Programmdateien ersetzen; Einstellungen (.env) und Daten (data) bleiben bei einer Aktualisierung erhalten
  RMDir /r "$INSTDIR\python"
  RMDir /r "$INSTDIR\app\lib"
  RMDir /r "$INSTDIR\app\hornet"
  RMDir /r "$INSTDIR\app\web"
  RMDir /r "$INSTDIR\app\models"
  RMDir /r "$INSTDIR\app\docs"
  SetOutPath "$INSTDIR\python"
  File /r "${STAGE}/python/*.*"
  SetOutPath "$INSTDIR\app"
  File /r "${STAGE}/app/*.*"
  SetOutPath "$INSTDIR"
  File "${ICON}"

  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\Hornet3000" "InstallDir" "$INSTDIR"

  ; Startmenü
  CreateDirectory "${STARTMENU}"
  SetOutPath "$INSTDIR\app"
  CreateShortCut "${STARTMENU}\Hornet3000 starten.lnk" "$INSTDIR\python\python.exe" '-I "$INSTDIR\app\hornet_run.py" run' "$INSTDIR\hornet3000.ico"
  CreateShortCut "${STARTMENU}\Oberfläche öffnen.lnk" "$INSTDIR\python\pythonw.exe" '-I "$INSTDIR\app\hornet_run.py" open' "$INSTDIR\hornet3000.ico"
  CreateShortCut "${STARTMENU}\Hornet3000 beenden.lnk" "$INSTDIR\python\pythonw.exe" '-I "$INSTDIR\app\hornet_run.py" stop' "$INSTDIR\hornet3000.ico"
  CreateShortCut "${STARTMENU}\Selbsttest.lnk" "$SYSDIR\cmd.exe" '/k ""$INSTDIR\python\python.exe" -I "$INSTDIR\app\hornet_run.py" selftest"' "$INSTDIR\hornet3000.ico"
  CreateShortCut "${STARTMENU}\Anleitung.lnk" "$INSTDIR\app\README.txt"
  CreateShortCut "${STARTMENU}\Deinstallieren.lnk" "$INSTDIR\Uninstall.exe"

  ; Eintrag in „Apps & Features“
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayName" "${NAME}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\hornet3000.ico"
  WriteRegStr HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "${UNINST_KEY}" "Publisher" "Hornet3000"
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1
SectionEnd

Section /o "Autostart bei Windows-Anmeldung (läuft im Hintergrund)" SecAuto
  SetOutPath "$INSTDIR\app"
  CreateShortCut "$SMSTARTUP\Hornet3000.lnk" "$INSTDIR\python\pythonw.exe" '-I "$INSTDIR\app\hornet_run.py" run' "$INSTDIR\hornet3000.ico"
SectionEnd

Section /o "Verknüpfung auf dem Desktop" SecDesk
  SetOutPath "$INSTDIR\app"
  CreateShortCut "$DESKTOP\${NAME}.lnk" "$INSTDIR\python\pythonw.exe" '-I "$INSTDIR\app\hornet_run.py" open' "$INSTDIR\hornet3000.ico"
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMain} "Programm, Python, ffmpeg und Erkennungsmodell. Keine Administratorrechte nötig."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecAuto} "Startet Hornet3000 bei jeder Anmeldung unsichtbar im Hintergrund (Protokoll: app\data\hornet.log)."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesk} "Legt eine Verknüpfung „Hornet3000 Wächter“ auf den Desktop."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Section "Uninstall"
  ${If} ${FileExists} "$INSTDIR\python\python.exe"
    nsExec::Exec '"$INSTDIR\python\python.exe" -I "$INSTDIR\app\hornet_run.py" stop'
    Pop $0
    Sleep 1500
  ${EndIf}
  Delete "$SMSTARTUP\Hornet3000.lnk"
  Delete "$DESKTOP\${NAME}.lnk"
  RMDir /r "${STARTMENU}"
  RMDir /r "$INSTDIR\python"
  RMDir /r "$INSTDIR\app\lib"
  RMDir /r "$INSTDIR\app\hornet"
  RMDir /r "$INSTDIR\app\web"
  RMDir /r "$INSTDIR\app\models"
  RMDir /r "$INSTDIR\app\docs"
  Delete "$INSTDIR\app\hornet_run.py"
  Delete "$INSTDIR\app\README.txt"
  Delete "$INSTDIR\app\LICENSES.txt"
  Delete "$INSTDIR\hornet3000.ico"
  Delete "$INSTDIR\Uninstall.exe"
  ${If} ${FileExists} "$INSTDIR\app\.env"
  ${OrIf} ${FileExists} "$INSTDIR\app\data"
    MessageBox MB_YESNO|MB_ICONQUESTION|MB_DEFBUTTON2 "Einstellungen (.env) und Aufzeichnungen (Alarme, Fotos, Videos, Protokoll) ebenfalls löschen?$\r$\n$\r$\nNein = bleiben im Ordner $INSTDIR\app erhalten." IDNO keep
    RMDir /r "$INSTDIR\app"
    keep:
  ${EndIf}
  RMDir "$INSTDIR\app"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "${UNINST_KEY}"
  DeleteRegKey HKCU "Software\Hornet3000"
SectionEnd
