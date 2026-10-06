# 004 Blog title planning

**Status:** done
**Depends on:** 001 (Content page), 002 (`BlogPost`, keywords, `blog/`)
**Touches:** `src/companyscan/blog/`, `src/companyscan/web/` (model, tasks, portal views), `src/companyscan/views/templates/portal/content.html`, new migration

## Goal

Before any post is written, an agent plans stubs: title, abstract, tags and a publish date, three days apart. Titles use the site's keywords, target its ICP, are written to be indexable, and never duplicate an existing post. The Content page shows the upcoming stubs.

## Acceptance criteria

- [x] `BlogPost` has `abstract`, `tags`, `publish_on` and a `stub` status; `body` stays and is empty for a stub.
- [x] A `titles` job plans a batch of stubs from the profile (ICP, keywords, offering) and the latest crawl text.
- [x] Dates are 3 days apart, continuing after the site's last scheduled post, never in the past.
- [x] No title duplicates, or near-duplicates, an existing post of the site (any status) or another title in the batch.
- [x] The Content menu item shows upcoming stubs in date order, with a button to plan more.
- [x] Tests cover the above with the LLM stubbed.

## Non-goals

Writing bodies for stubs, publishing, editing or rejecting stubs, per-site spacing settings.

## Ledger

<!-- Append entries below this line. Never edit a past entry. -->

{CHECKPOINT} #1 · agent:matthewkantor-local · abematt@feat/roadmap-001-003@185af27

**Done:** nothing for 004; 002 drafts full posts on a schedule and is untouched.
**Next:** model fields + migration, `blog.plan`, `titles` job, Content page section, tests.
**Open:** none.

{DECISION} #2 · agent:matthewkantor-local · abematt@feat/roadmap-001-003@185af27

Stubs are `BlogPost` rows with status `stub` over a new model because body generation later fills the same row, and 002's keyword rotation then counts stubs as used keywords for free.

{DECISION} #3 · agent:matthewkantor-local · abematt@feat/roadmap-001-003@185af27

Python assigns dates, keywords and dedupes (exact match after normalizing, plus word-overlap of 0.7 or more) over trusting the model, because 3-day spacing and no-duplicates must be guaranteed, not requested.

{DECISION} #4 · agent:matthewkantor-local · abematt@feat/roadmap-001-003@185af27

"Indexable" is handled in the prompt (one clear search intent per title, primary keyword early, under 60 characters, abstract 120 to 160 characters, no topic overlap with existing titles) over any indexing API call because nothing is published yet.

{CHECKPOINT} #5 · agent:matthewkantor-local · abematt@feat/roadmap-001-003@185af27

**Done:** `abstract`, `tags`, `publish_on`, `stub` status (migration 0012); `blog.plan`; `titles` job; upcoming section and Plan button on Content; 280 tests and ruff green.
**Next:** a step that writes the body for the earliest due stub (it can reuse `blog.generate` with the stub's title and abstract).
**Open:** batch size (4) and spacing (3 days) are constants in `blog/__init__.py`; stubs cannot be edited or rejected yet. 002's scheduled drafting still writes full posts without stubs.
