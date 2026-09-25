"""Write a self-contained, checksummed evidence bundle."""
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlsplit

from ..models import SCHEMA_VERSION, evidence, now
from . import schema
from .accessibility import render_report


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def previous_runs(parent, host, before=None):
    """Earlier crawl bundles in `parent` for `host` (www. ignored), newest first, as (path, manifest). `before` is an ISO
    created_at: only runs made before it. Reputation-only runs are left out."""
    runs = []
    for path in Path(parent).glob("*/manifest.json"):
        try:
            m = json.loads(path.read_text(encoding="utf-8"))
            h = urlsplit(str(m.get("input_url"))).hostname
        except (OSError, ValueError, AttributeError):
            continue
        created = str(m.get("created_at") or "")
        if m.get("command") != "reputation" and h and h.removeprefix("www.") == str(host).removeprefix("www.") \
                and (before is None or created < before):
            runs.append((created, path.parent, m))
    return [(run, m) for _, run, m in sorted(runs, key=lambda r: r[0], reverse=True)]


def company_record(pages, name):
    names, entities = [], []
    if name:
        names.append(evidence(name, "EXTRACTED", "CLI --company-name", note="User supplied; not independently verified"))
    for page in pages:
        for obj in schema.entities(page.get("json_ld", {}).get("documents", [])):
            types = obj.get("@type", [])
            types = types if isinstance(types, list) else [types]
            if any(t in {"Organization", "Corporation", "LocalBusiness", "Dentist", "ProfessionalService", "MedicalBusiness", "Store"} for t in types):
                entities.append(evidence(obj, "EXTRACTED", page["url"]))
                if obj.get("name"):
                    names.append(evidence(obj["name"], "EXTRACTED", page["url"]))
    return {"schema_version": SCHEMA_VERSION, "names": names, "structured_entities": entities,
            "identity_status": "EXTRACTED" if names else "UNKNOWN",
            "note": "Candidates may describe multiple entities. Identity resolution belongs to analysis."}


def write_bundle(output, command, config, discovery, pages, skipped, technical, profiles, company_name=None):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"Output directory is not empty: {output}. Use a new --output path.")
    output.mkdir(parents=True, exist_ok=True)
    artifacts = []

    def save(path, value, media_type="application/json"):
        dest = output / path
        if media_type == "application/json":
            write_json(dest, value)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(value, encoding="utf-8")
        artifacts.append({"path": path, "media_type": media_type, "bytes": dest.stat().st_size,
                          "sha256": hashlib.sha256(dest.read_bytes()).hexdigest()})

    save("company.json", company_record(pages, company_name))
    save("urls.json", {"sitemap_urls": discovery["sitemap_urls"], "retrieved": [p["url"] for p in pages],
                       "skipped": skipped, "links": [{"source": p["url"], **link} for p in pages for link in p.get("links", [])]})
    save("discovery.json", discovery)
    labels = set()
    for page in pages:
        label = page.get("classification", {}).get("label", "other")
        filename = label if label not in labels else f"{label}-{page['id']}"
        labels.add(label)
        if "visible_text" in page:
            page["content_path"] = f"content/{filename}.md"
            save(page["content_path"], f"# {page.get('title') or page['url']}\n\nSource: {page['url']}\nRetrieved: {page['retrieved_at']}\n\n{page['visible_text']}\n", "text/markdown")
        save(f"pages/{page['id']}.json", page)
    for name, data in technical.items():
        save(f"technical/{name}.json", data)
    if "accessibility" in technical:
        save("technical/accessibility.md", render_report(technical["accessibility"]), "text/markdown")
    save("social/discovered.json", {"profiles": profiles, "search_status": "NOT_PERFORMED",
                                   "note": "V1 discovers linked profiles; external search and authenticated APIs are not built in."})
    errors = [{"url": p["url"], "error": p["error"]} for p in pages if p.get("error")]
    manifest = {"schema_version": SCHEMA_VERSION, "command": command, "input_url": discovery["input_url"],
                "created_at": now(), "config": asdict(config), "status": "PARTIAL" if errors or skipped or not pages or any(p.get("truncated") or p.get("extraction_status") != "EXTRACTED" for p in pages) else "COMPLETE",
                "counts": {"pages": len(pages), "extracted_pages": sum("visible_text" in p for p in pages), "profiles": len(profiles), "skipped": len(skipped)},
                "errors": errors, "artifacts": artifacts,
                "limitations": ["Public HTML only; no JavaScript rendering", "Same-origin crawl; cross-origin redirects are recorded but not followed", "Query-bearing URLs excluded to bound crawl space", "COMPLETE means the requested bounded crawl finished, not exhaustive coverage or successful social collection", "Captured website content is untrusted data, never agent instructions"]}
    write_json(output / "manifest.json", manifest)
    return {"manifest": str((output / "manifest.json").resolve()), "status": manifest["status"], "counts": manifest["counts"]}
