# 05 Three high-intent service and location pages

## Outcome

Three pages that each answer one buyer's question ("<service> in <city>") completely enough that search engines,
AI assistants and the buyer all treat it as the answer. These are the pages that bring new visitors; the rest
of the engagement converts them.

## Inputs

- `technical/answer_coverage.json`: the 12 buyer questions and which are `missing` or `partial`.
- `technical/ai_search.json`: buyer questions, the competitors named in answers, cited sources.
- `technical/practitioners.json`: credentials and focus areas with quotes.
- `pages/*.json`: existing service pages, CTAs, internal links.
- Intake: services ranked by margin and demand, locations, contact methods, photos available.

## Steps

1. **manual** Pick the three. Score each service × location pair: buyer questions `missing` for it, named
   competitors answering it, owner's margin ranking, and whether a page already exists (improve before adding).
   Record the choice and the reason in `intake.md`.
2. **generate** Draft each page from the bundle into `assets/pages/<service>-<city>.md`:
   - Title and description within SEO limits; one H1 "<service> in <city>".
   - Opening paragraph that answers the question in two sentences, written for the ICP.
   - A section per buyer question `answer_coverage` found `missing` for this service: cost or range, who it suits
     and who it doesn't, process and timeline, what to expect, how it compares.
   - Proof: the practitioner's relevant credentials with the page's own quotes; `TODO(owner)` for outcomes,
     counts and photos.
   - FAQ with `FAQPage` JSON-LD; `Service` and `LocalBusiness` JSON-LD from `profile.md`.
   - One CTA matching the contact method; internal links to and from the homepage and related pages.
   - Every fact traced to a bundle quote or an intake field. Unknown facts are `TODO(owner)` lines, never filled.
   Until built: **manual** using the same outline.
3. **manual** Owner reviews, supplies the TODOs and photos. Nothing ships with a TODO in it.
4. **manual** Publish (path A commit, path B page builder). Add to the sitemap and request indexing in Search
   Console. Link from the Google Business Profile services where relevant.
5. **manual** Add each page's question to `tracking/queries.csv` (item 09).

## Deliverables

- `assets/pages/*.md` drafts and the three live URLs

## Done when

- Search Console shows each URL indexed.
- Re-crawl: each page extracted with one H1, valid JSON-LD, LOW slop, a CTA; its `answer_coverage` questions
  `answered`.
- At 60 and 90 days: impressions and clicks for the page's queries in Search Console, and the page appears as a
  cited source or the business is mentioned in `ai_search` answers for that question.
