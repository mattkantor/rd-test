"""Jinja2 environment for the home page and dashboard templates."""
from datetime import datetime
from urllib.parse import quote

from django.conf import settings
from django.templatetags.static import static
from jinja2 import Environment

from . import dashboard


def local_time(when):
    try:
        when = datetime.fromisoformat(when) if isinstance(when, str) else when
        return when.astimezone().strftime("%Y-%m-%d %H:%M")
    except (AttributeError, TypeError, ValueError):  # Tampered manifests can hold null or numbers here.
        return "?"


def file_url(path):
    # Relative to the unresolved root: bundle paths are built from it (macOS /var is a symlink).
    return "/files/" + quote(path.relative_to(settings.COMPANYSCAN_OUTPUT).as_posix())


def environment(**options):
    env = Environment(**options)
    env.globals["static"] = static
    env.filters.update(local_time=local_time, file_url=file_url, href=dashboard.link, badge=dashboard.badge)
    return env
