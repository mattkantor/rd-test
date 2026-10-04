# 09 A fixed set of commercial search queries and AI prompts

## Outcome

The same ten searches and the same buyer prompts measured every month, so item 10 can say "you now appear for
these, you didn't before" with evidence rather than impressions.

## Inputs

- `technical/llm_reputation.json` and `ai_search.json`: the stored buyer question set, rank, mention rate,
  competitors, cited sources.
- Intake: services ranked, locations, named competitors.
- Google Search Console (item 02).

## Steps

1. **exists** AI prompts: the question sets are stored per site and profile and reused by every re-crawl. Don't
   tick **Write new questions on the next crawl** during an engagement; a changed set breaks the comparison.
   The dashboard's **Since last run** and **Changes** tab show rank, mention rate and per-question movement.
2. **manual** Choose about ten commercial queries: "<service> <city>", "<service> near me" (from the city),
   "best <service> <city>", "<vertical> <neighbourhood>", one per item 05 page, plus the branded query. Write
   them in `tracking/queries.csv` with columns: date, query, engine (google, google_maps, bing), position,
   top result, our URL, notes.
3. **manual** Baseline and monthly: search each query in a private window with location set to the customer's
   city (Google: search settings or `&near=`; Maps: pan to the city). Record position of the business's site
   and listing, and the top three results. Thirty minutes per customer per month. Note that positions vary by
   device and exact location, so look for changes that hold over several months.
4. **manual** Add Search Console's impressions, clicks and average position for each query from the
   Performance report once a month to the same row. This is the measured signal; step 3 is the spot check.
5. **generate** Rank tracking through a SERP API, written into the bundle as a dimension, once paying for one
   beats thirty minutes a month times customers. Not at five.

## Deliverables

- `tracking/queries.csv` with a row per query per engine per month
- The stored question sets, untouched

## Done when

- Baseline row for every query exists on day 0.
- Every monthly report (item 10) cites the queries that moved, with the Search Console numbers beside the spot
  check.
