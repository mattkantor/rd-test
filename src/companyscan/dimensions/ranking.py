"""Leaderboard rank and sentiment score from extracted answers. Plain Python: the LLM answers and extracts, it never grades."""
from collections import Counter, defaultdict
from urllib.parse import urlsplit


def company_key(name, website=None):
    """Website host (lowercase, no www.) when usable, else the lowercased name."""
    try:
        host = urlsplit(website if "//" in website else f"//{website}").hostname if isinstance(website, str) and website else None
    except ValueError:  # Model placeholders like "[n/a]" parse as broken IPv6 hosts.
        host = None
    return (host or "").removeprefix("www.") or name.strip().lower()


def is_target(key, name, domain, company_name=None):
    # ponytail: exact domain/name/label match only; aliases like "Acme Inc" split. Add an alias list if that bites.
    if key != name.strip().lower():  # A stated website decides: same name on another domain is a different company.
        return key == domain
    squashed = key.replace(" ", "")
    return key == domain or squashed in {domain.split(".")[0], (company_name or "").lower().replace(" ", "")} - {""}


def rating(value):
    """Clamp a model-reported sentiment to -1..1; anything non-numeric is no rating."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(-1.0, min(1.0, float(value)))


def summarize(ratings):
    if not ratings:
        return {"score": None, "n": 0, "min": None, "max": None}
    return {"score": round(sum(ratings) / len(ratings) * 100), "n": len(ratings),
            "min": round(min(ratings) * 100), "max": round(max(ratings) * 100)}


def order(mention):
    position = mention.get("position")
    return position if isinstance(position, (int, float)) and not isinstance(position, bool) else float("inf")


def score(domain, answers, company_name=None, branded_sentiment=None):
    """domain: target host without www. answers: rows with a `companies` list, or an `error`."""
    positions, names, unbranded = defaultdict(list), defaultdict(Counter), []
    scored = [a for a in answers if not a.get("error") and isinstance(a.get("companies"), list)]
    for answer in scored:
        seen = {}
        mentions = [c for c in answer["companies"] if isinstance(c, dict) and isinstance(c.get("name"), str) and c["name"].strip()]
        for c in sorted(mentions, key=order):
            key = company_key(c["name"], c.get("website"))
            key = domain if is_target(key, c["name"], domain, company_name) else key
            if key in seen:
                continue  # Named twice in one answer: counts once, at its first position.
            seen[key] = c
            positions[key].append(len(seen))
            names[key][c["name"].strip()] += 1
        if domain in seen and rating(seen[domain].get("sentiment")) is not None:
            unbranded.append(rating(seen[domain]["sentiment"]))
    board = sorted(({"company": names[k].most_common(1)[0][0], "key": k, "mentions": len(p),
                     "avg_position": round(sum(p) / len(p), 2), "is_target": k == domain} for k, p in positions.items()),
                   key=lambda r: (-r["mentions"], r["avg_position"], r["key"]))
    total, mine = sum(r["mentions"] for r in board), len(positions.get(domain, []))
    branded = [rating(branded_sentiment)] if rating(branded_sentiment) is not None else []
    return {"rank": next((i for i, r in enumerate(board, 1) if r["is_target"]), None), "of": len(board),
            "leaderboard": board,
            "mention_rate": round(mine / len(scored), 3) if scored else None,
            "share_of_voice": round(mine / total, 3) if total else None,
            "sentiment": {**summarize(branded + unbranded), "branded": summarize(branded), "unbranded": summarize(unbranded)},
            "answers_total": len(answers), "answers_scored": len(scored)}
