# 03 Google, Bing and core business profiles

## Outcome

One canonical name, address, phone, hours and category set (`profile.md`), and the Google, Bing and Apple
listings match it exactly. Mismatches are the commonest reason a strong business loses Maps visibility.

## Inputs

- `technical/google_business.json`: `found`, mismatches (name, phone, website, postal code, street number),
  category, hours, status, rating, review count.
- Site JSON-LD and `tel:` links from `pages/*.json`.
- Intake: GBP access, booking link, services, practitioners.

## Steps

1. **generate** Seed `profile.md` from the bundle: NAP from JSON-LD and footer text, hours, services, a short
   (under 250 characters) and a long (under 750) description drafted from the site's own copy, booking link,
   practitioner list. `google_business`'s mismatch list becomes the fix list at the top. Until built: **manual**
   from the dashboard's Google listing card.
2. **manual** Google Business Profile. Claim or get manager access. Fix every mismatch. Set the primary category
   (the one buyers search, not the one the owner likes) and secondary categories. Add services with
   descriptions, hours including holidays, the booking link, 10 or more real photos (exterior, interior, team,
   work), the long description, attributes. Answer existing Q&A. Turn on messaging only if someone will answer.
3. **manual** Bing Places: import from Google Business Profile, then check the result. Apple Business Connect:
   claim and match `profile.md`.
4. **manual** Vertical core profiles that act like a primary listing, same data:

   | Vertical | Also treat as core |
   |---|---|
   | Medical, dental, plastic surgery | Healthgrades, Zocdoc (if booking), insurer directories the practice is in |
   | Legal | Avvo, state bar directory entry, Justia |
   | Wedding officiant | The Knot, WeddingWire, Zola |
   | Auto care | Yelp, Nextdoor business page |
   | Any | Yelp, Facebook page about section, Nextdoor |

5. **manual** Log each profile in `tracking/citations.csv` (platform, URL, status, date, who holds the login).

## Deliverables

- `customers/<slug>/profile.md`
- Google, Bing, Apple and vertical core listings matching it

## Done when

- Re-crawl `google_business.json` shows `found: true` and no mismatches.
- Every core listing in `tracking/citations.csv` is `live` with the same NAP character for character.
