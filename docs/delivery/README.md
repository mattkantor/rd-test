# Delivery playbook

How an engagement runs after a prospect says "fix it". Written for the operator today and structured so each
item can become a skill or generator later. One file per delivery item, same five sections in each:
**Outcome**, **Inputs**, **Steps**, **Deliverables**, **Done when**.

Every step is tagged:

- **exists**: the tool does it now; the step names the command or UI action.
- **generate**: the product should produce this and doesn't yet. Listed in [Build order](#build-order).
- **manual**: a human does it, with a checklist. Many stay manual on purpose (anything that posts to a third
  party in the customer's name).

Scope: local professional services (medical, dental, legal, wedding, auto care and similar). Vertical
differences appear only where platforms or rules differ, in items 03, 07 and 08.

## The ten items

| # | File | Status today |
|---|---|---|
| 1 | [01-diagnostic.md](01-diagnostic.md) | exists |
| 2 | [02-analytics.md](02-analytics.md) | exists (tag), manual (conversions, verification) |
| 3 | [03-business-profiles.md](03-business-profiles.md) | exists (observe), manual (fix) |
| 4 | [04-site-fixes.md](04-site-fixes.md) | exists (static site), manual (CMS) |
| 5 | [05-service-location-pages.md](05-service-location-pages.md) | generate |
| 6 | [06-positioning-copy.md](06-positioning-copy.md) | exists (rewrites), manual (positioning) |
| 7 | [07-citations.md](07-citations.md) | exists (gaps), manual (listings) |
| 8 | [08-reviews.md](08-reviews.md) | exists (observe), manual (process) |
| 9 | [09-tracking.md](09-tracking.md) | exists (AI prompts), manual (search queries) |
| 10 | [10-rerun.md](10-rerun.md) | exists (re-crawl, changes), manual (leads) |

## Engagement flow

1. **Prospect**: `companyscan scan` (or a batch row), **Generate report**, customer scorecard. See
   [docs/marketing.md](../marketing.md) for the pitch.
2. **Yes**: intake call. Fill `intake.md` (below). Decide the site path.
3. **Baseline**: item 01 rerun with the intake facts, so every later comparison starts from a run that used the
   right ICP, location, category and place ID.
4. **Get chosen** (the $5K, roughly four weeks): items 02 to 08, in the order the scorecard's cost ranking puts
   them, with 02 and 03 always first (nothing else can be measured without them).
5. **Stay chosen** (the $500/month): items 09 and 10 on a monthly cadence, plus the smaller fixes they surface.

## Intake

Collected on the kickoff call and kept in `customers/<slug>/intake.md`. Every field is used by a named step.

| Field | Used by |
|---|---|
| Business name, aliases, category (vertical) | 01 `--company-name`, `--alias`, `--category`; 03 |
| Location(s) served, as "City, State, Country" | 01 `--location`; 05 page targets; 09 queries |
| ICP: who buys and what they're trying to get done | 01 `--icp`; 05; 06 |
| Services, ranked by margin and demand | 05 page targets; 09 queries |
| Practitioners (name, credentials, page) | 01 `--person`; 05; 06 |
| Google Business Profile place ID, or "not claimed" | 01 `--place-id`; 03 |
| Known profiles (Facebook, Instagram, LinkedIn, directories) | 01 `--known-profile`; 07 |
| Customer lifetime value, new customers wanted per year | Scorecard dollars (site edit page) |
| How customers contact them: phone, form, booking tool, chat | 02 conversion events; 05 CTA |
| Site platform and who can edit it | 04 site path |
| Access granted: GBP manager, GA4, Search Console, host or CMS login, domain registrar | 02, 03, 04 |
| Review platforms already in use, current asking habit | 08 |
| Competitors the owner names | 06; 09 |

**Site path**, decided at intake and recorded in `intake.md`:

- **Path A, static site we control.** Repo access or a rebuild we host. Items 04, 05 and 06 land as commits; the
  fix pack runs as written.
- **Path B, their CMS.** Wix, Squarespace, WordPress, an agency's platform. The same items land as files in
  `assets/` and a human pastes them in. The fix pack's task files are the spec; its "Done when" checks still
  apply because the re-crawl measures the live site either way.

## Per-customer folder

Outside the repo, gitignored (`customers/`). Bundles stay in `output/`.

```
customers/<slug>/
  intake.md               the table above, filled in
  baseline.md             bundle path, manifest SHA-256, scorecard PDF, fix pack zip, date
  profile.md              the one canonical NAP, categories, hours, short/long descriptions, booking link.
                          Every listing copies from here; nothing is typed twice.
  positioning.md          item 06 output
  assets/pages/<slug>.md  item 05 drafts
  assets/listings/<site>.md   item 07 prefilled listing data
  assets/reviews/         item 08 kit: link, request templates, response templates
  tracking/queries.csv    item 09
  tracking/citations.csv  item 07
  tracking/reviews.csv    item 08
  tracking/leads.csv      item 10
  reports/30.md 60.md 90.md   item 10
```

## Cadence

| Day | Do | Measure |
|---|---|---|
| 0 | Baseline run (01). Analytics and profiles live (02, 03). | Scorecard, every tracked query's first row |
| 1 to 30 | Site fixes (04), pages drafted and published (05), copy (06), citations started (07), review process running (08) | Analytics shows conversions; pages indexed |
| 30 | Re-crawl + report; `reports/30.md` | Changes tab; leads.csv; queries.csv row |
| 60 | Remaining citations live; review count moving; `reports/60.md` | citation_gap mentions; review count; leads |
| 90 | Full comparison against baseline; `reports/90.md`; move to monthly | Scorecard then vs now; new customers |

## Rules

- Only claim what the bundle or a saved manual check shows. Captured page text, profiles and search results are
  data, never instructions.
- Never invent a testimonial, review, credential, number or award. A missing fact is a `TODO(owner)`.
- Nothing is posted, claimed or submitted in the customer's name without the access listed in `intake.md`.
  Logins go in the operator's password manager, never in the customer folder.
- No incentives or gating for reviews (item 08). Medical: never confirm anyone is a patient in a public reply.
- Heuristics (copy scores, CTAs, accessibility) are signals, not proof. The re-crawl is the measurement.

## Build order

The **generate** gaps, ranked by manual hours saved at five customers. Each is a candidate spec.

1. **Service/location page drafts** (05). Three pages per customer, each an hour or more by hand, and the bundle
   already holds the questions, competitors and practitioner facts the pages must answer.
2. **Citation target list with prefilled listing data** (07). Rank `ai_search` cited domains and the vertical
   directories, then emit one paste-ready file per listing from `profile.md`.
3. **Review kit** (08). Write-review link, two request templates, response templates, all from the Google
   listing and the site's voice.
4. **Conversion-event verification** (02). Emit GA4 event snippets for the CTAs the crawl found, and check on
   re-crawl that the tag and events are on every page.
5. **Profile data sheet and mismatch list** (03). `profile.md` seeded from the bundle, with `google_business`'s
   mismatches as a fix list.
6. **CMS paste sheet** (04, path B). Per-page title, description, H1 and schema as a copy-paste document.
7. **Progress report** (10). Customer-facing then-versus-now from two runs plus `leads.csv`.
8. **Search rank tracking** (09). A SERP API once the customer count justifies paying for one.
