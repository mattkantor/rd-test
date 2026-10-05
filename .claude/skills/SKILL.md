---
name: context-ledger
description: "Read and write the context ledger at the bottom of a roadmap item in docs/roadmap/NNN-slug.md — the durable {CHECKPOINT} / {DECISION} / {BLOCKED} / {CONTEXT} / {RESOLVED} / {HANDOFF} trail that carries reasoning state outside the context window. Use whenever a roadmap item is in play: picking up or resuming an item, before starting code on one, at any fork with a real alternative, when blocked and needing human input, when handing work to another agent, or when asked to check or post ledger state. Keywords: context ledger, checkpoint, decision log, blocked, handoff, pick up item, resume item, roadmap item, inject context, what did the agent decide, hand off to another agent."
---

# Context ledger — reasoning state that outlives the context window

Each roadmap item is a markdown file: `docs/roadmap/NNN-slug.md`. Its header holds the goal,
acceptance criteria and status. Everything below the `## Ledger` line is the ledger. You
**read** it to recover state you never had, and you **write** to it so a human can watch
your reasoning, correct it mid-flight, and hand the work to someone else's agent.

Entry templates: [`references/entry-templates.md`](references/entry-templates.md).

## The one rule this exists to enforce

> **Anything a future session or another agent would need, and cannot re-derive from the
> code, goes in the ledger before the session ends.**

A decision that lives only in your context window is lost at summarization. A blocker
you worked around silently is a wrong assumption nobody can see. The test for every
entry: *could the next agent produce the next commit from the item file alone?*

## Where the ledger lives

- Item file: `docs/roadmap/NNN-slug.md`. The ledger is everything after the `## Ledger`
  heading. Entries are append-only.
- Git is the history. Commit the ledger entry with the code it describes, or on its own
  commit if no code changed. Commit subjects and bodies also carry context, so reference
  the item in them: a `Roadmap: NNN` trailer on each commit.
- Nothing is stored anywhere else. Do not keep a separate copy in `.claude/` or the
  scratchpad.

---

## Phase 1 — READ before you touch anything

Triggered by: a roadmap item number in the prompt, a branch named `roadmap/NNN-*`, or
being asked to resume or pick up an item. **Do this before reading code, not after.**

```bash
cat docs/roadmap/NNN-slug.md
git log --oneline --grep='Roadmap: NNN' -20
```

The file is the whole state. The `git log` shows what has already been committed for it.

### Reconstruct state in this order

1. **Latest `{CHECKPOINT}`** — the base. Everything earlier is history; do not replay it.
2. **Every `{DECISION}` after that checkpoint** — binding constraints. Append-only: a
   decision is reversed only by a later `{DECISION}` that says so.
3. **Every `{BLOCKED}` with no matching `{RESOLVED}`** — an open question. **Do not
   proceed past it.** If the answer arrived in the chat, treat that as the answer and
   post the `{RESOLVED}` yourself.
4. **Every `{CONTEXT}` with no matching `{RESOLVED}`** — a standing instruction you have
   not yet acted on.

**Precedence when they conflict: human `{CONTEXT}` > your `{DECISION}` > item header.**
A `{CONTEXT}` that contradicts your earlier decision wins; follow it and post a
`{RESOLVED}` naming the reversal. Never silently keep your own plan.

### Verify the code position

A checkpoint names `repo@branch@sha`. Confirm it still exists and say so if the tree has
moved:

```bash
git cat-file -e <sha>^{commit} 2>/dev/null && echo "sha present" || echo "sha missing — rebased or unpushed"
git log --oneline -1 <branch> 2>/dev/null
```

A missing sha means "done" claims in that checkpoint are unverified. State that plainly
rather than assuming the work is there.

### Reading is silent

Do not write an entry that says you read the ledger. Your first write is the Phase 2 entry
checkpoint. Summarize to the user in chat what the ledger says, including every open
`{BLOCKED}` and unacknowledged `{CONTEXT}`.

---

## Phase 2 — Entry `{CHECKPOINT}` before the first code change

Append one entry checkpoint — **Done / Next / Open**, one line each — **before** editing
code. It is the anchor everything else in the session references, and it is what survives
if the session dies in the next ten minutes. Do not restate the item or describe what the
code looks like today; the reader has both.

If you are picking up a `{HANDOFF}`, name it: `Picking up: #12 {HANDOFF}`.

---

## Phase 3 — During the work

Append when one of these happens, and not otherwise:

| Situation | Marker |
| --- | --- |
| You chose between two viable approaches | `{DECISION}` |
| You are about to do something hard to reverse (migration, data change, dependency, API contract) | `{DECISION}` |
| You need a human answer and cannot safely assume one | `{BLOCKED}` — then **stop**, do not guess |
| An open `{BLOCKED}` or `{CONTEXT}` is now settled | `{RESOLVED}` |
| Scope changed materially from the entry checkpoint | `{CHECKPOINT}` |

`{BLOCKED}` is the one that actually saves work. The failure mode it prevents: guessing,
building on the guess for an hour, and the guess being wrong. State the question, the
options you see, your recommendation, and what you will do if nobody answers.

**Do not narrate.** Tool calls, files read, tests run — none of that is an entry. A
normal session is a handful of entries. Past roughly eight in one sitting you are writing
a transcript, and the two entries someone needed are now buried.

### Re-read at pause points

A human adding `{CONTEXT}` mid-session only reaches you if you look again. Re-read the
item file (same Phase 1 read, cheap) at these moments:

- after posting a `{BLOCKED}`, before you move to unrelated work — the answer may already
  be there
- before starting a materially new step (new file, new migration, new endpoint)
- after any long-running operation you waited on (test suite, deploy, eval run)
- before the Phase 4 closing checkpoint, always

If a new `{CONTEXT}` arrived, it takes precedence over your plan — apply it and post
`{RESOLVED}`. If the user says "check the ledger", that is this read, unconditionally.

---

## Phase 4 — Exit `{CHECKPOINT}`, always

Before the session ends — you finish, you run out of runway, the user stops, or context
is about to be summarized — append a closing `{CHECKPOINT}`. Non-negotiable. An unclosed
session leaves the item claiming work is in flight with no way to find it.

If the item's status changes (`planned` → `in-progress` → `blocked` → `done`), update the
header in the same commit. If ownership moves to another human or agent, append a
`{HANDOFF}` as its own entry. The handoff bar: **the receiver can produce the next commit
knowing only the item file.** If they would have to ask you a question, the handoff is
incomplete — fix it before committing.

---

## Writing an entry

Every agent-written entry opens with one header line:

```
{MARKER} #<seq> · agent:<who>-<where> · <repo>@<branch>@<sha>
```

Build the tail from the working tree:

```bash
printf '%s@%s@%s\n' \
  "$(basename "$(git rev-parse --show-toplevel)")" \
  "$(git branch --show-current)" \
  "$(git rev-parse --short HEAD)"
```

- `<seq>` — count the existing entries in the item's ledger, add one. It is an ordering aid
  so entries can cite each other (`re: #4`). Two agents on different branches can pick the
  same number; resolve the merge conflict by keeping both entries and renumbering the later
  one.
- `agent:<who>-<where>` — `who` is the local part of `git config user.email`, `where` is
  `local`, `cloud`, or `ci`. So: `agent:spalit-local`.

Append the entry at the bottom of the file, after the last existing entry, then commit it.

**Length: the header plus at most six lines** (`{HANDOFF}`: ten). The reader has the item
open, so an entry carries only what is new. Cite earlier entries and human notes by `#n`
or author, never summarise them. No preamble ("first entry on this item", "starting the
backend half"). No "reversible", "what this means for the frontend" or "why the alternative
lost" paragraphs — a `{DECISION}` is `X over Y because Z` on one line. Over budget means you
are restating something already in the item.

**One marker per entry.** An entry carrying two ideas cannot be answered. Never edit a
posted entry to change its meaning — the ledger is append-only. Correct it with a new
entry that references the old number.

Human `{CONTEXT}` entries carry no envelope. Accept a bare `{CONTEXT} don't touch the
migration` exactly as it is; never ask a human to format a note.

---

## Redaction — hard stop

The repo is pushed to GitHub, and commit history is permanent. **Never** put in a ledger
entry or a commit message:

- JWTs, bearer tokens, API keys, DB or AWS credentials
- customer document filenames, client names attached to findings, raw PII
- tenant `company_id`s identifying a real client
- full LLM answers or judge reasoning containing client content

Use placeholders — `company_id=<tenant-A>`, `doc=<client-doc-1>` — and keep real values in
the session.

---

## Anti-patterns

| Do not | Instead |
| --- | --- |
| Post a play-by-play of tool calls | Record decisions and state only |
| Guess past a `{BLOCKED}` | Append it and stop |
| Edit an entry to change its meaning | Append a new entry citing the old `#seq` |
| Combine `{CHECKPOINT}` and `{DECISION}` in one entry | Two entries |
| Restate the item header in a checkpoint | Link to it |
| Summarise an earlier entry before adding to it | Cite `#n`; say only what is new |
| Open with preamble ("first entry", "starting the BE half") | First line after the header is state |
| Justify a decision in paragraphs | `X over Y because Z`, one line |
| Exceed six lines | Cut until it fits; the item already has the rest |
| End a session without a closing `{CHECKPOINT}` | Always append one |
| Keep your own plan when a human `{CONTEXT}` disagrees | `{CONTEXT}` wins; post `{RESOLVED}` |
| Ask the human to re-format their note | Parse it as written |
| Write ledger notes into `.claude/` or the scratchpad | The item file is the only store |
