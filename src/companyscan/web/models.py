"""Sites, crawl runs and jobs. Bundles on disk stay the evidence; Run is an index of them, rebuilt by sync()."""
import json
from datetime import datetime
from urllib.parse import urlsplit

from django.conf import settings
from django.db import models
from django.db.models import Q

from ..report.analyze import latest
from ..scan.crawler import normalize, origin


class Site(models.Model):
    origin = models.CharField(max_length=500, unique=True)
    business_name = models.CharField(max_length=255, blank=True)
    icp = models.TextField("ICP", blank=True)

    def __str__(self):
        return self.origin

    @property
    def host(self):
        return urlsplit(self.origin).netloc


class Run(models.Model):
    """One crawl bundle folder under COMPANYSCAN_OUTPUT; values copied from its manifest.json."""
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="runs")
    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(null=True)  # The manifest's created_at: when the site was last crawled.
    status = models.CharField(max_length=20, blank=True)
    pages = models.IntegerField(default=0)
    dimensions = models.JSONField(default=list)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    @property
    def dir(self):
        return settings.COMPANYSCAN_OUTPUT / self.name

    @property
    def report(self):
        return latest(self.dir, "report.md")

    @property
    def pdf(self):
        return latest(self.dir, "report.pdf")


def parse_time(value):
    try:
        return datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def sync(root=None):
    """Upsert a Run per crawl manifest on disk and drop Runs whose folder is gone; the disk is the record."""
    # ponytail: rescans every manifest; fine for hundreds of bundles, track mtimes if it gets slow.
    seen = []
    for manifest in (root or settings.COMPANYSCAN_OUTPUT).glob("*/manifest.json"):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            site = origin(normalize(data["input_url"]))
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if "counts" not in data:  # Not a crawl bundle (e.g. a standalone reputation check).
            continue
        counts = data["counts"] if isinstance(data["counts"], dict) else {}
        config = data.get("config") if isinstance(data.get("config"), dict) else {}
        pages = counts.get("pages", 0)
        Run.objects.update_or_create(name=manifest.parent.name, defaults={
            "site": Site.objects.get_or_create(origin=site)[0], "created_at": parse_time(data.get("created_at")),
            "status": str(data.get("status") or "")[:20], "pages": pages if isinstance(pages, int) else 0,
            "dimensions": config["dimensions"] if isinstance(config.get("dimensions"), list) else []})
        seen.append(manifest.parent.name)
    Run.objects.exclude(name__in=seen).delete()


class Job(models.Model):
    """A crawl, report or re-crawl, run by the Huey worker. At most one running job per site (DB constraint)."""
    KINDS = [("crawl", "Crawl"), ("recrawl", "Re-crawl"), ("report", "Report")]
    STATES = [("running", "Running"), ("done", "Done"), ("error", "Error")]
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="jobs")
    kind = models.CharField(max_length=10, choices=KINDS)
    url = models.CharField(max_length=2000, blank=True)
    dimensions = models.JSONField(default=list)
    run = models.CharField(max_length=255)  # The bundle folder the job writes (crawl/recrawl) or reads (report).
    state = models.CharField(max_length=10, choices=STATES, default="running")
    label = models.TextField(blank=True)
    step = models.IntegerField(default=0)
    steps = models.IntegerField(default=0)
    done = models.IntegerField(null=True)
    total = models.IntegerField(null=True)
    unit = models.CharField(max_length=20, blank=True)
    started = models.DateTimeField(auto_now_add=True)
    finished = models.DateTimeField(null=True)

    class Meta:
        ordering = ["-started"]
        # ponytail: a worker killed mid-job leaves its row "running"; set it to error in the admin to unblock the site.
        constraints = [models.UniqueConstraint(fields=["site"], condition=Q(state="running"), name="one_running_job_per_site")]

    def __str__(self):
        return f"{self.get_kind_display()} {self.site} ({self.state})"

    @property
    def percent(self):
        """Overall 0-100: finished steps plus the fraction done in the current one."""
        if self.state == "done":
            return 100
        if not self.steps:
            return 0
        fraction = min(self.done / self.total, 1) if self.total and self.done is not None else 0
        return max(0, min(100, int((self.step - 1 + fraction) / self.steps * 100)))
