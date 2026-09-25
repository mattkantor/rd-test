"""JSON-LD traversal without fetching remote contexts."""
import json
import re


def objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


def entities(value):
    """Top-level JSON-LD nodes (each document, or its @graph members): what the site says about itself. Nested nodes
    describe other parties, e.g. a case study's `about` client, so they never count as the site's own name or profiles.
    ponytail: also drops a Person nested as an Organization's founder; allowlist relations if a site needs that."""
    if isinstance(value, list):
        for child in value:
            yield from entities(child)
    elif isinstance(value, dict):
        if "@type" in value:
            yield value
        if "@graph" in value:
            yield from entities(value["@graph"])


def parse_jsonld(blocks: list[str]) -> dict:
    documents, errors = [], []
    for index, block in enumerate(blocks):
        try:
            documents.append(json.loads(block))
        except (ValueError, RecursionError) as exc:
            errors.append({"block": index, "error": str(exc), "raw": block})
    types = set()
    for obj in objects(documents):
        kind = obj.get("@type", [])
        for item in kind if isinstance(kind, list) else [kind]:
            if isinstance(item, str):
                types.add(item)
    return {"documents": documents, "types": sorted(types), "errors": errors,
            "validation": "JSON syntax plus common rich-result property checks; not a full schema.org or Google validator"}


LOCAL_BUSINESS = {"LocalBusiness", "ProfessionalService", "Dentist", "MedicalBusiness", "Store", "LegalService", "FinancialService", "HomeAndConstructionBusiness"}
ARTICLE = {"Article", "BlogPosting", "NewsArticle", "TechArticle"}
# type -> (required, recommended); modelled on Google rich-result guidance
RULES = {
    "Organization": (["name"], ["url", "logo", "sameAs"]),
    "LocalBusiness": (["name", "address"], ["telephone", "url", "sameAs"]),
    "WebSite": (["name", "url"], []),
    "Person": (["name"], ["url", "sameAs"]),
    "Article": (["headline"], ["image", "datePublished", "author"]),
    "Service": (["name"], ["provider", "description"]),
    "Product": (["name"], ["offers", "aggregateRating", "review"]),
    "Review": (["author", "reviewRating"], ["itemReviewed"]),
    "AggregateRating": (["ratingValue"], ["reviewCount", "ratingCount"]),
    "BreadcrumbList": (["itemListElement"], []),
    "FAQPage": (["mainEntity"], []),
}


def _types(obj):
    t = obj.get("@type", [])
    return {x for x in (t if isinstance(t, list) else [t]) if isinstance(x, str)}


def _rule_keys(types):
    keys = {t for t in types if t in RULES}
    if types & LOCAL_BUSINESS:
        keys.add("LocalBusiness")
    if types & ARTICLE:
        keys.add("Article")
    return keys


def _empty(value):
    return value in (None, "", [], {})


def validate(documents: list, visible_text: str = "") -> list:
    """Property and reference checks for AEO-relevant schema; issues are findings, not proof of search eligibility."""
    issues, ids, refs = [], {}, []

    def issue(severity, type_, code, message, prop=None):
        issues.append({"severity": severity, "type": type_, "code": code, "property": prop, "message": message})

    for doc in documents:
        if isinstance(doc, dict) and "schema.org" not in str(doc.get("@context", "")):
            issue("error", None, "missing_context", "Top-level JSON-LD block has no schema.org @context")
    # Property rules apply to top-level/@graph nodes and identified entities, not inline stubs like a citation.
    nodes = {id(n) for d in documents if isinstance(d, dict) for n in ([d] + [g for g in d.get("@graph", []) if isinstance(g, dict)])}
    for obj in objects(documents):
        if not isinstance(obj, dict):
            continue
        types = _types(obj)
        entity = id(obj) in nodes or "@id" in obj
        if "@id" in obj and set(obj) - {"@id"}:
            ids.setdefault(obj["@id"], []).append(obj)
        elif set(obj) == {"@id"}:
            refs.append(obj["@id"])
        for key in (_rule_keys(types) if entity else ()):
            required, recommended = RULES[key]
            if key == "Organization" and types & LOCAL_BUSINESS:
                continue
            for prop in required:
                if _empty(obj.get(prop)):
                    issue("error", key, "missing_required", f"{key} is missing required '{prop}'", prop)
            for prop in recommended:
                if key == "Product" and prop in {"aggregateRating", "review"}:
                    continue
                if _empty(obj.get(prop)):
                    issue("warning", key, "missing_recommended", f"{key} is missing recommended '{prop}'", prop)
        if "Question" in types:
            answer = obj.get("acceptedAnswer")
            text = answer.get("text") if isinstance(answer, dict) else None
            if _empty(obj.get("name")) or _empty(text):
                issue("error", "Question", "incomplete_question", "Question needs 'name' and acceptedAnswer.text")
            elif visible_text and re.sub(r"\W+", " ", str(obj["name"])).strip().lower() not in re.sub(r"\W+", " ", visible_text).lower():
                issue("warning", "Question", "faq_not_visible", f"FAQ question not found in visible page text: {str(obj['name'])[:80]}")
        if "ListItem" in types and (_empty(obj.get("position")) or _empty(obj.get("name")) and not isinstance(obj.get("item"), dict)):
            issue("error", "BreadcrumbList", "incomplete_list_item", "Breadcrumb ListItem needs 'position' and 'name'")
        if "Person" in types and "Organization" in types:
            issue("warning", "Organization", "person_organization_conflation", "Entity is typed as both Person and Organization")
    for ref in refs:
        if ref not in ids:
            issue("warning", None, "unresolved_reference", f"@id reference {ref} is not defined on this page")
    for id_, defs in ids.items():
        names = {str(d.get("name")) for d in defs if d.get("name")}
        if len(names) > 1:
            issue("error", None, "conflicting_id", f"@id {id_} has conflicting names: {sorted(names)}")
    return issues


def site_entities(pages) -> dict:
    """Group @id definitions across pages to expose entities described inconsistently."""
    entities = {}
    for page in pages:
        for obj in objects(page.get("json_ld", {}).get("documents", [])):
            if isinstance(obj, dict) and "@id" in obj and set(obj) - {"@id"}:
                e = entities.setdefault(obj["@id"], {"names": set(), "types": set(), "pages": set()})
                if obj.get("name"):
                    e["names"].add(str(obj["name"]))
                e["types"].update(_types(obj))
                e["pages"].add(page["url"])
    return {k: {"names": sorted(v["names"]), "types": sorted(v["types"]), "page_count": len(v["pages"]),
                "conflict": len(v["names"]) > 1} for k, v in entities.items()}
