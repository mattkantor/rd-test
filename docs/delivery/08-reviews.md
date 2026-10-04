# 08 A legitimate review-generation process

## Outcome

Every customer is asked for a review, the same way, at the right moment, on the platform that matters for the
vertical. Reviews are answered. The site shows them. Review count and recency are the Trust signal buyers and
engines weigh most.

## Inputs

- `technical/google_business.json`: rating, review count, sample reviews.
- `technical/social-proof.json`: whether the site shows reviews or testimonials and whether it asks.
- Intake: platforms in use, current asking habit, how the business knows a job is finished, who talks to the
  customer last.

## Steps

1. **manual** Pick platforms. Google always. One vertical platform:

   | Vertical | Second platform |
   |---|---|
   | Medical, dental, plastic surgery | Healthgrades (or RealSelf for aesthetic) |
   | Legal | Avvo |
   | Wedding officiant | The Knot or WeddingWire (couples check these first) |
   | Auto care | Yelp |

2. **generate** Review kit in `assets/reviews/`: the Google write-review short link (from the place ID), a QR
   code for it, two request templates (SMS under 160 characters, email) in the site's voice, a template for
   the second platform, and response templates for 5-star, mixed and negative reviews. Until built: **manual**.
3. **manual** Design the ask. Trigger: the moment the job is done (appointment end, ceremony day after, car
   handed back). Channel: SMS first, email second. Sender: the person the customer dealt with. Cadence: ask
   once, one reminder after a week. Write it as a three-line standard operating procedure the staff will
   actually follow, and put it in `assets/reviews/process.md`.
4. **manual** Rules, written into the process file:
   - Ask everyone. Asking only happy customers (gating) violates Google's policy and the FTC's 2024 rule on
     reviews. No incentives, discounts or draws for reviews on Google; check each other platform's policy.
   - Never write, edit or seed a review. Never post a review from staff or family.
   - Medical: a public reply must never confirm the reviewer was a patient or mention any treatment.
   - Reply to every review within a week. Negative: acknowledge, take it offline, never argue.
5. **exists** Fix pack "Show and ask for social proof" task puts real reviews and the ask on the site (never
   invented testimonials). Path B: paste the review widget or quoted reviews with attribution.
6. **manual** Baseline row in `tracking/reviews.csv` (date, platform, count, rating) and a row each month.

## Deliverables

- `assets/reviews/` kit and `process.md`
- Reviews displayed and asked for on the site

## Done when

- The process ran: staff can say who asks, when and how; first requests sent and logged.
- Re-crawl `social-proof.json` is PASS (shows and asks).
- `tracking/reviews.csv` shows count rising month over month; `google_business` review count at 90 days above
  baseline with recent dates.
