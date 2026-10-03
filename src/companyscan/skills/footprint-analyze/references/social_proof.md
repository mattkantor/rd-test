# Social proof

Whether a buyer who reaches the site sees that other customers chose this business, and whether happy customers are
asked to say so. Use the same verdicts and citation shape as [analysis-rubric.md](analysis-rubric.md), and give every
finding a `business_impact` per [business-impact.md](business-impact.md) (loss type usually `trust` or `conversions`).
Finding IDs use a `P` prefix. Put the area in `analysis.json` as `social_proof` with `verdict`, `summary` and
`findings`.

Sources: `technical/social-proof.json` (always present; signals, quoted `examples`, `profiles`, `trustpilot`), the
per-page `visible_text` to confirm examples, and `technical/google_business.json` when present.

- **On-site proof** (`has_proof`): reviews or testimonials a buyer can see. Confirm the quoted examples against the
  page; reject false matches (a quoted phrase in an article, a "Reviews" menu label). Proof on the homepage or the main
  service/pricing page matters most; proof only on a deep page is weak.
- **Asks** (`has_ask`): a link or prompt to leave a review, share a testimonial or refer someone.
- **Google**: `google_business.json` with `found: false`, or found with no reviews, means a buyer who checks Google sees
  no reviews. When the file is absent, Google wasn't checked: say so and don't judge it.
- **Trustpilot**: only what the site shows (`trustpilot.widget`, `profile_link`, `score_text`). Nothing was fetched
  from Trustpilot; never state a TrustScore except as quoted from the page.

Verdict:
- `PASS`: real proof on the homepage or a core page, an ask somewhere a customer will see it, and Google reviews when
  Google was checked.
- `WARNING`: proof but no ask; an ask but no proof; proof only on deep pages; or the site is fine but Google has no
  reviews.
- `FAIL`: no reviews or testimonials anywhere on the site and no ask, or no on-site proof with no Google reviews.

Recommend the smallest fixes that matter: show two or three real, attributed quotes on the homepage and the main
service page; add a "Leave us a Google review" link (from the Google Business Profile); add a referral prompt on the
contact page. Never suggest inventing testimonials or adding review markup without real reviews.
