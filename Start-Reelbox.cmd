@echo off
setlocal
cd /d "%~dp0"
where docker >nul 2>nul
if errorlevel 1 (
  echo Install Docker Desktop for Windows, then run this file again.
  echo https://docs.docker.com/desktop/setup/install/windows-install/
  pause
  exit /b 1
)
docker info >nul 2>nul
if errorlevel 1 (
  echo Start Docker Desktop in Linux containers mode, then try again.
  pause
  exit /b 1
)
if not exist .env (
  powershell -NoProfile -Command "$r=[System.Security.Cryptography.RandomNumberGenerator]::Create();$b=New-Object byte[] 32;$r.GetBytes($b);$r.Dispose();$t=-join($b|ForEach-Object{$_.ToString('x2')});[IO.File]::WriteAllText('.env',('API_TOKEN='+$t+[Environment]::NewLine+'WEB_PORT=3000'+[Environment]::NewLine+'DOWNLOAD_HOST_DIR=./downloads'+[Environment]::NewLine),[Text.UTF8Encoding]::new($false))"
  if errorlevel 1 exit /b 1
)
if not exist data mkdir data
if not exist downloads mkdir downloads
docker compose up -d --build
if errorlevel 1 (
  echo Reel Box could not start. Check the error above.
  pause
  exit /b 1
)
set "REELBOX_PORT=3000"
for /f "tokens=2 delims==" %%P in ('findstr /b "WEB_PORT=" .env') do set "REELBOX_PORT=%%P"
start "" "http://localhost:%REELBOX_PORT%"
echo Reel Box is running. Use Stop-Reelbox.cmd to stop it.
endlocal
