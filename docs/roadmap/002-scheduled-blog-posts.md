# 002 Scheduled blog posts from the site profile

**Status:** done
**Depends on:** 001 (customer portal, where the customer sees and reviews posts)
**Touches:** `src/companyscan/web/models.py` (Site fields, post model), `src/companyscan/web/forms.py` and the site edit view, `src/companyscan/web/tasks.py` (scheduled task), new migration, a new blog generation module (`src/companyscan/blog/`), `src/companyscan/llm.py` (model call only)

## Goal

Each site profile gets two new fields, **keywords** and **what the business does**. From the full profile, the app generates blog posts on a schedule, so a customer gets a steady stream of posts without writing them.

## Acceptance criteria

- [x] `Site` gets two new fields: `keywords` (text, one per line or comma-separated) and `offering` (what the business does, free text).
- [x] Both fields show on the staff site edit page and the customer Settings page (001), and save.
- [x] A generation step takes the full profile (business name, ICP, category, location, people, aliases, keywords, offering) and the site's latest crawl content, and produces one post: title, meta description, body in markdown, and the keyword it targets.
- [x] Each generated post is stored as a **draft** on the site, with its source profile version and the run it used. Nothing is published automatically.
- [x] A schedule (per site: frequency and number of posts per run) creates drafts through the Huey worker, one job per site, using the existing single-running-job rule.
- [x] Customers see their drafts in the Content tool (001) and can approve or reject each one. Approval is recorded; publishing is a separate step.
- [x] A post never repeats a keyword already used on the same site in the last N posts, unless the schedule says so.
- [x] Tests cover: the new fields save, the generator is called with the profile and keywords (LLM stubbed via `chat_model`), drafts are created on schedule, and nothing is published without approval.

## Scope

- Two new profile fields, plus their form and admin entries.
- Post model with draft and approval status.
- Per-site schedule and the worker task.
- Generation with the existing `chat_model()` path, JSON-mode output.

## Non-goals

- Publishing to a CMS, the customer's website, or social. Export as markdown is enough for now.
- Images or media.
- Scoring or SEO metrics on the generated posts.
- Generation without a human approval step.

## Open questions

- Publishing: approval only (drafts exported by hand), or should a later item add a publish target? Assumed: approval only for now.
- Frequency: default assumed to be one post per week per site. Confirm.
- Writing style: is there a house voice to follow, or only the profile fields? Assumed: profile fields only, plus the copy rules already in the report (no unsupported claims, no pressure tactics).
- Post length: assumed 600 to 900 words. Confirm.
- Facts: posts must only use what the site or profile states. Assumed: any claim not in the profile or crawl is left out, not invented.

## Ledger

<!-- Append entries below this line. Never edit a past entry. -->

{CHECKPOINT} #1 · agent:matthewkantor-local · abematt@feat/roadmap-001-003@5b64787

**Done:** nothing for 002; 001 is committed, so Content and Settings pages exist (`web/portal.py`).
**Next:** Site fields + `BlogPost` model, `blog/` generator, `blog` job kind + hourly scheduler, Content approve/reject, tests.
**Open:** the five open questions below, answered with the item's own assumptions (see decisions).

{DECISION} #2 · agent:matthewkantor-local · abematt@feat/roadmap-001-003@5b64787

Item's assumptions taken as defaults (weekly, one post, 600 to 900 words, approval-only, profile fields plus crawl as the only facts) over blocking, because the user said to continue unless blocked; the schedule fields are per site so frequency changes without code.

{DECISION} #3 · agent:matthewkantor-local · abematt@feat/roadmap-001-003@5b64787

Python picks the target keyword (first one not used in the last 10 posts) and tells the model, over letting the model choose, because the no-repeat rule must be enforceable and testable without trusting the LLM.

{DECISION} #4 · agent:matthewkantor-local · abematt@feat/roadmap-001-003@5b64787

Scheduler is a Huey hourly `db_periodic_task` that queues a `blog` Job through the existing `tasks.start`, over a cron/management command, because the single-running-job rule and progress UI come for free.

{CHECKPOINT} #5 · agent:matthewkantor-local · abematt@feat/roadmap-001-003@5b64787

**Done:** fields, `BlogPost`, `blog/` generator, `blog` job + hourly `schedule_blogs`, Content approve/reject, migration 0010; 259 tests and ruff green; README updated.
**Next:** 003 reuses the portal login, site ownership and the approve/reject pattern in `web/portal.py`.
**Open:** none blocking; defaults (weekly, one post, approval-only) still await human confirmation. Word count is a prompt rule, not enforced.
