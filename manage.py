#!/usr/bin/env python
import os
import sys
from pathlib import Path

def load_env(path):
    """KEY=VALUE lines from .env (API keys for the web server and worker). Real environment variables win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().removeprefix("export ").partition("=")
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))  # Works without pip install -e.
    if sys.argv[1:2] != ["test"]:  # Tests stub every provider and must never see real keys.
        load_env(Path(__file__).resolve().parent / ".env")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "companyscan.server.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
