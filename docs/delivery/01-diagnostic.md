# 01 Baseline Find / Trust / Choose diagnostic

## Outcome

A checksummed run that shows where buyers fail to find, trust or choose the business, and the scorecard that
puts a dollar figure on it. Every later measurement compares against this run.

## Inputs

- Site URL. From intake: company name, aliases, category, location, ICP, practitioners, place ID, known
  profiles, LTV and new customers wanted.

## Steps

1. **exists** Scan with every dimension and the intake facts:
   ```sh
   companyscan scan https://example.com --max-pages 200 \
     --company-name "Name" --category "dentist" --location "Austin, TX, USA" \
     --icp "families choosing a dentist near Austin" --place-id ChIJ... \
     --person "Dr. A" --known-profile https://facebook.com/... \
     --dimension security --dimension llm_reputation --dimension ai_search \
     --dimension citation_gap --dimension answer_coverage --dimension practitioners \
     --dimension google_business --json
   ```
   Or in the UI: add the site with the same fields, tick all dimensions, **Crawl**. The UI stores the place ID
   and question sets so re-crawls stay comparable.
2. **exists** **Generate report** (or the CLI report flow). Verify `analysis/analysis.json` was written.
3. **exists** Set LTV and new customers wanted on the site's edit page, then download the **Customer scorecard**
   PDF and the **Fix pack (.zip)**.
4. **manual** Record `baseline.md`: bundle path, `manifest.json` SHA-256, scorecard and fix pack filenames, date.
5. **manual** Read the report's business impact ranking and write the engagement order into `intake.md`. 02 and
   03 come first regardless.

## Deliverables

- `output/<host>-<timestamp>/` bundle with `analysis/`
- `customers/<slug>/baseline.md`
- Scorecard PDF (sent to the customer), fix pack zip (ours)

## Done when

- Exit code 0 or 1 with the limits noted in `baseline.md`. A cross-origin redirect means rerun on the right origin.
- `google_business` has `found: true` (or `baseline.md` says the listing is unclaimed, feeding 03).
- Question sets exist for this profile, so 09 and 10 can reuse them.
