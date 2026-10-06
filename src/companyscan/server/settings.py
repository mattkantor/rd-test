"""Django settings. Local: SQLite, DEBUG on. Server: set DATABASE_URL (Postgres), which turns DEBUG off by default."""
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

from jinja2 import ChainableUndefined

from .. import logs

BASE_DIR = Path.cwd()
DATABASE_URL = os.environ.get("DATABASE_URL", "")
DEBUG = os.environ.get("DJANGO_DEBUG", "0" if DATABASE_URL else "1") == "1"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or ("dev-only-insecure-key" if DEBUG else None)
if not SECRET_KEY:
    raise RuntimeError("Set DJANGO_SECRET_KEY when DEBUG is off")
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o]
if not DEBUG:  # Behind Caddy (deploy/), which terminates HTTPS and says so in X-Forwarded-Proto.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True

# Evidence bundles stay on disk; the database indexes them and tracks jobs. Same default as the CLI.
COMPANYSCAN_OUTPUT = Path(os.environ.get("COMPANYSCAN_OUTPUT", "output")).resolve()

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "huey.contrib.djhuey",
    "companyscan.web",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "companyscan.server.urls"
WSGI_APPLICATION = "companyscan.server.wsgi.application"

VIEWS = Path(__file__).resolve().parents[1] / "views"
TEMPLATES = [
    {  # The dashboard and home page: Jinja2, autoescaped. Captured bundle text is untrusted.
        "BACKEND": "django.template.backends.jinja2.Jinja2",
        "DIRS": [VIEWS / "templates"],
        "OPTIONS": {"environment": "companyscan.web.jinja.environment", "undefined": ChainableUndefined},
    },
    {  # Django admin.
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": [
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
        ]},
    },
]

if DATABASE_URL:
    db = urlsplit(DATABASE_URL)
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql", "NAME": db.path.lstrip("/"), "USER": unquote(db.username or ""),
        "PASSWORD": unquote(db.password or ""), "HOST": db.hostname or "", "PORT": db.port or "", "CONN_MAX_AGE": 60,
    }}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ponytail: SQLite-backed queue on both; bundles are on local disk anyway, so web and worker share one host.
# Use huey.RedisHuey if the worker ever moves to its own machine.
HUEY = {
    "name": "companyscan",
    "huey_class": "huey.SqliteHuey",
    "filename": os.environ.get("HUEY_DB", str(BASE_DIR / "huey.sqlite3")),
    "immediate": os.environ.get("HUEY_IMMEDIATE") == "1",
}

LOGIN_URL = "login"  # Customer sign-in; staff pages still send to the admin login.
LOGIN_REDIRECT_URL = LOGOUT_REDIRECT_URL = "/"
STATIC_URL = "static/"
STATICFILES_DIRS = [VIEWS / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
# companyscan.logs configures logging instead of Django: logs/web.log or logs/worker.log locally (warnings also on the
# terminal), stderr on a server. Django's own loggers (request errors with tracebacks) propagate into it.
LOGGING_CONFIG = None
logs.setup("worker" if "run_huey" in sys.argv else "web", console=True)
USE_TZ = True
TIME_ZONE = os.environ.get("TZ", "UTC")
