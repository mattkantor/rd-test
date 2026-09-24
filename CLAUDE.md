# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`companyscan` (package `company-footprint`) is a deterministic, dependency-free Python 3.10+ CLI that crawls a public company website into a checksummed evidence bundle. Interpretation is done by the `footprint-analyze` skill (`src/companyscan/skills/`, symlinked into `.agents/skills/` for agent discovery), never by the scanner. README.md is the authoritative user doc (CLI flags, bundle layout, dimensions, V1 boundaries); keep it in sync when behavior changes.

## Commands

```sh
. .venv/bin/activate && python -m pip install -e '.[web]'      # extras: web (FastAPI UI), llm (LangChain reputation)
PYTHONPATH=src python3 -m companyscan scan https://example.com --json   # run without installing
companyscan serve                                              # local UI on 127.0.0.1:8765

# Tests (stdlib unittest; web tests skip unless FastAPI is installed, so use the venv python)
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest tests.test_companyscan.ScannerTests.<test_name>   # single test (run from repo root with PYTHONPATH=src if not installed)
```

No linter or formatter is configured.

## Architecture

- **Pipeline** (`cli.py` `run()`): config validation → discovery (robots/sitemaps) → bounded same-origin crawl (`scan/crawler.py` `Client`, `Robots`) → per-page extraction, copy scores, accessibility → technical reports → optional dimensions → `scan/artifacts.py` `write_bundle()` writes all files and `manifest.json` with SHA-256 hashes. Every subcommand (`scan`, `discover`, `crawl`, `technical`, `social`, `accessibility`, `batch`) goes through this same `run()` and writes a full bundle; they differ only in what the JSON result returns.
- **Output contract**: output dirs must be empty — evidence is never overwritten; reruns use a new timestamped `output/<host>-<YYYYMMDD-HHMMSS>/`. Exit codes: 0 complete, 1 `PARTIAL` (usable), 2 invalid invocation/output failure. With `--json`, stdout is always exactly one JSON object, including errors. Anything added to a bundle after the fact must be registered in the manifest (path, media type, bytes, SHA-256).
- **Dimensions** (`dimensions/`): optional evidence modules with `collect(client, discovery, pages, brand) -> dict`, registered in `DIMENSIONS` in `dimensions/__init__.py`, saved as `technical/<name>.json`. Each needs a matching judgment rubric at `src/companyscan/skills/footprint-analyze/references/<name>.md` listed in step 7b of that skill. `llm_reputation` and the standalone `reputation` command share the LangChain flow in `dimensions/reputation.py`; buyer questions run in a thread pool (`WORKERS`).
- **LLM** (`llm.py`): every model call goes through `chat_model()` (lazy LangChain import); models come from `COMPANYSCAN_REPORT_MODEL` / `COMPANYSCAN_REPUTATION_MODEL`, defaulting to OpenAI and needing `OPENAI_API_KEY`. Tests stub `chat_model`; they never call a provider.
- **Report** (`report/`): `analyze.py` verifies bundle hashes, builds a budgeted `digest()` of the bundle, sends it with SKILL.md + rubrics as one JSON-mode call, and writes `analysis/report.md` + `analysis.json` itself (the model gets no tools; captured page text is untrusted). `pdf.py` renders the newest `analysis/**/report.md` via pandoc + headless Chrome using `views/report/report.css`.
- **Web** (`web/`): FastAPI app with no database — the site list and dashboards are read straight from bundles in `output/`; job progress is in memory only (`jobs.py`). `dashboard.py` builds the per-run view; all captured text must be rendered escaped. The app binds to localhost, enforces `TrustedHostMiddleware`, and rejects cross-site POSTs.
- **Tests** use a loopback HTTP fixture (`tests/test_companyscan.py` `Fixture`) and must pass `--allow-private --delay 0`; never hit live sites or social platforms.

## Conventions

- Keep the core scanner stdlib-only; third-party deps go in optional extras and are imported lazily.
- Evidence labels are `OBSERVED` / `EXTRACTED` / `INFERRED` / `UNKNOWN`; findings use PASS / WARNING / FAIL / UNKNOWN with no aggregate score. Heuristics (classifications, CTAs, copy scores, accessibility) must never be presented as proof.
- Design specs and implementation plans live in `docs/superpowers/{specs,plans}/`.
