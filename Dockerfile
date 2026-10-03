# One image for the web app and the Huey worker (docker-compose.yml): Python, pandoc and Chromium for the PDFs,
# gunicorn for Django. Everything that must survive a rebuild lives in /data (a volume).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=companyscan.server.settings \
    CHROME=/usr/bin/chromium CHROME_ARGS="--no-sandbox --disable-dev-shm-usage" \
    COMPANYSCAN_OUTPUT=/data/output HUEY_DB=/data/huey.sqlite3

RUN apt-get update \
    && apt-get install -y --no-install-recommends pandoc chromium fonts-liberation fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install '.[web]' gunicorn
COPY manage.py ./
COPY deploy/entrypoint.sh /entrypoint.sh

# Static files are baked into the image; the dummy values only let settings load at build time.
RUN mkdir -p /data \
    && DJANGO_SECRET_KEY=build DATABASE_URL=postgres://build/build HUEY_DB=/tmp/build-huey.sqlite3 \
       python manage.py collectstatic --noinput \
    && useradd --create-home app && chown app /data && chmod +x /entrypoint.sh && rm -f /tmp/build-huey.sqlite3*
USER app

ENTRYPOINT ["/entrypoint.sh"]
CMD ["web"]
