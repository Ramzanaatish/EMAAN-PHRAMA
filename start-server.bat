@echo off
REM Pharma Purchase Assistant — HTML + Server launcher (v1.3.0)
REM Server (PharmaServer.exe) chalata hai, phir HTML file browser mein kholta hai.
REM Ye .bat, PharmaServer.exe aur Pharma-Purchase-Assistant.html — teeno ek hi folder mein honi chahiye.
cd /d "%~dp0"
if not exist PharmaServer.exe (
  echo PharmaServer.exe is folder mein nahi mila.
  echo Pehle GitHub Actions se PharmaServer.exe download kar ke is folder mein rakhein.
  pause
  exit /b 1
)
start "PharmaServer" /min PharmaServer.exe
timeout /t 3 /nobreak >nul
start "" "Pharma-Purchase-Assistant.html"
