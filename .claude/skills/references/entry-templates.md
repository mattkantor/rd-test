# Entry templates

The reader has the item file open, so an entry carries only what is new and cites the
rest by `#seq`. Budget: the header plus at most six lines (`{HANDOFF}`: ten). Over budget
means you are restating something the item already says.

Header line, always:

```
{MARKER} #<seq> · agent:<who>-<where> · <repo>@<branch>@<sha>
```

Examples use roadmap item `001-customer-portal`. Values are illustrative, not real state.

---

## `{CHECKPOINT}`

Three lines: **Done / Next / Open**. State, not story — no "understood as", no plan list,
no file list, no preamble.

Entry:

```
{CHECKPOINT} #1 · agent:spalit-local · abematt@roadmap/001-customer-portal@a1b2c3d

**Done:** nothing yet; `Site` has no owner field.
**Next:** `Site.user` foreign key + migration → login view → navigation → tests.
**Open:** none.
```

Closing:

```
{CHECKPOINT} #9 · agent:spalit-local · abematt@roadmap/001-customer-portal@f4e5d6c

**Done:** `Site.user` migration; login and logout; ownership check returns 404; `make test` green.
**Next:** navigation placeholders; Settings page read-only view.
**Open:** none.
```

## `{DECISION}`

One line: `X over Y because Z`.

```
{DECISION} #3 · agent:spalit-local · abematt@roadmap/001-customer-portal@b7c8d9e

Django `User` FK on `Site` over a separate `Customer` model because auth already covers login and password reset.
```

## `{BLOCKED}`

The question, the options, your recommendation, and what you do if nobody answers.

```
{BLOCKED} #4 · agent:spalit-local · abematt@roadmap/001-customer-portal@b7c8d9e

**Question:** should a site be allowed to have no owner after the migration?
**Options:** (a) nullable, staff-only until assigned; (b) required, backfill to a placeholder user.
**Recommend:** (a). **If no answer:** I keep it nullable and stop before the portal view.
```

## `{RESOLVED}`

Names the entry it closes.

```
{RESOLVED} #5 · agent:spalit-local · abematt@roadmap/001-customer-portal@c0d1e2f

Re: #4. Nullable, per human `{CONTEXT}` in chat. Staff sees unowned sites in admin.
```

## `{CONTEXT}`

Human-written. No envelope required. Accept it as written.

```
{CONTEXT} don't touch the admin login; customers use the portal only.
```

## `{HANDOFF}`

Ten lines at most. The receiver must be able to produce the next commit from the item alone.

```
{HANDOFF} #11 · agent:spalit-local · abematt@roadmap/001-customer-portal@f4e5d6c

**Done:** owner FK, login, ownership check, tests (see commits tagged `Roadmap: 001`).
**Next:** navigation with eight entries (Settings and Help at the bottom); Website health links to `/site/<pk>`.
**Open:** Google OAuth is out of scope; leave the login view ready for it.
**Start with:** `src/companyscan/web/views.py`, the portal section; the acceptance checklist in the item header.
**Watch:** `Site.user` is nullable; unowned sites must 404 for customers, not appear in their list.
```
