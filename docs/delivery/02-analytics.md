# 02 Analytics and conversion tracking

## Outcome

Every page loads one analytics tag behind consent, each way a customer contacts the business is a conversion
event, and Search Console and Bing Webmaster Tools are verified. Without this, item 10 has no numbers.

## Inputs

- `technical/measurement.json`: pages without analytics, tag manager, consent tool.
- Page CTAs and `tel:`, `mailto:` and booking links from `pages/*.json`.
- Intake: contact methods, GA4 access, site path.

## Steps

1. **manual** Create or get access to a GA4 property and Google Tag Manager container owned by the customer's
   Google account (not ours), and Google Search Console and Bing Webmaster Tools for the domain.
2. **exists** Fix pack task 1 adds the tag and a consent banner to every page (path A). Path B: the task file
   says what to add; paste the tag through the CMS's analytics or custom-code setting.
3. **manual** Define conversions from the contact methods: `phone_click` on `tel:` links, `form_submit`,
   `booking_click` on the scheduling tool's link, `directions_click`, `email_click`. Mark each as a key event in
   GA4. Send them through GTM so they're editable without a deploy.
4. **generate** Emit the GTM trigger and GA4 event definitions for the CTAs and `tel:` links the crawl found,
   per page, so step 3 is import rather than clicking.
5. **manual** Verify: open GA4 DebugView, trigger each event on the live site, confirm it arrives. Submit the
   sitemap in Search Console and Bing. Record the property ID and the verification date in `intake.md`.
6. **generate** On re-crawl, flag any page in `measurement.json` without the tag and compare against the baseline.

## Deliverables

- GA4 property with key events; GTM container; Search Console and Bing verified
- `intake.md` updated with IDs and verification date

## Done when

- Re-crawl `measurement.json` shows the tag on every page and a consent tool present.
- Each conversion fired once in DebugView and shows in GA4 realtime.
- Search Console shows the sitemap as processed.
