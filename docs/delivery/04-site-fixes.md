# 04 Highest-impact SEO, AEO and conversion fixes on the existing site

## Outcome

The report's findings fixed on the live site, in cost order: analytics and consent, security headers, SEO
basics, structured data, link previews, accessibility, unanswered buyer questions, AI slop rewrites, truthful
persuasion, practitioner profiles, social proof display.

## Inputs

- Fix pack zip from item 01 (`START.md`, `tasks/`, `data/`, `OWNER-TODO.md`).
- Intake: site path, who edits, host.

## Steps

1. **manual** Answer `OWNER-TODO.md` with the owner before any task starts. Every `TODO(owner)` left in a task is
   a fact to collect, not to invent.
2. **exists, path A** Unzip next to the site's repo and run Claude Code or Codex: "Read START.md in the fix pack
   and complete every task in its checklist." Review each commit. Deploy.
3. **manual, path B** Work the task files in checklist order. Each one's **What to do** maps to a CMS setting:
   SEO basics to the page SEO panel, structured data to a code injection or SEO plugin, headers to the host's
   settings (often not possible on hosted builders; record as a known limit), copy tasks to the page editor.
4. **generate, path B** A paste sheet: per page, the title, description, H1 and JSON-LD to set, in CMS order,
   so step 3 is copy and paste rather than reading task files.
5. **manual** Items the fix pack lists under **Also noted** go to `intake.md` as backlog for Stay chosen.
6. **exists** Re-crawl + report. The task files' **Done when** checks are the acceptance test.

## Deliverables

- Path A: commits in the site repo. Path B: `assets/paste-sheet.md` and the changes live in the CMS.
- `OWNER-TODO.md` answered

## Done when

- Re-crawl: every task's **Done when** holds (SEO pass rate, JSON-LD share, headers, accessibility barriers,
  analytics on every page are all dashboard tiles).
- `answer_coverage` questions the tasks addressed moved from `missing` to `answered` or `partial`.
- Copy scores on rewritten pages are LOW slop and at most MEDIUM bias.
