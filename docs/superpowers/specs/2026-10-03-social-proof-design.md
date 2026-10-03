# Social proof check: reviews, testimonials and the asks for them

## Goal

Make sure every site is checked for social proof. A buyer should see reviews or testimonials on the site, and there
should be a way for customers to leave a review, a testimonial or a referral. Off-site, Google reviews count; a
Trustpilot widget, profile link or score shown on the site counts as on-site proof. No Google listing means no Google reviews, which is a failure.

Agreed with the user:
- On-site proof **or** an ask is the minimum; both is a pass.
- Google: no listing found, or a listing with no reviews, counts against social proof.
- Trustpilot is checked **on the site only**: its widget, links to the business's Trustpilot profile, and Trustpilot
  scores printed on the page. No request ever goes to Trustpilot (no API, widget endpoint or profile page) for now.

## 1. On-site check: `technical/social-proof.json` (always written, no network)

Built in `scan/social_proof.py` from the captured pages, beside `aeo` and `social-preview` in `scan/technical.py`.

Per page, the signals found (each with the page URL and a short quoted example ≤ 200 characters):

**Proof shown**
- `json_ld_reviews`: JSON-LD `Review` or `AggregateRating` (from `json_ld.types` / `testimonials`).
- `testimonial_section`: a heading matching `testimonial|what (our )?(clients|customers) say|reviews|kind words|success
  stories`, or the page classified `testimonial`.
- `attributed_quote`: a quotation candidate followed by an attribution (`— Name` / `Name, Role`).
- `review_widget`: a script or iframe from a known review platform: Trustpilot (`widget.trustpilot.com`), Google reviews
  embeds, Elfsight, Birdeye, Podium, Yotpo, Reviews.io, Judge.me, Stamped, Okendo, Yelp, G2, Capterra, Clutch.

**Ways to give it**
- `review_link`: a link to leave a review: `search.google.com/local/writereview`, `g.page/r/…/review`,
  `trustpilot.com/evaluate/…`, `yelp.com/writeareview`, `g2.com/…/reviews/new`, `clutch.co/…/review`, or link text like
  "leave a review", "write a review", "review us".
- `testimonial_ask`: link or button text like "share your experience", "submit a testimonial", "tell us how we did".
- `referral_ask`: "refer a friend", "referral program", "referrals" in a link, button or heading.

**Profile links**: links to the business's review profiles (Google Maps place, `trustpilot.com/review/<domain>`, Yelp
`biz`, G2, Capterra, Clutch), recorded as profiles, not as proof.

**Trustpilot on the site** (`trustpilot` in the summary): `widget` (a `widget.trustpilot.com` script, or an element
with class `trustpilot-widget`, which the extractor now records per page as `pages/*.json` → `trustpilot_widgets`:
its `data-businessunit-id`, `data-template-id` and `data-style-height`), `profile_link` (a link to
`trustpilot.com/review/…`), `review_link` (`trustpilot.com/evaluate/…`, also a `review_link` signal), and
`score_text` (visible text naming Trustpilot within a sentence that also holds a rating, TrustScore or review count,
e.g. "Rated 4.8 / 5 on Trustpilot"; quoted as found, never parsed into a score). A widget counts as a `review_widget`;
score text counts as proof.

Summary fields: `has_proof`, `has_ask`, `pages_with_proof`, `signals` (counts by kind), `examples` (≤ 10), `profiles`,
`trustpilot` (above), and `status`: `PASS` (proof and ask), `WARNING` (one of them), `FAIL` (neither).
Heuristic and labelled `INFERRED`; `limitations` says HTML only, widgets that load reviews by JavaScript are seen as
widgets, not counted as reviews.

## 2. Google counts toward social proof

No new fetch: `google_business` already records `found`, `reviews.rating` and `reviews.count`. The judgment combines
them (report rubric and dashboard): not found, or found with no reviews, is a social-proof FAIL item ("No Google
reviews: buyers who check Google see nothing"). Found with reviews is proof.

## 3. Where it shows

- **Dashboard**:
  - A **Social proof** tile: on-site verdict as the value, sub-line "Google 4.8★ (84) · Trustpilot widget" or "No
    Google reviews", level from the worst of on-site and Google. Key metric `proof_pages` (pages with proof).
  - The ✓/✗ row gains **Reviews on site** and **Review link**.
  - New trended metric: `proof_pages`.
  - The Site-wide tab gets a Social proof card listing signals with their quoted examples and pages.
  - Anomaly: "No social proof on the site" (FAIL) or "No way for customers to leave a review or referral" (WARNING),
    and "No Google reviews".
- **Report**: `references/social_proof.md` rubric (always applies; the scanner always writes the file), judging the
  on-site signals with Google and Trustpilot together. Area key `social_proof` in `analysis.json`.
- **Scorecard**: `social_proof` belongs to the **Trust** stage, with `WHY["social_proof"]`: "Buyers trust other
  customers more than anything you say about yourself. Reviews and testimonials where they decide, and an easy way
  for happy customers to leave one, are what tip them your way."
- **Fix pack**: task **Show and ask for social proof** (`social-proof`), created when the on-site status isn't PASS
  or Google has no reviews:
  - Add a testimonials section on the homepage and services or pricing page from quotes already on the site (with
    their attribution); none on the site: `TODO(owner): two or three real customer quotes with name and role`.
  - Add a "Leave us a review" link to the Google write-review URL built from `place_id` when known
    (`https://search.google.com/local/writereview?placeid=<id>`), else `TODO(owner): Google review link`; and to the
    Trustpilot `evaluate` URL when the site already links to its Trustpilot profile.
  - Add a referral or "share your experience" prompt on the contact and thank-you pages.
  - Don't: invent testimonials, names, ratings or review counts; add `AggregateRating` markup without real reviews.
  - Off-site (OWNER-TODO): "Get a Google Business Profile and ask your last 10 customers for a review" when Google has
    no listing or no reviews.

## Testing

- `scan/social_proof.py`: fixture pages for each signal kind, none, proof-only (WARNING), ask-only (WARNING), both
  (PASS); quoted examples capped and stripped; the homepage of the real bundle shape (quotes without JSON-LD) finds
  `attributed_quote`.
- Extractor: a `.trustpilot-widget` div records its data attributes.
- Trustpilot on the site: widget script, widget div, profile link, evaluate link and score text each detected; a
  sentence naming Trustpilot without a rating isn't score text. The check never makes a network request.
- Dashboard: tile, ✓/✗ items, anomaly text, "No Google reviews" when `google_business.found` is false.
- Scorecard: `social_proof` lands in Trust. Fix pack: task created/skipped, write-review link from `place_id`, no
  invented quotes.

## Out of scope

Any request to Trustpilot (API, widget endpoint or profile page) and a stored Trustpilot ID; reading reviews from Yelp,
G2, Capterra or Clutch (only links and widgets are detected); judging review sentiment; rendering JavaScript widgets.

## Docs

README: the social-proof report in the bundle layout and the checks list. `docs/output-schema.md`:
`technical/social-proof.json` and `pages/*.json` `trustpilot_widgets`.
