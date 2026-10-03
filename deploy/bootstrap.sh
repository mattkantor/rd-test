#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu droplet (22.04/24.04), run as root: Docker, firewall, swap, the code, .env with
# generated secrets, and the running stack. Safe to re-run; it keeps an existing .env and checkout.
#
#   bootstrap.sh <git repo url> <domain>
#
# For a private repo, use an HTTPS URL with a read-only token or add a deploy key first. Point the domain's DNS A
# record at the droplet before running, so Caddy can get the HTTPS certificate.
set -euo pipefail
REPO=${1:?usage: bootstrap.sh <git repo url> <domain>}
DOMAIN=${2:?usage: bootstrap.sh <git repo url> <domain>}
DIR=${DIR:-/opt/companyscan}

apt-get update
apt-get install -y ca-certificates curl git openssl ufw
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh

ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443 && ufw --force enable

# Chromium and a crawl together can outgrow a 1-2 GB droplet; swap keeps the PDF step from being killed.
if ! swapon --show | grep -q .; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

[ -d "$DIR/.git" ] || git clone "$REPO" "$DIR"
cd "$DIR"
if [ ! -f .env ]; then
  cp env.example .env
  {
    echo "DOMAIN=$DOMAIN"
    echo "DJANGO_SECRET_KEY=$(openssl rand -hex 32)"
    echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)"
  } >> .env
  chmod 600 .env
fi
mkdir -p backups

docker compose up -d --build

cat <<MSG

Running at https://$DOMAIN (the certificate can take a minute on first start).
Next:
  1. Put your API keys in $DIR/.env, then: cd $DIR && docker compose up -d
  2. Create your staff login:            docker compose exec web python manage.py createsuperuser
Later updates:                           $DIR/deploy/update.sh
MSG
