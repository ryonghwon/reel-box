@echo off
setlocal
cd /d "%~dp0"
docker compose stop
echo Reel Box stopped. Your files and history are preserved.
pause
endlocal
