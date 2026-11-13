#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then
  umask 077
  TOKEN=$(openssl rand -hex 32)
  printf 'API_TOKEN=%s\nWEB_PORT=3000\nDOWNLOAD_HOST_DIR=%s/downloads\n' "$TOKEN" "$(pwd)" > .env
fi
mkdir -p data downloads
printf 'Setup complete. Start Reel Box with: docker compose up --build -d\n'
