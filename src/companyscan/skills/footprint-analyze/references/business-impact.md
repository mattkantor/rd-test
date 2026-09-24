# Business impact layer

Owners don't care that a link returns 404. They care that a ready-to-buy prospect clicked it and left. Every finding (`F…` and `C…`) gets a `business_impact` that translates the defect into what the business is losing, told from the prospect's side.

## Rules

- **Speak about customers and money, not the defect.** Name who hits the problem (a blog reader, a buyer comparing agencies, someone ready to book) and what they do next (leave, hesitate, distrust, never find you). Leave jargon out of the headline.
- **One loss type per finding**, whichever is primary:

  | `loss_type` | What the business loses |
  |---|---|
  | `leads` | People who would have enquired never do |
  | `conversions` | People who were interested don't book or buy |
  | `deal_value` | Deals close smaller or get negotiated down |
  | `sales_cycle` | Deals stall, or buyers delay until later |
  | `trust` | Buyers discount the claims or doubt the company |
  | `visibility` | Search engines, AI assistants or referrals surface the company less, or describe it wrongly |
  | `wasted_effort` | Sales time or content spend produces nothing |

- **Magnitude** is `high`, `medium` or `low`, with a reason. Base it on where the problem sits in the buying journey (closer to the buying decision means higher), how many pages or visitors it touches, and whether it undercuts the company's main promise.
- **Impact is `INFERRED`.** Never invent traffic, conversion rates or revenue. To show scale, you may use figures the company itself publishes (its prices, contract terms, claimed results), labelled as the company's figures, for example "at the site's own $5,200/month price, one lost client is…". If no such figures exist, describe the loss without numbers.
- **Irony matters.** When a defect contradicts what the company sells (a copywriting agency with template copy, a deliverability firm with broken email), say so. That is usually what makes it expensive.
- **PASS findings** get a `protects` framing: what the strength is protecting, and why to keep it. **UNKNOWN findings** get a `risk you can't see` framing.

## Output

Add this to each finding in `analysis.json`:

```json
"business_impact": {
  "headline": "Readers ready to buy click through and hit a dead end",
  "loss_type": "leads",
  "who": "blog readers clicking an in-article service link",
  "mechanism": "one or two sentences: what the customer experiences and does next",
  "magnitude": "high",
  "magnitude_reason": "why",
  "illustration": "optional, using only the company's published figures; null otherwise",
  "kind": "INFERRED"
}
```

Add a top-level `business_impact_summary` with `ranked` (finding IDs, highest loss first) and `by_loss_type` (loss type mapped to finding IDs).

In `report.md`, add a **What this is costing you** section right after the Summary. It holds the ranked list of headlines with their magnitude, grouped by loss type, written for the owner. Also show each finding's impact headline next to the finding itself. Keep the technical detail in the findings and the business story in this section.
