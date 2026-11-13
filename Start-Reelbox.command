#!/bin/sh
set -eu
cd "$(dirname "$0")"
if ! docker info >/dev/null 2>&1; then
  printf 'Docker Desktop을 먼저 실행한 뒤 다시 열어 주세요.\n'
  read -r answer
  exit 1
fi
sh scripts/setup.sh
docker compose up -d --build
REELBOX_PORT=$(sed -n 's/^WEB_PORT=//p' .env)
printf '\n브라우저에서 http://localhost:%s 를 여세요.\n' "${REELBOX_PORT:-3000}"
