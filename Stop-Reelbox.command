#!/bin/sh
set -eu
cd "$(dirname "$0")"
docker compose stop
printf '종료했습니다. 파일과 작업 기록은 유지됩니다.\n'
