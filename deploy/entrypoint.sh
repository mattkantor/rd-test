#!/bin/sh
# web: apply migrations, then serve Django with gunicorn. worker: the Huey consumer that runs crawl and report jobs.
# Anything else runs as given, e.g. `docker compose exec web python manage.py createsuperuser`.
set -e
mkdir -p "$COMPANYSCAN_OUTPUT"
case "$1" in
  web)
    python manage.py migrate --noinput
    exec gunicorn companyscan.server.wsgi:application --bind 0.0.0.0:8000 \
      --workers "${WEB_CONCURRENCY:-2}" --timeout 120 --access-logfile - ;;
  worker)
    exec python manage.py run_huey --workers "${HUEY_WORKERS:-2}" ;;
  *)
    exec "$@" ;;
esac
