# 001 Customer portal

**Status:** planned
**Depends on:** none
**Touches:** `src/companyscan/web/` (models, views, templates, urls), `src/companyscan/server/` (urls, settings), new migration

## Goal

A customer logs in, sees the site(s) assigned to them, and manages that site's settings, process and content from a portal. Staff keep the existing admin tools.

## Acceptance criteria

- [ ] `Site` has a `user` foreign key to Django's `User` (nullable for existing rows, `on_delete=PROTECT`). One user can own many sites; a site has at most one user.
- [ ] Customers sign in with username and password at a portal login page. Google OAuth is not built yet, but the login view is structured so it can be added without rewriting it.
- [ ] After login, `/` shows a plain hello-world welcome page.
- [ ] A signed-in customer sees a left navigation listing the tools: Content, Social, Website health, Google SEO, Local business, AI visibility, Competitors. Bottom of the navigation: Settings and Help.
- [ ] "Website health" opens the existing internal site dashboard for the customer's site. Other entries can be placeholder pages that say "coming soon".
- [ ] Settings shows the customer's own account details and their site's profile fields (name, ICP, location, and so on), read-only in this item. Editing comes later.
- [ ] A customer can only see sites where `site.user == request.user`. Other sites return 404, not 403.
- [ ] Staff login still works for `/admin/` and the staff pages.
- [ ] Tests cover: login required, ownership check (another customer's site is a 404), and the navigation links.

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
