PY ?= .venv/bin/python
MANAGE = $(PY) manage.py

.PHONY: help venv install migrate migrations superuser run worker dev test test-core scan collectstatic clean

help:  ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

venv:  ## Create .venv if missing
	test -d .venv || python3 -m venv .venv

install: venv  ## Install the package with the web extra (Django, Huey, LangChain)
	$(PY) -m pip install -e '.[web]'

migrate:  ## Apply database migrations
	$(MANAGE) migrate

migrations:  ## Create migrations after model changes
	$(MANAGE) makemigrations web

superuser:  ## Create a staff login for the UI and admin
	$(MANAGE) createsuperuser

run: migrate  ## Web server on 127.0.0.1:8000
	$(MANAGE) runserver

worker:  ## Huey worker that runs crawl and report jobs
	$(MANAGE) run_huey

dev: migrate  ## Web server and worker together (Ctrl+C stops both)
	$(MANAGE) run_huey & trap 'kill $$!' EXIT; $(MANAGE) runserver

test:  ## Full suite, including the Django web tests
	$(MANAGE) test tests --top-level-directory tests

test-core:  ## Scanner tests only, no Django needed
	PYTHONPATH=src $(PY) -m unittest discover -s tests

scan:  ## Crawl a site from the CLI: make scan URL=https://example.com
	@test -n "$(URL)" || (echo "usage: make scan URL=https://example.com" && exit 2)
	PYTHONPATH=src $(PY) -m companyscan scan $(URL)

collectstatic:  ## Gather static files for the server (WhiteNoise)
	$(MANAGE) collectstatic --noinput

clean:  ## Remove caches and build output (keeps output/ bundles and the databases)
	find . -name __pycache__ -not -path './.venv/*' -prune -exec rm -rf {} +
	rm -rf build dist staticfiles .coverage src/*.egg-info
