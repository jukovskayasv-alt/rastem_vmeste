#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "Нет .env. Выполни: cp .env.example .env && nano .env"
  exit 1
fi

docker compose pull
docker compose up -d --build
docker compose ps
echo
echo "Элир: https://elir.62.84.122.57.nip.io"
