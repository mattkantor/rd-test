# 07 About ten high-value external profiles and citations

## Outcome

The business is present, with identical NAP, on the sites search engines and AI assistants actually consult for
this market, plus the directories buyers in this vertical trust. Item 03 covers the core listings; this is the
next ten.

## Inputs

- `technical/citation_gap.json`: cited pages that don't mention the business, grouped by domain.
- `technical/ai_search.json` `scores.sources`: the domains cited most across buyer answers.
- `social/discovered.json`: profiles already found.
- `profile.md` from item 03.

## Steps

1. **generate** Target list, ranked: domains from `scores.sources` and `citation_gap` where a business can be
   listed or mentioned (directories, review sites, associations), then the vertical table below, then local
   (chamber of commerce, BBB, city or neighbourhood directories, local news "best of" lists). Drop domains the
   business is already on (`discovered.json`). Mark each as **listing** (we can create it), **earn** (needs
   outreach: an association page, a news mention) or **skip** (competitor sites, aggregators with no listing
   path). Until built: **manual** from the dashboard's AI search cited-sites table.
2. **manual** Vertical table, used when the ranked list has fewer than ten listing targets:

   | Vertical | Directories buyers and engines use |
   |---|---|
   | Medical, dental, plastic surgery | Healthgrades, Vitals, WebMD, RealSelf (aesthetic), Zocdoc, insurer directories, state licence lookup |
   | Legal | Avvo, Justia, FindLaw, Lawyers.com, Super Lawyers, state bar, Martindale |
   | Wedding officiant | The Knot, WeddingWire, Zola, Thumbtack, Bark, local wedding venue vendor lists |
   | Auto care | Yelp, Carfax Service Shops, RepairPal, Angi, Thumbtack, Nextdoor |
   | Any | Yelp, Facebook, Nextdoor, BBB, chamber of commerce, Apple, Foursquare, Yellow Pages, Manta |

3. **generate** One file per target in `assets/listings/<site>.md`, prefilled from `profile.md` in that site's
   field order and length limits (name, categories, short and long description, hours, services, photos to
   upload, booking link). Until built: **manual** copy from `profile.md`.
4. **manual** Create or claim each listing with a customer-owned login. Paste from the file. No variations in
   NAP, ever. Record platform, URL, status, date and login owner in `tracking/citations.csv`. **Earn** targets
   get a one-paragraph outreach note and a follow-up date.
5. **manual** Add the live profile URLs to `--known-profile` (or the site's edit page) so the next run's
   identity profile and `citation_gap` recognise them, and to the site's `sameAs` JSON-LD.

## Deliverables

- `assets/listings/*.md`
- `tracking/citations.csv` with about ten new rows

## Done when

- Ten rows `live` in `tracking/citations.csv`, NAP identical to `profile.md`.
- Re-crawl `citation_gap.json`: previously missing domains now mention the business; `discovered.json` lists
  the new profiles.
- 90 days: the business appears in `ai_search` buyer answers it was absent from, or the cited domains include
  ones we listed on.
