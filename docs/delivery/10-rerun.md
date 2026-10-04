# 10 Rerun the diagnostic at 30, 60 and 90 days and track leads and customers

## Outcome

Evidence that the engagement produced customers, not rankings: each run compared with the baseline, each lead
logged with its source, each new customer counted. This is the number we report and the reason the monthly fee
continues.

## Inputs

- Baseline run and each **Re-crawl + report** run.
- GA4 key events (item 02), `tracking/queries.csv` (09), `tracking/reviews.csv` (08), `tracking/citations.csv`
  (07).
- The owner: which leads became customers, and their value.

## Steps

1. **exists** At 30, 60 and 90 days: **Re-crawl + report** on the site page. It uses every dimension, the stored
   question sets and the stored place ID, so the comparison is like for like. Download the new scorecard.
2. **exists** Read the **Changes** tab and the Overview tiles' deltas and sparklines: AI rank and mention rate,
   answered questions, Google rating and reviews, SEO pass rate, JSON-LD share, analytics coverage,
   accessibility barriers, cited sites that came and went.
3. **manual** `tracking/leads.csv`, filled weekly from GA4 and the owner: date, source (organic search, Maps,
   AI assistant, directory, referral, direct, ads), type (call, form, booking, walk-in), became customer (yes,
   no, pending), value. Ask the owner to ask every new customer "how did you find us" and write it down; it's
   the only source attribution that survives phone calls.
4. **manual** `reports/<day>.md`, one page, for the customer: new customers and leads this period by source,
   the three changes that mattered with their evidence (a query that moved, an AI answer that now names them,
   reviews added), what's in progress, what we do next. Lead with customers, then leads, then visibility. Never
   lead with a score.
5. **generate** Draft that report from the two runs' snapshots, `leads.csv`, `queries.csv` and `reviews.csv`,
   in the scorecard's Find / Trust / Choose framing. Until built: **manual**.
6. **manual** At 90: full scorecard then versus now, the quarter's customer count against the "new customers
   wanted per year" goal, and the Stay chosen plan for the next quarter: which queries and questions still
   miss, which findings are open, what content comes next.

## Deliverables

- Three runs with reports; `tracking/leads.csv`; `reports/30.md`, `60.md`, `90.md`

## Done when

- Every tracked metric has a baseline value and a 90-day value, and the report says which moved and which
  didn't.
- `leads.csv` has a source for every lead and a yes/no for every lead older than 30 days.
- The customer can say how many new customers the quarter produced and where they came from.
