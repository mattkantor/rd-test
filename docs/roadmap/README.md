# Roadmap

Each feature is one markdown file in this folder: `NNN-slug.md`. The file holds the goal,
acceptance criteria and status at the top, and an append-only ledger below. The ledger is
how an agent (or a person) picks up work without the earlier context.

Baseline of what the product does today: [`../features.md`](../features.md).

## Items

| # | Item | Status |
| --- | --- | --- |
| 001 | [Customer portal](001-customer-portal.md) | done |
| 002 | [Scheduled blog posts from the site profile](002-scheduled-blog-posts.md) | done |
| 003 | [Google Business Profile agent](003-google-business-profile.md) | planned |

## Adding an item

1. Take the next number and write `NNN-slug.md` with this header:

   ```markdown
   # NNN Title

   **Status:** planned
   **Depends on:** none
   **Touches:** paths the work will change

   ## Goal

   One or two sentences.

   ## Acceptance criteria

   - [ ] Each one is something you can check.

   ## Scope

   ## Non-goals

   ## Ledger

   <!-- Append entries below this line. Never edit a past entry. -->
   ```

2. Add a row to the table above.
3. Commit the file on its own.

Or ask an agent: "add a roadmap item: <title>, it should do <goal>".

## Working an item

- Pick a `planned` item whose dependencies are `done` and whose `Touches` paths don't
  overlap work already in progress.
- Read the item and its ledger first. The `context-ledger` skill
  (`.claude/skills/SKILL.md`) has the procedure and the entry markers.
- Work on a branch named `roadmap/NNN-slug`. Put `Roadmap: NNN` in commit trailers.
- Append `{CHECKPOINT}` entries as you go. Record `{DECISION}` at each fork and
  `{BLOCKED}` when you need a human answer.
- When the acceptance criteria pass, set the status to `done` and update the table.
