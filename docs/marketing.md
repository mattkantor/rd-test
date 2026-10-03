# Marketing DrGrow

Market the problem, use the scanner as the proof, sell the service as the fix.

## The question we sell

> When someone in your area needs a dentist, why would they choose you?

Don't lead with SEO, AEO, GEO, AI, automation, websites, "digital marketing" or "digital footprint". Those describe how we do the work. The dentist isn't trying to improve a digital footprint. They want to be the dentist people choose.

**Promise:** Become the obvious choice.

**Line underneath:** We analyze how patients discover, evaluate and choose your practice, then fix what's causing them to choose someone else.

**Method:** **Find → Trust → Choose.** A dentist should get it in five seconds.

## The customer-facing report

Keep it short, not a 37-page technical audit. Three questions, then 3–5 specific things costing them patients. We're diagnosing the problem here, not handing over an implementation manual, so don't list 48 recommendations.

| Stage | Question | What it covers | Where the evidence comes from |
|---|---|---|---|
| **Find** | Can patients looking for your services discover you? | Searches, Maps, AI answers, competitors, gaps | `ai_search`, `llm_reputation`, `citation_gap`, `google_business`, discovery/robots/sitemaps, `llms.txt` |
| **Trust** | When they find you, do you look like the safe choice? | Reviews, recency, ratings, third-party presence, consistency, credentials, authority, competitor comparison | `google_business`, `practitioners`, social profiles, `llm_reputation` |
| **Choose** | Once they're considering you, do you give them a reason to book? | Messaging, differentiation, services, social proof, CTAs, booking friction, mobile | Page copy scores, CTAs, `answer_coverage`, `jev_copy`, accessibility, technical checks |

The customer scorecard (`companyscan` **Generate report** → scorecard PDF) is the current customer-facing format. It leads with loss, groups every area under Find, Trust or Choose (`scorecard.STAGES`), and ends with the offer as **Get chosen** (the fix) and **Stay chosen** (the monthly service).

**Honesty rule:** only claim what's in the bundle. The scanner records where the practice ranks in AI answers against the competitors those answers name (`llm_reputation` / `ai_search`) and the practice's own Google rating and reviews. It doesn't record Google search or Maps rankings, or competitors' ratings. So a line like "three practices with weaker ratings come up ahead of you" needs a manual check first, saved with the evidence. Copy scores, CTAs and accessibility checks are heuristics, not proof. See the evidence labels in the README.

## The offer

Don't ask "Would you like us to do your SEO?" Ask "Do you want us to fix this?"

- **$5,000: Become the Chosen Practice.** Fix the major Find/Trust/Choose problems from the assessment: Google Business Profile, website and service pages, review system, citations, conversion, AI visibility, tracking. The diagnosis decides the work. Nobody gets a generic SEO checklist.
- **$500/month: Stay the Chosen Practice.** Re-scan regularly and keep watching competitive position, reputation, AI visibility and conversion. Make smaller improvements, create and tune content, maintain profiles, grow reviews, and report actual patient acquisition.

The $5K fixes the system. The $500 keeps improving it. The number we ultimately report is new patients per month.

How the work gets done after a yes, item by item: [docs/delivery/README.md](delivery/README.md).

## Acquisition: scored, personalized outbound

The scanner is an internal lead-scoring engine as much as a lead magnet. Find out who has the problem before you contact anyone.

1. Build a list of about 500 independent dental practices (CSV with a `domain` column).
2. Scan them all: `companyscan batch prospects.csv --domain-column domain --output ./output/<list-name> --json`.
3. Rank by opportunity:
   - **Already excellent:** don't call.
   - **Mediocre site but strong on Maps and reviews:** lower priority.
   - **Good practice, weak online presence, competitors clearly ahead:** call now.
4. Generate the scorecard for the call-now group and lead with it.

**Opener:**

> We ran an analysis of how your practice shows up when someone in your area is choosing a dentist. We found a few places where you're losing visibility to nearby practices. Can I send it over?

**Specific version** (use only facts from the bundle or a saved manual check):

> Dr. Patel, you're rated 4.8, which is great. But when we looked at how someone searching for a dentist in [area] would find you, three practices with weaker patient ratings come up ahead of you. We found a couple of reasons why. We put together a short report if you'd like to see it.

Compare that with "Want more leads?"

## Content: publish the aggregate findings

The scans are proprietary data. Publish what they show in aggregate, not "5 SEO Tips for Dentists":

- "We analyzed 100 Toronto dental practices. Here's what separates the practices patients find from the ones they don't."
- "A 4.9-star dentist with 200 reviews wasn't showing up when we asked AI where to go. Here's why."
- "We searched for 50 dentists the way a new patient would. Here's where practices lose them."

Use these for LinkedIn posts, dental-industry articles, webinars, association talks, videos, benchmark reports and PR. They show we understand how practices win patients, not just how to run marketing tools. Anonymize practices unless they agree to be named.

## One-line summary

Find → Trust → Choose is the method. The scanner proves where they're losing patients. The $5K engagement fixes it. The $500/month keeps them competitive. It's a shelf-space business for local services: we measure and improve the places where the buying decision actually happens.
