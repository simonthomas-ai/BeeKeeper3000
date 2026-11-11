@echo off
rem Hornet3000 Update auf 1.2.0 (Windows): startet update.py mit dem Python der Installation.
rem Eigener Ordner:  Update-Windows.bat "D:\Pfad\zur\Installation"   (Ordner mit "python" und "app")
cd /d "%~dp0"
set "T=%~1"
if "%T%"=="" set "T=%LOCALAPPDATA%\Programs\Hornet3000"
if not exist "%T%\python\python.exe" (
  echo Keine Hornet3000-Installation gefunden in "%T%".
  echo Ordner angeben:  Update-Windows.bat "D:\Pfad\zur\Installation"
  pause
  exit /b 2
)
"%T%\python\python.exe" update.py --target "%T%"
pause
