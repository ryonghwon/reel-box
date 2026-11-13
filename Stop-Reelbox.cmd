@echo off
setlocal
cd /d "%~dp0"
docker compose stop
echo Reelbox stopped. Your files and history are preserved.
pause
endlocal
