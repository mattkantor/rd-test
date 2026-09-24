"""Per-page AI slop judged by TypeSafe's Jev (a scoring model, not a text generator). A second, holistic opinion
beside the regex copy scores: INFERRED, never proof of AI authorship. The API key never enters the bundle."""
import json
import os
import ssl
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..models import now
from ..scan.copy_scores import chrome, level

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MODEL = os.environ.get("JEV_MODEL", "jev-latest")
WORKERS = 8  # ponytail: fixed pool; Jev allows 1,200 requests/min, lower it on 429s.
MAX_CHARS = 60_000  # ponytail: ~15k tokens, well under Jev's 32k state+question limit; split pages if long ones matter.
LEVELS = ["Clearly human: specific, first-hand details, idiosyncratic voice", "Mostly human with a few generic lines",
          "Mixed: noticeably formulaic or generic in places", "Mostly formulaic, generic, interchangeable with any company",
          "Unmistakably AI-style: stock phrases, templated rhythm, no specifics"]
# Holistic judgments only: Jev doesn't count reliably, so pattern counts stay in the regex scorer.
QUESTIONS = {
    "ai_slop": {"type": "score", "criteria": LEVELS,
                "instructions": "How much does this website copy read like generic, formulaic AI-generated marketing text "
                                "rather than copy a specific person wrote from first-hand knowledge?"},
    "first_hand": {"type": "noul", "instructions": "Does the copy include a concrete first-hand detail (a named person, "
                                                   "place, date, measured result, or specific incident)?"},
    "generic": {"type": "noul", "instructions": "Could this copy be pasted onto a competitor's website with only the name changed?"},
}


def tls():
    try:  # Some Python builds ship without a usable CA store; certifi comes with the llm/web extras.
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def ask(key, text, timeout, context):
    body = json.dumps({"model": MODEL, "state": text, "questions": QUESTIONS}).encode()
    request = Request(ENDPOINT, body, {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urlopen(request, timeout=timeout, context=context) as r:
        return json.load(r)


def judge(key, page, text, timeout, context):
    out = {"url": page["url"], "words_sent": len(text.split()), "truncated": len(text) > MAX_CHARS}
    try:
        data = ask(key, text[:MAX_CHARS], timeout, context)
        slop, answers = data["answers"]["ai_slop"], data["answers"]
        score = round(float(slop["score"]) / (len(LEVELS) - 1) * 100)
    except HTTPError as exc:
        return {**out, "error": f"HTTP {exc.code}: {exc.read(500).decode('utf-8', 'replace')}"}
    except (URLError, OSError, ValueError, KeyError, TypeError) as exc:
        return {**out, "error": str(exc)}
    return {**out, "model": data.get("model"), "input_tokens": (data.get("usage") or {}).get("input_tokens"),
            "ai_slop": {"score": score, "level": level(score), "confidence": slop.get("confidence"),
                        "probabilities": slop.get("probabilities")},
            "first_hand": answers["first_hand"].get("noul"), "generic": answers["generic"].get("noul")}


def collect(client, discovery, pages, brand):
    key = os.environ.get("JEV_API_KEY")
    base = {"model": MODEL, "retrieved_at": now(), "kind": "INFERRED", "questions": QUESTIONS,
            "limitation": "One model's holistic judgment of the page copy (navigation and footer removed): evidence to "
                          "review, never proof of AI authorship. Scores are Jev's 0-4 rubric level scaled to 0-100."}
    if not key:
        return {**base, "status": "UNKNOWN", "reason": "no_key", "note": "Set JEV_API_KEY to enable."}
    # Same pages and same chrome-stripped copy the regex scorer used.
    usable = [p for p in pages if isinstance(p.get("visible_text"), str) and not p.get("duplicate_of")]
    shared = chrome(usable)
    targets = [(p, "\n".join(line for line in p["visible_text"].splitlines() if line not in shared)) for p in usable
               if ((p.get("copy_scores") or {}).get("ai_slop") or {}).get("score") is not None]
    context = tls()
    with ThreadPoolExecutor(WORKERS) as pool:
        futures = [pool.submit(judge, key, p, text, client.config.timeout, context) for p, text in targets]
        for done, _ in enumerate(as_completed(futures), 1):
            client.progress(done, len(futures), "pages")
    results = [f.result() for f in futures]
    scores = [r["ai_slop"]["score"] for r in results if "ai_slop" in r]
    errors = [r for r in results if "error" in r]
    return {**base, "status": "OBSERVED" if scores or not results else "UNKNOWN",
            "reason": "all_requests_failed" if results and not scores else None,
            "pages_judged": len(scores), "pages_failed": len(errors),
            "input_tokens": sum(r.get("input_tokens") or 0 for r in results),
            "ai_slop": {"median": round(statistics.median(scores)) if scores else None,
                        "high": sum(s >= 60 for s in scores), "medium": sum(30 <= s < 60 for s in scores)},
            "pages": results}
