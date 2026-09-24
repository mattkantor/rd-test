"""Versioned evidence records and crawl configuration."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from typing import Any

SCHEMA_VERSION = "1.0"
USER_AGENT = "CompanyScan/0.1"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def evidence(value: Any, kind: str, source: str, **extra: Any) -> dict:
    return {"value": value, "kind": kind, "source": source, **extra}


@dataclass
class Config:
    max_pages: int = 50
    max_depth: int = 3
    timeout: float = 15
    delay: float = 0.25
    max_bytes: int = 2_000_000
    max_sitemaps: int = 20
    max_urls: int = 10_000
    allow_private: bool = False
    collect_social: bool = False
    dimensions: list = field(default_factory=list)

    def validate(self) -> None:
        if min(self.max_pages, self.max_bytes, self.max_sitemaps, self.max_urls) < 1:
            raise ValueError("page, byte, sitemap, and URL limits must be positive")
        if self.max_depth < 0 or not math.isfinite(self.timeout) or not math.isfinite(self.delay) or self.timeout <= 0 or self.delay < 0:
            raise ValueError("depth/delay must be nonnegative and timeout positive")


@dataclass
class Response:
    url: str
    final_url: str
    status: int | None = None
    headers: dict = field(default_factory=dict)
    body: str = ""
    redirects: list = field(default_factory=list)
    error: str | None = None
    retrieved_at: str = field(default_factory=now)
    truncated: bool = False

    def metadata(self) -> dict:
        return {key: value for key, value in vars(self).items() if key != "body"}
