# Marketing copy rubric

Judges whether the captured copy sells, not just whether it is accurate. Same verdicts, evidence kinds and citation shape as [analysis-rubric.md](analysis-rubric.md). Finding IDs use a `C` prefix.

## Scope

Review every core page in full: homepage, service/offer pages, process pages, location/landing pages, pricing, testimonials, contact. Sample at least 10 blog posts (or all if fewer), spread across dates and post types; record which were reviewed. Exclude error pages and duplicates. Quote only captured text. Copy the company did not write (client reviews, embedded quotes) counts as proof, not as the company's voice.

## 1. Customer-directed persuasion

The copy should work on the reader's motives first and establish credibility second.

Record each lever with a quote and its position (section number counted from the top of the page, and whether it falls in the first screen: H1, subhead and first CTA):

| Group | Levers |
|---|---|
| Customer-directed (lead with these) | loss aversion / cost of inaction, pain and agitation, curiosity gaps and open loops, urgency, scarcity, reader-centred outcomes ("you" framing), contrast/before-after, anchoring, risk reversal |
| Credibility (follow with these) | authority, credentials, stats, client logos, social proof, testimonials, case studies, bandwagon |

Verdicts per core page:
- `PASS`: the first screen carries at least one customer-directed lever, and the first credibility element comes after it.
- `WARNING`: credibility or company description leads ("We are…", stats before any pain or outcome), or only one or two lever types appear anywhere on the page.
- `FAIL`: no customer-directed lever on the page at all.

Also report:
- **Reader focus.** Count second-person words (you, your, you're) against first-person company words (we, our, us). Say whether the opening sentence is about the reader or the company.
- **Truthful pressure.** Urgency or scarcity with no stated basis (fake countdowns, "only 2 spots left" with no reason given) is a `WARNING` for credibility risk. Real constraints, such as limited onboarding capacity stated plainly, are good. Never recommend inventing scarcity.
- **Missing levers.** List the levers that are absent and would fit the offer. Recommend them as messaging options, not as facts.

## 2. ICP clarity and consistency

From the copy alone, extract who each page speaks to: role, company type and size, industry, geography, stage, and trigger situation.
- `PASS`: core pages name the same buyer in concrete terms.
- `WARNING`: the ICP is generic ("businesses", "B2B teams") or shifts between pages without a clear segment structure.
- `FAIL`: pages address conflicting buyers (for example, "enterprise only" on one page and "solo founders" on another).

Show the per-page ICP in a table. Separate explicit statements from inferences.

## 3. Human voice

**Start from the scanner's scores.** Each page JSON has `copy_scores.ai_slop` (0–100; LOW <30, MEDIUM 30–59, HIGH 60+, UNKNOWN under 80 words), and `technical/copy-scores.json` has the site summary, `top_pages` and `skeleton_openings`. These are deterministic heuristics (phrase lists, sentence-length spread, openings shared across pages, placeholder text), not judgments.
- Read the 5 highest-scoring pages in full, plus every HIGH core page. For each flagged signal, **confirm or reject** it with a quote. A shared case-study template, a legitimate em dash habit, or a "Key takeaways" widget is not slop, even when the scanner counts it.
- Report a per-page table: URL, AI slop score and level, top signals, confirmed/rejected.
- Copy each score's `level` exactly as recorded in the page JSON; never relabel it. The bands are fixed: 37 is MEDIUM, not LOW.
- When `copy_scores` is absent (older bundles), say the scores weren't collected and fall back to the manual counts below.

Check whether the copy reads like a person wrote it for a specific reader. These are heuristic signals only. Never state that text *is* AI-generated unless the site says so (an AI-drafting disclosure is an observation). Count per 1,000 words and quote examples:

- Stock AI vocabulary: delve, leverage, seamless, robust, elevate, unlock, empower, streamline, landscape, game-changer, cutting-edge, "in today's fast-paced", "navigate the complexities", "it's important to note", "whether you're … or …".
- Structural tells: "not just X, but Y" / "it's not X, it's Y" contrasts; reflexive groups of three; em-dash density; every section ending in a summary line; headline formulas repeated across posts; "The short answer" / "The honest answer" / "Here's the thing" openers; generic FAQ padding.
- Sameness: uniform sentence length (report the mean and standard deviation of sentence length in words), identical post skeletons, unfilled template tokens ("in Your Area").
- Specificity, the counter-signal: named places, numbers with context, first-hand detail, a distinct opinion. These make copy read as human.

Verdict: `PASS` when tells are rare and specifics are common. `WARNING` when tells cluster (roughly more than 3 per 1,000 words, or repeated skeletons across posts). `FAIL` only when template artifacts or placeholder text appear in published copy.

## 4. Goal direction

Every page should move the reader toward one action.
- Name each page's primary goal (book a call, sign up, read next) and its CTA. `FAIL` if a core page has no CTA or its CTA is broken.
- Trace the section order against a persuasion arc: hook → problem/stakes → solution → how it works → proof → objection handling → CTA. Flag sections that neither advance the arc nor remove an objection ("saying things for the sake of it").
- Check CTA placement: in the first screen, after proof, and at the end. Check that CTA wording names the reader's outcome, not just the action ("See your campaign plan" rather than "Submit").
- Blog posts: does each post end with a CTA relevant to its topic, and do internal links lead to a money page? Links to 404s count against goal direction.

## 5. Marketing bias levers

`copy_scores.marketing_bias` (0–100, same levels) measures how heavily a page **relies on persuasion levers**, not whether it is dishonest. Its breakdown has seven levers: `unsupported_claims` (puffery, absolutes, statistics with no source or before/after), `self_focus` (we/our against you/your), `one_sidedness` (no "not a fit", trade-off or downside anywhere in 300+ words), `pressure` (urgency and scarcity), `fomo`, `loss_aversion` and `authority`.

The score is reliance; your verdict is honesty. For each HIGH page, and the homepage, judge every lever that scored:
- `PASS`: the lever is truthful and backed by proof on the site. Loss aversion that names a real cost, or authority with verifiable credentials, is good copy (§1 recommends both).
- `WARNING`: pressure or FOMO with no stated basis; puffery ("best", "#1", "world-class") with no proof; company-talk crowding out the reader; no balance anywhere on a page asking for a commitment.
- `FAIL`: a claim contradicted elsewhere on the site (price, contract, client count), or scarcity shown to be false.
Quote the scanner's example snippets and check them against the page. Reject false matches, such as a real project "deadline" in a case study.

## Output

In `analysis.json`, add a `copy` object:

```json
{
  "scope": {"core_pages": [], "blog_sample": [], "excluded": []},
  "pages": [{"url": "", "primary_goal": "", "first_screen": "", "levers": [{"lever": "", "group": "customer|credibility", "section": 1, "quote": ""}], "you_we": [0, 0], "icp": "", "arc_gaps": [], "verdicts": {"persuasion": "", "goal": ""}}],
  "icp_consistency": {"verdict": "", "per_page": []},
  "voice": {"verdict": "", "per_1000_words": {}, "sentence_length": {"mean": 0, "stdev": 0}, "examples": []},
  "scores": {"ai_slop": {"median": 0, "high_pages": []}, "marketing_bias": {"median": 0, "high_pages": []},
             "pages": [{"url": "", "ai_slop": 0, "marketing_bias": 0, "confirmed": [], "rejected": [], "lever_verdicts": {}}]},
  "findings": [],
  "recommendations": []
}
```

In `report.md`, add a **Marketing copy** section with: a **Copy scores** table (page, AI slop, marketing bias, top levers, confirmed or rejected), the bias-lever verdicts, a per-page lever table (lever, group, position), the ICP table, voice metrics, findings `C1…`, and rewrite suggestions. Label rewrites clearly as suggestions, and keep them within what the company can truthfully claim.
