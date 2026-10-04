# Deploy plan: DigitalOcean droplet

How to put the app (web UI, job worker, database, HTTPS) on one DigitalOcean droplet with Docker Compose. Everything
it needs is in the repo: `Dockerfile`, `docker-compose.yml`, `deploy/` (`bootstrap.sh`, `update.sh`, `entrypoint.sh`,
`Caddyfile`). The stack was built and run end to end locally on 2026-10-03: HTTPS, login page, static files, a job
queued by the web app and run by the worker, and the nightly backup all worked.

## What runs on the droplet

| Service | What it does | Data kept in |
|---|---|---|
| `db` | Postgres 16 | `pgdata` volume |
| `web` | Django under gunicorn; applies migrations on every start | `data` volume (shared) |
| `worker` | Huey: crawl, report and re-crawl jobs | `data` volume (shared) |
| `caddy` | HTTPS for your domain (Let's Encrypt, renews itself), proxies to `web` | `caddy_data` volume |
| `backup` | `pg_dump` every 24 hours to `./backups`, keeps 14 days | `/opt/companyscan/backups` |

Web and worker share the `data` volume: the evidence bundles (`/data/output`) and the job queue (`/data/huey.sqlite3`)
must be on one host. On the server, logs go to `docker compose logs`, not to `logs/`.

## Before you start (checklist)

- [ ] **GitHub login works on your Mac.** `gh auth login -h github.com -p https -w` in a normal terminal (not `!` in
      Claude Code, which times out), then `gh auth setup-git`.
- [ ] **Everything you want live is committed and pushed.** `git status` is clean (or only holds work you're keeping
      back), then `git push origin main`. The droplet clones from GitHub, so uncommitted work won't be there.
- [ ] **A domain or subdomain** for the app, e.g. `app.obviouschoice.systems`.
- [ ] **Repo access for the droplet.** If the repo is private, create a fine-grained GitHub token with read-only
      "Contents" access to this one repo (or a deploy key). You'll use it once in the clone URL.
- [ ] **API keys at hand:** `OPENAI_API_KEY` (reports and AI checks), `GOOGLE_PLACES_API_KEY` (Google listing),
      `JEV_API_KEY` (Jev copy check), `META_ACCESS_TOKEN` (Meta ads, optional). Only the checks you use need a key.

## Steps

1. **Create the droplet.** Ubuntu 24.04 LTS, Basic plan, **2 GB RAM / 1 vCPU or more** (about $12/month; Chromium and
   a crawl together need the memory; the bootstrap also adds 2 GB swap). Pick the region nearest you, add your SSH
   key, and note the droplet's public IP.

2. **Point DNS at it.** At your DNS provider, add an `A` record for your domain → the droplet's IP. Wait until
   `dig +short app.example.com` returns that IP; Caddy needs it to get the certificate.

3. **Run the bootstrap** (as root on the droplet):
   ```sh
   ssh root@<droplet-ip>
   curl -fsSL https://raw.githubusercontent.com/mattkantor/rd-test/main/deploy/bootstrap.sh -o bootstrap.sh
   bash bootstrap.sh https://github.com/mattkantor/rd-test.git app.example.com
   ```
   For a private repo, `raw.githubusercontent.com` needs the token too, so either copy `deploy/bootstrap.sh` over
   with `scp`, or clone first and run it from the checkout:
   ```sh
   git clone https://<token>@github.com/mattkantor/rd-test.git /opt/companyscan
   bash /opt/companyscan/deploy/bootstrap.sh - app.example.com
   ```
   It installs Docker, opens ports 22/80/443 (ufw), adds swap, writes `/opt/companyscan/.env` with a generated
   `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD`, and starts the stack. The first build takes a few minutes.

4. **Add your API keys** to `/opt/companyscan/.env` (it starts from `env.example`), then restart:
   ```sh
   cd /opt/companyscan && nano .env && docker compose up -d
   ```
   Optional settings there: `COMPANYSCAN_SERVICE_NAME` / `_PITCH` / `_CTA` (scorecard copy),
   `COMPANYSCAN_LOG_LEVEL=DEBUG`, `WEB_CONCURRENCY` and `HUEY_WORKERS` (default 2 each).

5. **Create your staff login:**
   ```sh
   docker compose exec web python manage.py createsuperuser
   ```

6. **Bring your existing data over (optional).** The server starts empty. To carry over crawls you already have,
   copy bundles into the shared volume; the app indexes them on the next page load:
   ```sh
   # on your Mac
   tar -czf bundles.tgz -C output .
   scp bundles.tgz root@<droplet-ip>:/opt/companyscan/
   # on the droplet
   cd /opt/companyscan && docker compose cp bundles.tgz worker:/tmp/ \
     && docker compose exec worker sh -c 'tar -xzf /tmp/bundles.tgz -C /data/output'
   ```
   Site profiles (ICP, LTV, question sets) live in the database; re-enter them in the UI, or ask for a one-off
   export/import script.

## Check it works

- [ ] `https://app.example.com` loads with a valid certificate and redirects to the login page.
- [ ] You can log in, add a site and start a crawl; the job finishes (watch `docker compose logs -f worker`).
- [ ] **Generate report** works (needs `OPENAI_API_KEY`) and the PDF and **Customer scorecard** download (Chromium).
- [ ] **Fix pack (.zip)** downloads.
- [ ] Next morning: `ls /opt/companyscan/backups` shows a `companyscan-<date>.sql.gz`.

## Running it

| Task | Command (in `/opt/companyscan`) |
|---|---|
| Deploy new code | `deploy/update.sh` (pull, rebuild, restart; migrations run on start) |
| Follow logs | `docker compose logs -f web worker` |
| Every failure with its trace | `docker compose logs worker web 2>&1 \| grep -A30 'ERROR\|CRITICAL'` |
| Status | `docker compose ps` |
| CLI scan on the server | `docker compose exec worker companyscan scan https://example.com` |
| Django shell | `docker compose exec web python manage.py shell` |
| Restart one service | `docker compose restart worker` |
| Restore a backup | `gunzip -c backups/companyscan-<date>.sql.gz \| docker compose exec -T db psql -U companyscan companyscan` |

Backups cover the database only. The evidence bundles live in the `data` volume; turn on DigitalOcean's droplet
backups (weekly, +20% of the droplet price) or snapshot the droplet before risky changes to cover them too.

## Rolling back

Code: `git log --oneline` on the droplet, `git checkout <good commit>`, then `docker compose up -d --build`. Return to
normal with `git checkout main && deploy/update.sh`. A migration that already ran stays applied; restore the
database from `backups/` if a release changed data badly.

## Troubleshooting

- **No HTTPS / certificate errors:** DNS doesn't point at the droplet yet, or ports 80/443 are closed.
  `docker compose logs caddy` says which. Fix DNS, then `docker compose restart caddy`.
- **"Bad Request (400)":** `DOMAIN` in `.env` doesn't match the address you're visiting.
- **CSRF failure on login:** visit over `https://` on the exact `DOMAIN`.
- **PDF or scorecard fails:** `docker compose logs worker` shows the Chrome or pandoc error. Out of memory shows as
  Chrome exiting: resize the droplet to 4 GB.
- **A check reports "Set ... to enable":** the key is missing from `.env`; add it and `docker compose up -d`.
- **Job stuck "running":** the worker was restarted mid-job. Set the job to error in `/admin/`, then start it again.

## Later, if it outgrows one droplet

The queue is SQLite on the shared volume, so web and worker must stay together. To split them across machines, switch
Huey to Redis (`huey.RedisHuey` in `server/settings.py`), move bundles to shared storage (e.g. DigitalOcean Spaces),
and the database to DigitalOcean Managed Postgres (`DATABASE_URL`).
