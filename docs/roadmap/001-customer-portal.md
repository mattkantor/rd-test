# 001 Customer portal

**Status:** done
**Depends on:** none
**Touches:** `src/companyscan/web/` (models, views, templates, urls), `src/companyscan/server/` (urls, settings), new migration

## Goal

A customer logs in, sees the site(s) assigned to them, and manages that site's settings, process and content from a portal. Staff keep the existing admin tools.

## Acceptance criteria

- [x] `Site` has a `user` foreign key to Django's `User` (nullable for existing rows, `on_delete=PROTECT`). One user can own many sites; a site has at most one user.
- [x] Customers sign in with username and password at a portal login page. Google OAuth is not built yet, but the login view is structured so it can be added without rewriting it.
- [x] After login, `/` shows a plain hello-world welcome page.
- [x] A signed-in customer sees a left navigation listing the tools: Content, Social, Website health, Google SEO, Local business, AI visibility, Competitors. Bottom of the navigation: Settings and Help.
- [x] "Website health" opens the existing internal site dashboard for the customer's site. Other entries can be placeholder pages that say "coming soon".
- [x] Settings shows the customer's own account details and their site's profile fields (name, ICP, location, and so on), read-only in this item. Editing comes later.
- [x] A customer can only see sites where `site.user == request.user`. Other sites return 404, not 403.
- [x] Staff login still works for `/admin/` and the staff pages.
- [x] Tests cover: login required, ownership check (another customer's site is a 404), and the navigation links.

## Scope

- Password login using Django auth. Logout.
- Customer accounts created in `/admin/` by staff for now.
- Navigation and placeholder pages.

## Non-goals

- Google OAuth or any other social login (deferred until the app is hosted).
- Customer self-signup or password reset email.
- Editing settings, content, or social from the portal.
- Changing the existing public scorecard at `/sites/<uuid>`. It stays login-free.

## Decisions

- "Site health" and "Website health" are one menu entry, called Website health.
- The Website health page reuses the internal site dashboard (`/site/<int:pk>` and `/run/<name>`), scoped to the customer's site. The public scorecard at `/sites/<uuid>` is not used.

## Ledger

<!-- Append entries below this line. Never edit a past entry. -->

{CHECKPOINT} #1 · agent:matthewkantor-local · abematt@feat/roadmap-001-003@fa46cbb

**Done:** nothing yet; `Site` has no owner, `/` is staff-only, all pages use `staff_member_required`.
**Next:** `Site.user` + migration, portal login/logout, `/` dispatch, left nav, ownership-scoped dashboard, tests.
**Open:** none.

{DECISION} #2 · agent:matthewkantor-local · abematt@feat/roadmap-001-003@fa46cbb

One branch `feat/roadmap-001-003` for items 001 to 003 over per-item `roadmap/NNN-*` branches because the user asked for one branch and one PR; commits carry `Roadmap: NNN`.

{DECISION} #3 · agent:matthewkantor-local · abematt@feat/roadmap-001-003@fa46cbb

`/` dispatches by role (staff keeps the sites list, customers get the welcome page) over moving the staff list because existing staff URLs and tests stay valid.

{DECISION} #4 · agent:matthewkantor-local · abematt@feat/roadmap-001-003@fa46cbb

Existing staff-only dashboard views (`/site/<pk>`, `/run/<name>`, job polls, `/files`, scorecard, fix pack) also serve the owning customer, 404 otherwise, over a duplicate customer dashboard because the item says to reuse it; POST actions and edit stay staff-only.

{DECISION} #5 · agent:matthewkantor-local · abematt@feat/roadmap-001-003@fa46cbb

Django's stock `LoginView`/`LogoutView` and the existing app styles over new UI because the user asked for the default UI; Google login can later swap in at `LOGIN_URL` without touching views.

{CHECKPOINT} #6 · agent:matthewkantor-local · abematt@feat/roadmap-001-003@fa46cbb

**Done:** `Site.user` (migration 0009), portal login/logout, `/` dispatch, left nav, owner-scoped dashboard, read-only Settings; 253 tests and ruff green; README updated.
**Next:** 002 builds on the Content tool and Settings page.
**Open:** a customer with several sites gets a list under Website health; one site redirects straight to its dashboard.
