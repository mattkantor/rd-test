# 003 Google Business Profile agent

**Status:** done
**Depends on:** 001 (customer portal and sign-in), 002 only for the Content tool's shared approval pattern
**Touches:** `src/companyscan/dimensions/google_business.py` (Places lookup, read-only, unchanged), new `src/companyscan/google/` (OAuth, Business Profile client, change proposals), `src/companyscan/web/` (connect page, approval queue, models), new migration, `src/companyscan/web/tasks.py` (sync and claim-status jobs)

## Goal

A customer connects their Google account in the portal. An agent reads their Google Business Profile, proposes fixes to location info, starts the claim where the listing is unclaimed, and drafts review and Q&A replies. The customer approves each change before anything is written to Google.

## Acceptance criteria

- [x] The customer connects their Google account from the portal with OAuth. Tokens are stored encrypted per site, and the customer can disconnect at any time.
- [x] The app lists the Business Profile locations that account manages. The customer picks which one belongs to their site. A location is matched to the site by website or phone, with a warning if neither matches.
- [x] The app reads the location's name, address, phone, hours, categories, description, and website, and compares them with the site profile (001 and the existing profile fields). Each mismatch is shown with the current and proposed value.
- [x] Edits are proposed, never sent automatically. The customer approves or rejects each one. Approved edits are written through the Business Profile API and recorded with the before and after values.
- [x] Claim status is read for the site. If the location is unclaimed, the app starts Google's verification flow and shows its status. Completing verification stays with Google (postcard, phone or video); the app does not try to bypass it.
- [x] Reviews and questions are read from the API. The app drafts a reply to each, and the customer approves before it is posted. The draft never states facts that aren't in the profile.
- [x] The Places API key (`PLACES_API_KEY` / `GOOGLE_PLACES_API_KEY`) stays read-only and remains the source for the existing `google_business` dimension. OAuth is used only for reads and writes on the Business Profile API.
- [x] Tests cover: OAuth callback and token storage (Google stubbed), mismatch detection, proposals waiting for approval, a rejected proposal never writing, and a reply draft never posting without approval.

## Scope

- Google OAuth for the customer, scoped to Business Profile management.
- Listing read and edit through the Business Profile API, with per-field proposals.
- Claim status and start of the verification flow.
- Review and Q&A reading, with reply drafts for approval.
- Approval queue in the portal, and an audit record of every write.

## Non-goals

- Completing verification on the customer's behalf.
- Automatic writes without approval.
- Creating new listings for businesses that aren't the customer's.
- Google Search or Maps rank tracking. The existing Places lookup stays as it is.
- Flagging listing suspensions or duplicates beyond what the API reports.
- Social login for the customer account (001 covers password only for now).

## Open questions

- **Business Profile API access is not confirmed.** Check whether the project has approved access. If not, request it first. Until it's approved, only the Places-based read (already built) can run. Need your answer before the write path can be tested.
- **Google's OAuth app verification.** Business Profile scopes need Google's app verification before anyone outside your test users can connect. Expect a review that can take weeks. Confirm this is acceptable before the portal launches.
- **Reply drafts:** should the agent draft replies to negative reviews too, or only positive ones and questions? Assumed: all, with the customer approving each one.
- **Multiple locations:** one site can map to more than one Business Profile location. Assumed: the customer picks one location per site for now.
- **Hosting:** OAuth redirect URLs need a public HTTPS address. The item assumes this waits until the app is hosted (the Docker/Caddy deploy in `docs/deploy.md`). Confirm.

## Design notes (draft, not approved)

### Purpose

A customer connects their Google account in the portal. The app reads their Business Profile
location, shows what differs from the site profile, and proposes edits. It also starts the
claim flow for an unclaimed listing and drafts replies to reviews and questions. Nothing is
written to Google until the customer approves it.

### Decisions (from the roadmap questions)

- **Scope:** read and edit listing info; start claim and verification; read reviews and Q&A
  with reply drafts. No listing-problem flagging beyond what the API reports.
- **Who signs in:** the customer, with their own Google account, from the portal (item 001).
  The app only touches locations that account manages.
- **Writes:** every change and reply is a proposal. The customer approves it, then the app
  writes it. A rejected proposal is never sent.
- **Places key:** `GOOGLE_PLACES_API_KEY` stays read-only and keeps feeding the existing
  `dimensions/google_business.py` check. It is never used for writes.
- **Credentials:** `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` in `.env` (git-ignored).
  Add both names to `env.example`, without values.

### Google APIs used

Confirm endpoint names and field shapes against Google's current reference at build time.
The design assumes:

| Need | API | Note |
| --- | --- | --- |
| List the accounts and locations a user manages | Account Management | Needs the `business.manage` scope |
| Read and update location info | Business Information | `locations.get` and `locations.patch` with an `updateMask` |
| Claim status, start verification | Verifications | Google completes the verification (postcard, phone or video) |
| Read reviews, post a reply | Business Profile reviews | Reply is written only after approval |
| Read and answer questions | Q&A | Answer is written only after approval |

OAuth scope: `https://www.googleapis.com/auth/business.manage`.

### Components

Each unit has one job and talks to the rest through a small interface.

- **`companyscan/google/oauth.py`**: builds the consent URL, exchanges the callback code for
  tokens, refreshes access tokens. Knows nothing about listings.
- **`companyscan/google/client.py`**: thin wrapper over the Business Profile endpoints above.
  Takes a valid access token and returns plain dicts. Retries once on 401 after a refresh.
- **`companyscan/google/compare.py`**: pure function. Takes a location dict and a site profile,
  returns field mismatches as `{field, current, proposed}`. No network. Easy to test.
- **`companyscan/google/proposals.py`**: creates, approves, rejects and applies proposals.
  Applying a proposal calls the client, then records the result on the proposal.
- **`web/` views and templates**: connect page, location picker, mismatch list, approval
  queue, reviews and Q&A drafts. Jinja2 templates, escaped output.

### Data model

- `GoogleConnection`: `site` (FK), `user` (FK), `google_account_id`, `token` (encrypted),
  `refresh_token` (encrypted), `expires_at`, `created_at`, `revoked_at`. One active connection
  per site.
- `GoogleLocation`: `connection` (FK), `location_id`, `name`, `snapshot` (JSON of the last read),
  `read_at`. One per Business Profile location the customer picked for the site.
- `Proposal`: `location` (FK), `kind` (`field_edit`, `review_reply`, `qna_answer`,
  `claim_start`), `target` (field name, or review or question id), `before`, `after`
  (JSON), `status` (`pending`, `approved`, `rejected`, `applied`, `failed`), `created_at`,
  `decided_at`, `decided_by` (FK), `error` (text, may be empty).

An audit trail is the `Proposal` rows themselves: each applied write keeps its before and
after values and who approved it.

### Flows

**Connect.** Customer clicks Connect on the site page. The app redirects to Google with the
`business.manage` scope and a `state` value stored in the session. The callback checks
`state`, exchanges the code, and stores the tokens encrypted. The customer then picks a
location from the list Google returns. If neither the website nor the phone matches the site,
the picker shows a warning and asks for confirmation.

**Read and compare.** A sync job (Huey, one per site, same single-running-job rule as crawls)
reads the chosen location and runs `compare.py` against the site profile. Each mismatch
becomes a `field_edit` proposal in `pending`. Existing pending proposals for the same field
are updated, not duplicated.

**Approve and apply.** The customer approves a proposal. The app writes it with
`locations.patch` and an `updateMask` containing only that field. The result is stored on the
proposal. A failed write sets status `failed` with the error and leaves the old value in
place.

**Claim.** If the location is unclaimed, the portal shows a Start claim button. It creates a
`claim_start` proposal, which the customer approves. The app then starts the verification
through the Verifications API and shows the status Google returns. The app never completes
the verification.

**Reviews and Q&A.** A sync reads new reviews and questions. For each one with no reply, the
app drafts a reply as a `review_reply` or `qna_answer` proposal. The draft uses only facts in
the site profile and the crawl. The customer approves or edits it before it is posted.

### Errors and limits

- **Token expired or revoked:** refresh once. If that fails, mark the connection revoked and
  show "Reconnect Google" on the site page. No writes are attempted.
- **API quota or 5xx:** retry with backoff up to three times in the worker. Then the job
  fails, and the UI shows the last successful sync time.
- **Write rejected by Google:** the proposal becomes `failed` with Google's message. It is not
  retried automatically.
- **Unknown field or missing location:** `compare.py` skips it and the job records a warning
  instead of guessing.
- **Logs:** never log tokens, the client secret, review text, or reply drafts. Log IDs and
  status only, per the logging rules in `CLAUDE.md`.

### Security

- Tokens are encrypted at rest with `cryptography`'s Fernet, using a key from
  `GOOGLE_TOKEN_KEY` in `.env`. This is one new dependency, added to the `web` extra.
- The OAuth `state` is checked on callback to prevent login CSRF.
- Each view checks that the requesting user owns the site (item 001), so a customer can never
  reach another customer's connection.
- Redirect URI comes from `GOOGLE_OAUTH_REDIRECT_URI`. Localhost works for development;
  production needs HTTPS (see `docs/deploy.md`).

### Testing

- `compare.py`: unit tests with fixed location and profile dicts.
- `oauth.py` and `client.py`: HTTP stubbed. No live Google calls in tests, per `CLAUDE.md`.
- `proposals.py`: a rejected proposal never calls the client; a failed write keeps the old
  value; approval writes only the named field's `updateMask`.
- Views: connect requires login and site ownership; the callback rejects a bad `state`.
- Reply drafts: the test asserts a draft is created as `pending` and never posted without
  approval.

### Open items

- **Confirm API access** is enabled in the project and the OAuth consent screen is configured
  for the `business.manage` scope. Google's app verification is still needed before outside
  users can connect.
- **Token encryption key:** generate `GOOGLE_TOKEN_KEY` and add it to `.env` and `env.example`
  before implementation.
- **Hosting:** the redirect URI needs HTTPS in production. Development uses localhost.

## Ledger

<!-- Append entries below this line. Never edit a past entry. -->

{CHECKPOINT} #1 · agent:matthewkantor-local · abematt@feat/roadmap-001-003@75f7f32

**Done:** nothing for 003; 001 and 002 are committed (portal login, ownership checks, approve/reject pattern, `Job` kinds).
**Next:** models + migration, `google/` (oauth, client, compare, proposals, replies), `google` job, Local business page, tests.
**Open:** Business Profile API access and Google app verification are unconfirmed; see #3.

{DECISION} #2 · agent:matthewkantor-local · abematt@feat/roadmap-001-003@75f7f32

Hand-written OAuth in `google/oauth.py` (stdlib `urllib`) over django-allauth because the item needs Fernet-encrypted per-site tokens and a connect flow that is not a login; allauth stores plain tokens, adds sites/socialaccount tables and Django-template pages the Jinja UI doesn't use. Only new dependency is `cryptography`.

{BLOCKED} #3 · agent:matthewkantor-local · abematt@feat/roadmap-001-003@75f7f32

**Question:** is Business Profile API access approved for the Google project, and is the OAuth consent screen set up for `business.manage`?
**Options:** (a) build everything against stubbed HTTP, untested live; (b) wait.
**Recommend:** (a). **If no answer:** doing (a); endpoint paths are written from Google's docs from memory and need one live check before launch. Claude was also denied reading `oauth.json`, so credentials come only from `GOOGLE_OAUTH_*` env vars.

{DECISION} #4 · agent:matthewkantor-local · abematt@feat/roadmap-001-003@75f7f32

Edits limited to name, phone, website and description over address, hours and categories because the site profile is free text and cannot map safely to Google's structured address, hours or category IDs; those three are read and shown only. `Site.phone` added so a phone mismatch is detectable.

{DECISION} #5 · agent:matthewkantor-local · abematt@feat/roadmap-001-003@75f7f32

Approve applies the write in the same request (status `approved` then `applied` or `failed`) over a separate apply step because a customer approval is the only trigger the item allows; a rejected proposal has no code path to the client.

{DECISION} #6 · agent:matthewkantor-local · abematt@feat/roadmap-001-003@75f7f32

Redirect URI `/google/callback` (from `env.example`) and the Local business nav entry host the feature, over the Google SEO entry, because Google SEO means search rank, which is a non-goal here.

{CHECKPOINT} #7 · agent:matthewkantor-local · abematt@feat/roadmap-001-003@75f7f32

**Done:** models + migration 0011, `google/` (oauth, client, compare, replies, proposals), `google` job + daily `sync_google`, Local business page, admin audit view; 273 tests and ruff green; README and `cryptography` extra updated.
**Next:** one live check against Google once API access is approved: endpoint paths in `google/client.py`, the `updateMask` for `phoneNumbers.primaryPhone`, and the verification flow.
**Open:** #3 still unanswered, so the write path is tested only against stubs. Google app verification is needed before non-test users connect; HTTPS redirect URI needed in production.
