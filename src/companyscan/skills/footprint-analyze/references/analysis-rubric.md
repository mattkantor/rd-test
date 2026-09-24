# Evidence-based analysis rubric

## Evidence and verdicts

- `OBSERVED`: verbatim captured text, link, header or structured value.
- `EXTRACTED`: normalized observation with preserved provenance.
- `INFERRED`: reasoned interpretation with confidence and supporting evidence.
- `UNKNOWN`: insufficient evidence, including collection failure. No invented completion.

Verdicts are findings, not scores:
- `PASS`: captured evidence clearly answers the question or satisfies the stated criterion within corpus scope.
- `WARNING`: ambiguity, weak support, or a material inconsistency that needs qualification.
- `FAIL`: explicit captured evidence contradicts a stated criterion, or adequate coverage demonstrates a specific absence. Name the criterion and explain coverage. A crawler block can fail an access-policy criterion without implying business failure.
- `UNKNOWN`: capture missing, unavailable, unusable, stale beyond task needs, or inadequate to assess.

Use `high`, `medium`, `low` confidence with a reason. Do not treat scanner heuristic confidence values as calibrated probabilities. Marketing claims are observations of what the company says, not independent proof. Testimonials/case studies may be evidence offered by the company; label whether independently verified (usually unknown).

Citation shape: `{artifact, source_url, locator, quote, retrieved_at}`. Example locator: `headings[0].text`, `visible_text paragraph containing …`, or `documents[0].name`. Quotes must match captured text. For absence/technical findings cite the checked fields and state which pages were covered; a made-up quote is never needed.

## Three comprehension passes

Answer every question separately for `website`, `social`, `combined`:

1. What company is this?
2. What does it sell?
3. Who is its ideal customer? Separate explicit from inferred ICP.
4. What problem does it solve?
5. Where does it operate?
6. Why should someone choose it?
7. What evidence supports those claims?
8. What facts are ambiguous?
9. What facts appear contradictory?
10. What important questions cannot be answered?

For each: answer (or null), evidence kind, verdict, confidence/reason, citations. Do not confuse serving a location with merely mentioning it, audience with followers, different services with contradictions, or a founder's identity with the company entity. Separate legal entity, brand, parent/subsidiary and individual practitioner if evidence allows; otherwise flag ambiguity.

Website corpus: captured first-party pages and technical observations. Social corpus: captured, reviewed, likely official profile content and any explicitly recorded social search evidence, clearly distinguishing snippets. Combined corpus: both, preserving source attribution. Website links to accounts do not become social messaging evidence. `DISCOVERED_NOT_COLLECTED` yields `UNKNOWN` for social comprehension, even when network ownership seems likely. An empty `recent_content` array means no posts collected, not no posts published.

The matrix has rows Company, Services, ICP, Location, Differentiator, Proof and columns Website, Social, Combined. Use full verdict labels for accessibility and clarity. Tie every cell to one or more comprehension answers. Resolve combined verdicts from all available evidence; a clear website does not erase a conflicting profile. Missing social capture does not automatically invalidate clear website answers, but combined coverage must be qualified.

## Findings to evaluate

- Identity: brand/legal identity, what it is, structured entity candidates and references.
- Offer: products/services, prices if stated, buyer and problem, value proposition.
- Audience: explicit ICP, inferred ICP, industries, organization/person types, conflicting audience cues.
- Messaging: primary promise, differentiators, claims, proof, primary CTA and consistency.
- Geography: location versus service area, addresses, conflicting/unstated coverage.
- Surfaces: website versus each captured network; audience differences may be intentional. Do not assume they are mistakes without context.
- Machine comprehension: entity links, service specificity, geography, person/company relationships, JSON-LD syntax versus semantics, canonical/noindex observations, declared crawler rules and HTML text availability.

Keep distinct: declared robots access, observed HTTP retrieval by CompanyScan, actual access by named bots, search indexing, and AI inclusion. Only the first two are observed by this scanner. Short HTML extraction may indicate a JavaScript site or simply a short page; do not assert which without evidence.

## Deliverables

`report.md`: company/audience summary, claims and proof, corpus coverage, evidence-backed findings, comprehension matrix, ambiguity/contradiction/unanswered-question lists, and prioritized recommendations if warranted. Include all ten answers per corpus, either inline or linked to `analysis.json`. Keep it readable for a company owner.

`analysis.json`:

```json
{
  "schema_version": "1.0",
  "source_manifest": {"path": "manifest.json", "sha256": "actual hash"},
  "analyzed_at": "UTC ISO timestamp",
  "coverage": {"website": {}, "social": {}, "limitations": []},
  "facts": [],
  "comprehension": {"website": [], "social": [], "combined": []},
  "matrix": [],
  "findings": [],
  "recommendations": []
}
```

Finding: `{id, title, criterion, severity, kind, observation, interpretation, confidence, confidence_reason, evidence, coverage_limits}`. `severity` is a verdict label, not a numerical rating. Each recommendation references finding IDs. Each comprehension answer includes `question_id` 1–10, `question`, `answer`, `kind`, `verdict`, `confidence`, `confidence_reason`, `evidence`. Matrix row: `{dimension, website, social, combined, answer_refs}`; answer references identify both corpus and question ID. Facts include `{id, statement, kind, confidence, evidence}`; unknown statements explain the missing evidence.
