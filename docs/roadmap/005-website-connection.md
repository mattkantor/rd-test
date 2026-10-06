# 005 Website connection

**Status:** done
**Depends on:** 001 (portal, Settings page, site ownership)
**Touches:** `src/companyscan/web/` (model, new `connect.py`, urls), `src/companyscan/views/templates/portal/`, new migration

## Goal

A customer records how their website's admin can be reached, from a Settings subpage where they choose which of their sites it is for. Later items use it to export data (blog posts and so on) to the site.

## Acceptance criteria

- [x] Settings has a "Website connection" subpage, linked from Settings and keeping Settings highlighted in the navigation.
- [x] The customer chooses one of their own sites; the page then shows that site's connection form.
- [x] The connection holds platform, admin URL, username and a secret (password or API token). The secret is stored encrypted and never shown again; leaving it blank on edit keeps it.
- [x] A customer can disconnect, which deletes the stored credentials.
- [x] Only the site's owner can see or change a connection (404 otherwise).
- [x] Tests cover the above.

## Non-goals

Exporting anything, verifying the credentials against the website, per-platform setup guides.

## Ledger

<!-- Append entries below this line. Never edit a past entry. -->

{CHECKPOINT} #1 · agent:matthewkantor-local · abematt@feat/roadmap-001-003@9b81c5b

**Done:** nothing for 005.
**Next:** `SiteConnection` model + migration, `web/connect.py` views, template, tests.
**Open:** platform list and credential type were not specified; see #2.

{DECISION} #2 · agent:matthewkantor-local · abematt@feat/roadmap-001-003@9b81c5b

A generic platform + admin URL + username + secret record over one platform's API because the target CMS is unknown; platform is a choice list (WordPress, Shopify, Webflow, Squarespace, Wix, Other) so the export step can branch on it without a migration.

{DECISION} #3 · agent:matthewkantor-local · abematt@feat/roadmap-001-003@9b81c5b

Secret encrypted with the existing Fernet key (`GOOGLE_TOKEN_KEY` through `google.oauth.encrypt`) over a second key because one key to guard and rotate is enough for now; the name is Google-specific and can be generalized when a second key is needed.

{DECISION} #4 · agent:matthewkantor-local · abematt@feat/roadmap-001-003@9b81c5b

Save without a live check over testing the login because a check needs a per-platform client; the page says the credentials are stored, not verified.

{CHECKPOINT} #5 · agent:matthewkantor-local · abematt@feat/roadmap-001-003@9b81c5b

**Done:** `SiteConnection` (migration 0013), `web/connect.py`, Settings subpage with site chooser, disconnect, owner-only; 287 tests and ruff green.
**Next:** an export step that reads `site.connection`, decrypts `secret` with `google.oauth.decrypt`, and branches on `platform`.
**Open:** platform list and credential shape need confirming against the CMS you actually use; credentials are not verified; the encryption key is still named for Google.
