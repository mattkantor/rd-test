"""Optional report dimensions. Each module's collect(client, discovery, pages, brand) returns evidence saved as
technical/<name>.json; judgment belongs to the analysis skill's references/<name>.md rubric."""
from . import fonts, jev_copy, meta_ads, reputation, security

DIMENSIONS = {
    "security": {"label": "Security headers", "collect": security.collect},
    "fonts": {"label": "Font consistency", "collect": fonts.collect},
    "llm_reputation": {"label": "LLM reputation", "collect": reputation.collect},
    "meta_ads": {"label": "Meta Ad Library", "collect": meta_ads.collect},
    "jev_copy": {"label": "AI slop (Jev)", "collect": jev_copy.collect},
}
