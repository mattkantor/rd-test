"""Ask an LLM what it says about a company: AI visibility plus model-stated competitors.

check_reputation works with any LangChain chat model; the `reputation` command and the dimension both use one."""
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlsplit

from ..llm import REPUTATION_MODEL, chat_model
from ..models import SCHEMA_VERSION, now
from ..scan.artifacts import write_json
from ..scan.crawler import normalize
from .ranking import score

PROMPT = ("What do you know about the company at {domain}{name}? Who is its ideal customer profile and where does it "
          "operate? How does it compare to others serving that customer in that location, and who are its main "
          "competitors (names and websites)?")

ANALYZE = ("Extract the following answer about {domain} into the schema. Use only what the answer states; "
           "set recognized to false if it does not identify this specific company.\n\nANSWER:\n{answer}")

# JSON schema (not Pydantic) so this module needs no dependency; LangChain returns a dict.
ANALYSIS_SCHEMA = {
    "title": "ReputationAnalysis",
    "description": "What an LLM answer says about a company's reputation and competitors.",
    "type": "object",
    "properties": {
        "recognized": {"type": "boolean", "description": "Answer identifies this specific company"},
        "inferred_icp": {"type": ["string", "null"]},
        "inferred_location": {"type": ["string", "null"]},
        "positioning_summary": {"type": ["string", "null"], "description": "How it compares within its ICP and location"},
        "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative", "unknown"]},
        "target_sentiment": {"type": ["number", "null"],
                             "description": "How the answer describes this company, -1 negative to 1 positive; null if not discussed"},
        "competitors": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "website": {"type": ["string", "null"]}, "reason": {"type": ["string", "null"]}},
            "required": ["name", "website", "reason"]}},
    },
    "required": ["recognized", "inferred_icp", "inferred_location", "positioning_summary", "sentiment", "target_sentiment",
                 "competitors"],
}

LIMITATIONS = ["Scores come from a small sample of one model's answers on one date; answers vary between runs, models and phrasing",
               "ICP, location, positioning, competitors and sentiment are UNVERIFIED model claims, not evidence",
               "No web search or grounding; reflects model training data only",
               "Companies are matched by website domain or name, so aliases of one company may be counted separately",
               "Generated buyer questions reflect the model's own inferred ICP and location",
               "domain_mentioned is a literal substring check on the branded answer"]


def text(message):
    content = getattr(message, "content", message)
    if isinstance(content, list):  # Some providers return content blocks.
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return str(content)


def check_reputation(domain, llm, company_name=None):
    """Run the buyer-style prompt, then extract structure from the answer. `llm` is any LangChain chat model."""
    host = urlsplit(normalize(domain)).netloc
    prompt = PROMPT.format(domain=host, name=f" ({company_name})" if company_name else "")
    record = {"schema_version": SCHEMA_VERSION, "domain": host, "company_name": company_name, "prompt": prompt,
              "asked_at": now(), "raw_answer": text(llm.invoke(prompt)), "analysis": None, "status": "COMPLETE"}
    haystack = record["raw_answer"].lower()
    record["domain_mentioned"] = any(term.lower() in haystack for term in (host.removeprefix("www."), company_name) if term)
    try:
        record["analysis"] = llm.with_structured_output(ANALYSIS_SCHEMA).invoke(ANALYZE.format(domain=host, answer=record["raw_answer"]))
    except Exception as exc:  # Keep the raw answer; the analysis can be rerun from it.
        record.update(status="PARTIAL", error=f"analysis failed: {exc}")
    return record


GENERATE = ("Write {n} different questions a buyer might ask an AI assistant when choosing a provider. Buyer: {icp}. "
            "Location: {location}. Ask for recommendations, shortlists or comparisons, the way a real buyer would. "
            "Never name or hint at a specific company, including {domain}.")

PROMPTS_SCHEMA = {"title": "BuyerPrompts", "description": "Unbranded buyer questions.", "type": "object",
                  "properties": {"prompts": {"type": "array", "items": {"type": "string"}}}, "required": ["prompts"]}

EXTRACT = ("List every company or product the answer below names or recommends, in the order they first appear. "
           "Give each its website if the answer states one, its 1-based position, and a sentiment from -1 (negative) "
           "to 1 (positive) for how the answer describes it. Use only the answer.\n\nANSWER:\n{answer}")

MENTIONS_SCHEMA = {
    "title": "CompanyMentions", "description": "Companies named in an answer, in order.", "type": "object",
    "properties": {"companies": {"type": "array", "items": {"type": "object", "properties": {
        "name": {"type": "string"}, "website": {"type": ["string", "null"]}, "position": {"type": "integer"},
        "sentiment": {"type": "number"}}, "required": ["name", "website", "position", "sentiment"]}}},
    "required": ["companies"],
}


def structured(llm, schema, prompt, key):
    """Structured call that must return a list under `key`; LangChain can return None on a parse failure."""
    value = (llm.with_structured_output(schema).invoke(prompt) or {}).get(key)
    if not isinstance(value, list):
        raise ValueError(f"extraction returned no {key} list")
    return value


def generate_prompts(llm, domain, icp, location, n, company_name=None):
    prompt = GENERATE.format(n=n, icp=icp or f"customers of companies like the one at {domain}",
                             location=location or "unspecified", domain=domain)
    # Whole-word match, so a short label like "go" doesn't drop "good dentist for kids?".
    banned = [re.compile(rf"(?<![a-z0-9]){re.escape(t.lower())}(?![a-z0-9])") for t in (domain, domain.split(".")[0], company_name) if t]
    kept = [p.strip() for p in structured(llm, PROMPTS_SCHEMA, prompt, "prompts") if isinstance(p, str) and p.strip()]
    return list(dict.fromkeys(p for p in kept if not any(b.search(p.lower()) for b in banned)))[:n]


def ask(llm, prompt, number):
    row = {"prompt": prompt, "sample": number, "asked_at": now(), "raw_answer": None, "companies": None, "error": None}
    try:
        row["raw_answer"] = text(llm.invoke(prompt))
        row["companies"] = structured(llm, MENTIONS_SCHEMA, EXTRACT.format(answer=row["raw_answer"]), "companies")
    except Exception as exc:  # One failed sample is recorded and excluded; the rest still score.
        row["error"] = str(exc)
    return row


WORKERS = 8  # ponytail: fixed pool; lower it if the provider rate-limits.


def ask_buyers(llm, prompts, samples, progress=None):
    jobs = [(prompt, number) for prompt in prompts for number in range(1, samples + 1)]
    with ThreadPoolExecutor(WORKERS) as pool:
        futures = [pool.submit(ask, llm, prompt, number) for prompt, number in jobs]
        for done, _ in enumerate(as_completed(futures), 1):
            if progress:
                progress(done, len(jobs), "buyer answers")
    return [f.result() for f in futures]  # Input order, whatever order they finished in.


def rank_reputation(domain, llm, company_name=None, prompts=None, samples=3, num_prompts=8, progress=None):
    """Branded check, then unbranded buyer questions sampled and scored into a rank and sentiment."""
    branded = check_reputation(domain, llm, company_name)
    host = branded["domain"].removeprefix("www.")
    analysis, error, source = branded["analysis"] or {}, None, "user" if prompts else "generated"
    if not prompts:
        try:
            prompts = generate_prompts(llm, host, analysis.get("inferred_icp"), analysis.get("inferred_location"),
                                       num_prompts, company_name)
        except Exception as exc:  # Keep the branded result; the rank is just unavailable.
            prompts, error = [], f"prompt generation failed: {exc}"
        if not prompts and not error:
            error = "prompt generation returned no usable buyer questions (all were blank or named the company)"
    prompts = list(dict.fromkeys(prompts))
    answers = ask_buyers(llm, prompts, samples, progress)
    scores = score(host, answers, company_name, analysis.get("target_sentiment"))
    partial = branded["status"] != "COMPLETE" or error or not scores["answers_scored"] or any(a["error"] for a in answers)
    return {"status": "PARTIAL" if partial else "COMPLETE", "domain": host, "error": error, "branded": branded,
            "prompts": [{"text": p, "source": source} for p in prompts], "answers": answers, "scores": scores}


def write_bundle(output, result, model):
    output = Path(output)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f"Output path must be an empty directory: {output}")
    stamp = {"schema_version": SCHEMA_VERSION, "model": model, "created_at": now()}
    files = {"reputation/reputation.json": {**result["branded"], "model": model},
             "reputation/answers.json": {**stamp, "prompts": result["prompts"], "answers": result["answers"]},
             "reputation/scores.json": {**stamp, "domain": result["domain"], **result["scores"]}}
    artifacts = []
    for path, value in files.items():
        write_json(output / path, value)
        data = (output / path).read_bytes()
        artifacts.append({"path": path, "media_type": "application/json", "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    manifest = {"schema_version": SCHEMA_VERSION, "command": "reputation", "input_url": result["domain"], "model": model,
                "created_at": stamp["created_at"], "status": result["status"], "error": result["error"],
                "artifacts": artifacts, "limitations": LIMITATIONS}
    write_json(output / "manifest.json", manifest)
    scores = result["scores"]
    return {"manifest": str((output / "manifest.json").resolve()), "status": result["status"],
            "rank": scores["rank"], "of": scores["of"], "mention_rate": scores["mention_rate"],
            "share_of_voice": scores["share_of_voice"], "sentiment": scores["sentiment"]["score"],
            "domain_mentioned": result["branded"]["domain_mentioned"]}


def collect(client, discovery, pages, brand):
    # ponytail: defaults mean ~50 API calls per scan; lower num_prompts/samples here if scans get too slow.
    name = None if brand == urlsplit(discovery["origin"]).hostname else brand
    try:
        llm = chat_model(REPUTATION_MODEL, timeout=120)
        result = rank_reputation(discovery["origin"], llm, name, progress=getattr(client, "progress", None))
    except Exception as exc:  # Missing key, auth, network and provider errors share no base class.
        return {"status": "UNKNOWN", "reason": "llm_request_failed", "error": str(exc), "limitations": LIMITATIONS}
    return {**result, "model": REPUTATION_MODEL, "limitations": LIMITATIONS}
