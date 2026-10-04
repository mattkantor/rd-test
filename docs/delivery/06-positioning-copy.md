# 06 Homepage and service-page positioning and copy

## Outcome

A buyer landing on the homepage knows within five seconds who this is for, what they get, and why this
business over the competitors the assistants name. The copy is specific, truthful and asks for one action.

## Inputs

- `technical/ai_search.json` and `llm_reputation.json`: competitors named, how the business is described.
- `copy_scores` and `jev_copy` per page; the report's copy pass and persuasion findings.
- Fix pack tasks for AI slop and truthful persuasion.
- Intake: ICP, services, practitioners, the owner's own competitors and reasons customers pick them.

## Steps

1. **manual** Positioning interview on the kickoff call: who they're best for, who they turn away, what
   customers say when they explain why they chose them, what the named competitors say about themselves (read
   their homepages). Write `positioning.md`: one sentence of positioning, three proof points each tied to a
   fact we can show, the one action the homepage asks for. The Claude Code skills `obviously-awesome` and
   `storybrand-messaging` are available for this step.
2. **exists** Fix pack rewrites: the AI slop task and the truthful persuasion task cover the key pages' existing
   copy (outcome, proof, cost of inaction, credentials, one CTA; puffery toned down).
3. **generate** Homepage draft from `positioning.md` plus the bundle: hero (positioning sentence, proof line,
   CTA), the three proof points with their evidence, services linking to item 05 pages, practitioner strip
   from `practitioners.json`, social proof block (item 08), one CTA repeated. Until built: **manual** with the
   same outline.
4. **manual** Owner review for truth, then publish. Path B: paste section by section.
5. **manual** Service pages: apply the same hero pattern to each existing service page; item 05 pages already
   follow it.

## Deliverables

- `customers/<slug>/positioning.md`
- Homepage and service pages live with the new copy

## Done when

- Re-crawl: homepage and service pages score LOW slop and at most MEDIUM bias, one CTA detected per page.
- Report copy pass: persuasion levers present, ICP consistent, no unsupported claims flagged.
- The 90-day `ai_search` branded answer describes the business the way `positioning.md` does.
