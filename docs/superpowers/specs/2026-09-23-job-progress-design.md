# Job progress on the dashboard: design

Date: 2026-09-23 · Status: approved in chat, awaiting spec review · Builds on: `2026-09-23-run-dashboard-design.md`, re-crawl

## Goal

While a crawl, re-crawl or report job runs for a site, its dashboard shows what is happening: the current step, a progress bar, and counts where the step has them. It refreshes itself until the job finishes. It then shows the result, and for a crawl it links to the new run.

## Progress reporting

- `scan.crawler.Client` gets a `progress` attribute: a callable `progress(done=None, total=None, unit="")`. The default does nothing.
- `cli.run(args, target=None, output=None, progress=None)`. When `progress` is given, `run` builds the step list and, before each step, points `client.progress` at a callback that forwards `(step_number, steps, step_label, done, total, unit)` to `progress`. The steps are:
  1. `Discovering sitemaps`
  2. `Crawling pages`: the crawl loop calls `client.progress(len(pages), client.config.max_pages, "pages")` after each page
  3. `Running technical checks` (technical reports plus accessibility)
  4. One step per selected dimension, labelled with `DIMENSIONS[name]["label"]`, e.g. `LLM reputation`
  5. `Writing bundle`
- Without `progress`, the CLI behaves exactly as before, with no output.
- `dimensions.reputation.collect` passes `client.progress` into `rank_reputation(..., progress=...)`, which calls `progress(answered, total, "buyer answers")` after each sampled answer, where `total = len(prompts) × samples`.
- The report job has two steps: `Claude is writing the report` (no counts) and `Rendering PDF`.

## Job state (`web/jobs.py`)

- `JOBS[key]` keeps `state` and `label` and adds `kind` (`"crawl"` or `"report"`), `run` (the bundle folder name the job writes or reports on), `step`, `steps`, `done`, `total`, `unit`, `started` and `finished` (ISO UTC times).
- `label` is always a readable one-liner, e.g. `Crawling pages: 32 of 50 pages`. The home page keeps showing it.
- `percent(job) -> int` (0–100) = (completed steps + the fraction done in the current step) ÷ steps. The fraction is `done / total` when `total` is set, otherwise 0. A finished job is 100.
- `claim(key, label, kind, run)` records the kind, run and start time. `execute` records `finished`, and on success keeps `run` and `kind`, so the result can link to the new run.

## Dashboard

- The route looks up `jobs.JOBS.get(origin(normalize(manifest.input_url)))` and passes it, together with `percent`, to the template.
- **Running:** a status panel with the kind (Crawl / Re-crawl / Report), the step label, `step N of M`, a bar whose width is `percent` (a CSS width on a div), `done of total unit` when known, the start time, and `<meta http-equiv="refresh" content="3">`.
- **Done:** `✔ <label>`, and for a crawl job whose `run` differs from this bundle, a `View new run` link to `/run/<run>`.
- **Error:** the error label in the error colour.
- **No job for this site:** no panel.
- **Returning to the dashboard:** the dashboard's Re-crawl and Generate-report forms send `return_to=dashboard`. `/recrawl` and `/report` then redirect to `/run/<dir>` built from the validated bundle's own name. Any other value, or none, redirects to `/` as before, so there is no open redirect.

## Out of scope

- Live updates without a page reload (JavaScript or server-sent events)
- Cancelling a job
- Keeping job history across server restarts (jobs stay in memory)
- CLI progress output

## Testing

- `run()` with a progress collector against the existing loopback fixture: the steps arrive in order, the step count is 4 plus the number of dimensions, and the page counts rise to the number of pages crawled.
- `rank_reputation` progress: the final call is `(total, total, "buyer answers")`.
- `percent`: mid-step with counts, mid-step without counts, and a finished job.
- The dashboard shows the panel, bar and refresh while a job runs; `View new run` after a crawl job finishes; the error label after a failure; and no panel when there is no job.
- `/recrawl` and `/report` with `return_to=dashboard` redirect to `/run/<dir>`, and without it to `/`.
- The existing tests that compare the whole `JOBS` dict change to check only the fields they care about.
