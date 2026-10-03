#!/usr/bin/env bash
# Pull the latest code and rebuild; migrations run when the web container starts. Run on the droplet.
set -euo pipefail
cd "$(dirname "$0")/.."
git pull --ff-only
docker compose up -d --build
docker image prune -f
