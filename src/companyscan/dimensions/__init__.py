"""Optional report dimensions. Each module's collect(client, discovery, pages, brand) returns evidence saved as
technical/<name>.json; judgment belongs to the analysis skill's references/<name>.md rubric."""
from functools import partial

from . import coverage, fonts, google_business, jev_copy, meta_ads, practitioners, reputation, security

DIMENSIONS = {
    "security": {"label": "Security headers", "collect": security.collect},
    "fonts": {"label": "Font consistency", "collect": fonts.collect},
    "llm_reputation": {"label": "LLM reputation", "collect": reputation.collect},
    "ai_search": {"label": "AI search (web)", "collect": partial(reputation.collect, search=True)},
    "answer_coverage": {"label": "Answer coverage (LLM)", "collect": coverage.collect},
    "practitioners": {"label": "Practitioner profiles (LLM)", "collect": practitioners.collect},
    "google_business": {"label": "Google Business Profile", "collect": google_business.collect},
    "meta_ads": {"label": "Meta Ad Library", "collect": meta_ads.collect},
    "jev_copy": {"label": "AI slop (Jev)", "collect": jev_copy.collect},
}
