"""Sites, crawl runs and jobs. Bundles on disk stay the evidence; Run is an index of them, rebuilt by sync()."""
import json
import logging
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, URLValidator
from django.db import models
from django.db.models import Q

from .. import agents
from ..dimensions.reputation import QUESTIONS
from ..llm import AGENT_MODEL
from ..report.analyze import latest
from ..scan.crawler import normalize, origin
from .dashboard import SNAPSHOT, load, snapshot

log = logging.getLogger(__name__)


def lines(text):
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def validate_urls(text):
    for line in lines(text):
        URLValidator(schemes=["http", "https"])(line)


class Site(models.Model):
    origin = models.CharField(max_length=500, unique=True)
    # The customer who owns this site in the portal; unowned sites are staff-only.
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="sites")
    # The customer-facing scorecard lives at /sites/<public_id>: unguessable, so the page needs no login.
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    business_name = models.CharField(max_length=255, blank=True)
    icp = models.TextField("ICP", blank=True)
    # Only for a local business: helps the AI reputation check find it and asks buyer questions for that place.
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    # Identity fingerprint: tells this business apart from namesakes in AI answers and on third-party pages.
    category = models.CharField(max_length=255, blank=True, help_text="What kind of business, e.g. growth advisory for SaaS CEOs")
    people = models.TextField(blank=True, help_text="Founders or principals, one per line")
    aliases = models.TextField("Other names", blank=True, help_text="Former names, product names, short forms; one per line")
    profiles = models.TextField("Official profiles", blank=True, validators=[validate_urls],
                                help_text="LinkedIn, Crunchbase, G2, Google Business Profile URLs; one per line")
    # For the customer scorecard's dollar value: the growth goal is customer_ltv x target_customers.
    customer_ltv = models.PositiveIntegerField("Customer lifetime value ($)", null=True, blank=True,
                                               help_text="What one new customer is worth over the relationship")
    target_customers = models.PositiveIntegerField("New customers wanted per year", null=True, blank=True,
                                                   help_text="How many new customers the business wants to win in a year")
    phone = models.CharField(max_length=50, blank=True, help_text="Main business phone; compared with the Google listing")
    # What the business does and the topics to rank for: the input to the scheduled blog drafts (blog/).
    keywords = models.TextField(blank=True, help_text="Keywords to write posts for, one per line")
    offering = models.TextField("What the business does", blank=True)
    blog_every_days = models.PositiveIntegerField("Blog post every N days", null=True, blank=True, help_text="Leave blank to stop drafting posts")
    blog_per_run = models.PositiveSmallIntegerField("Posts per run", default=1)
    blog_repeat_keywords = models.BooleanField("Reuse keywords", default=False,
                                               help_text="Allow a keyword again once every keyword was used in the last posts")
    place_id = models.CharField("Google place ID", max_length=255, blank=True,
                                help_text="Filled in by the first crawl that finds the Google listing; clear it to search again")
    # The last LLM read of the site ({key, identity, ...}, see reputation.read_site): reused while the page text, ICP and
    # model are unchanged, so the identity the checks work from doesn't shift between runs of the same site.
    site_read = models.JSONField(null=True, blank=True)

    def __str__(self):
        return self.origin

    @property
    def host(self):
        return urlsplit(self.origin).netloc

    @property
    def location(self):
        return ", ".join(part for part in (self.city, self.state, self.country) if part.strip())

    def scan_args(self):
        """CLI flags carrying what the user told us about the business into the crawl."""
        # flag=value so text starting with "-" isn't read as another flag.
        single = (("--company-name", self.business_name), ("--icp", self.icp), ("--location", self.location),
                  ("--category", self.category), ("--place-id", self.place_id))
        multi = (("--person", self.people), ("--alias", self.aliases), ("--known-profile", self.profiles))
        return ([f"{flag}={value.strip()}" for flag, value in single if value.strip()]
                + [f"{flag}={value}" for flag, text in multi for value in lines(text)])

    def profile(self):
        """The full profile the blog generator writes from (also stored on each post as its source version)."""
        return {"business_name": self.business_name, "icp": self.icp, "category": self.category, "location": self.location,
                "phone": self.phone, "website": self.origin, "people": lines(self.people), "aliases": lines(self.aliases), "keywords": lines(self.keywords), "offering": self.offering}

    def question_key(self):
        """The profile fields buyer questions are written for; changing one gets a new question set."""
        return {"icp": self.icp.strip(), "location": self.location.strip(), "category": self.category.strip()}

    def saved_questions(self):
        """This profile's stored sets as cli.run's args.saved_questions: {dimension: {"from": run, key: items}}, or None
        for a set emptied by "new questions", which makes the next crawl write new ones."""
        return {s.kind: {"from": s.run, QUESTIONS[s.kind]: s.items} if s.items else None
                for s in self.question_sets.filter(kind__in=QUESTIONS, **self.question_key())}


class QuestionSet(models.Model):
    """The questions a question-based dimension asks for one site and profile. Stored so every crawl asks the same ones,
    comparable run to run and not paid for again, even after the bundle that wrote them is deleted. Empty items: write a
    new set on the next crawl. A copy of what was asked is always in the bundle itself."""
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="question_sets")
    kind = models.CharField(max_length=40)  # The dimension: llm_reputation, ai_search or answer_coverage.
    icp = models.TextField("ICP", blank=True)
    location = models.CharField(max_length=310, blank=True)
    category = models.CharField(max_length=255, blank=True)
    items = models.JSONField(default=list, blank=True)  # As in the dimension's JSON: prompts [{"text"}] or questions [{"question", ...}].
    run = models.CharField(max_length=255, blank=True)  # The crawl that wrote them.
    created_at = models.DateTimeField(auto_now=True)
    # ponytail: no unique constraint (a long ICP overflows a Postgres index); one running job per site means one writer.

    class Meta:
        ordering = ["kind"]

    def __str__(self):
        return f"{self.site} {self.kind}"


def remember(site, bundle):
    """Store what a crawl bundle settled that later crawls should reuse: the questions each dimension asked (when there's
    no set yet for the profile it ran with), the site read, and the Google listing's place id once one is found."""
    config = (load_json(bundle / "manifest.json") or {}).get("config")
    if not isinstance(config, dict):
        return
    for kind in ("llm_reputation", "ai_search"):
        read = (load_json(bundle / f"technical/{kind}.json") or {}).get("site_read")
        if isinstance(read, dict) and read.get("identity") and read.get("key"):
            site.site_read = {**read, "reused_from": read.get("reused_from") or bundle.name}
            site.save(update_fields=["site_read"])
            break
    listing = load_json(bundle / "technical/google_business.json") or {}
    place_id = listing["listing"].get("place_id") if listing.get("found") and isinstance(listing.get("listing"), dict) else None
    if isinstance(place_id, str) and place_id and not site.place_id:
        site.place_id = place_id[:255]
        site.save(update_fields=["place_id"])
    key = {field: str(config.get(field) or "").strip() for field in ("icp", "location", "category")}
    for kind, field in QUESTIONS.items():
        data = load_json(bundle / f"technical/{kind}.json") or {}
        if data.get("status") == "UNKNOWN" or not isinstance(data.get(field), list):
            continue
        rows = [q for q in data[field] if isinstance(q, dict)]
        items = ([{"text": q["text"]} for q in rows if isinstance(q.get("text"), str)] if field == "prompts" else
                 [{k: q.get(k) for k in ("question", "offering", "intent")} for q in rows if isinstance(q.get("question"), str)])
        found = site.question_sets.filter(kind=kind, **key).first()
        if items and not found:
            site.question_sets.create(kind=kind, items=items, run=bundle.name, **key)
        elif items and not found.items:  # Emptied by "new questions": this crawl wrote the new set.
            found.items, found.run = items, bundle.name
            found.save()


class BlogPost(models.Model):
    """A planned or generated post. A stub (title, abstract, tags, date) comes first; a written post starts as a draft, and only the
    customer's approval moves it on (publishing is a later step)."""
    STATES = [("stub", "Planned"), ("draft", "Draft"), ("approved", "Approved"), ("rejected", "Rejected")]
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="posts")
    title = models.CharField(max_length=255)
    abstract = models.TextField(blank=True)  # What the reader learns; planned before the body is written.
    meta_description = models.CharField(max_length=255, blank=True)
    tags = models.JSONField(default=list, blank=True)
    publish_on = models.DateField(null=True, blank=True)  # When it is meant to go live; a stub has this and no body yet.
    body = models.TextField(blank=True)  # Markdown; empty for a stub.
    keyword = models.CharField(max_length=255)
    status = models.CharField(max_length=10, choices=STATES, default="draft")
    run = models.CharField(max_length=255, blank=True)  # The crawl whose text it was written from.
    profile = models.JSONField(default=dict)  # Site.profile() when it was written.
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return self.title


def default_schema():
    return {"type": "object", "properties": {}}


class Agent(models.Model):
    """An agentic resource: a stored prompt, model and output schema, all editable in the admin. A caller hands it a
    context dict; it returns JSON, written to output/agents/ and recorded as an AgentRun. What the agent is *for* —
    where the context comes from and what is done with the answer — lives in the caller, never here."""
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=100, unique=True, help_text="How code refers to it, and the output file's name")
    description = models.TextField(blank=True, help_text="What this agent is for; not sent to the model")
    prompt = models.TextField(help_text="The system prompt: what to do, and what each output field must contain")
    model = models.CharField(max_length=100, default=AGENT_MODEL, help_text="provider:model, e.g. openai:gpt-5-mini")
    temperature = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(2)],
                                    help_text="Blank for the model's default; some models reject a temperature")
    context = models.JSONField(default=dict, blank=True, help_text="Static context, merged under whatever the caller passes")
    output_schema = models.JSONField(default=default_schema, blank=True,
                                     help_text='JSON Schema of the answer, e.g. {"properties": {"angle": {"type": "string"}}}. '
                                               'Every declared property is required unless the schema lists "required".')
    enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def perform(self, context=None):
        """Run the agent on its static context updated with `context`; return the AgentRun. A failure is recorded as a
        run with an error and then raised as ValueError, so the caller's job surfaces it and nothing is lost."""
        context = {**(self.context if isinstance(self.context, dict) else {}), **(context or {})}
        if not self.enabled:
            raise ValueError(f"Agent “{self.name}” is disabled.")
        try:
            output = agents.run(self.prompt, self.model, self.output_schema, context, self.temperature, self.slug)
        except ValueError as exc:
            self.runs.create(context=context, error=str(exc))
            raise
        run = self.runs.create(context=context, output=output)
        path = settings.COMPANYSCAN_OUTPUT / "agents" / f"{self.slug}-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{run.pk}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(output, ensure_ascii=False, indent=1), encoding="utf-8")
        run.path = str(path)
        run.save(update_fields=["path"])
        log.info("agent %s wrote %s", self.slug, path)
        return run


class AgentRun(models.Model):
    """One execution of an agent: what went in, what came back, where it was written, or why it failed."""
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="runs")
    context = models.JSONField(default=dict)
    output = models.JSONField(default=dict, blank=True)
    path = models.CharField(max_length=500, blank=True)  # The JSON file under output/agents/; empty for a failure.
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.agent} ({'error' if self.error else 'ok'})"


class GoogleConnection(models.Model):
    """A customer's Google account linked to a site. Tokens are Fernet-encrypted (google/oauth.py); revoked_at set means the
    customer disconnected or Google refused the refresh, and the site shows "Reconnect Google"."""
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="google_connections")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    token = models.TextField()
    refresh_token = models.TextField(blank=True)
    expires_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["site"], condition=Q(revoked_at__isnull=True), name="one_active_google_connection_per_site")]

    def __str__(self):
        return f"{self.site} Google"


class GoogleLocation(models.Model):
    """The Business Profile location the customer picked for the site, and what the last read found."""
    connection = models.OneToOneField(GoogleConnection, on_delete=models.CASCADE, related_name="location")
    account = models.CharField(max_length=255)  # accounts/123
    location_id = models.CharField(max_length=255)  # locations/456
    name = models.CharField(max_length=255, blank=True)
    snapshot = models.JSONField(default=dict)  # {"location": ..., "claimed": bool, "verifications": [...], "options": [...]}
    read_at = models.DateTimeField(null=True)

    def __str__(self):
        return self.name or self.location_id


class Proposal(models.Model):
    """A change the agent wants to make on Google. Nothing is written until the customer approves it. The rows are the audit
    trail: each applied write keeps its before and after values and who approved it."""
    KINDS = [("field_edit", "Listing edit"), ("review_reply", "Review reply"), ("qna_answer", "Question answer"), ("claim_start", "Start claim")]
    STATES = [("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected"), ("applied", "Applied"), ("failed", "Failed")]
    location = models.ForeignKey(GoogleLocation, on_delete=models.CASCADE, related_name="proposals")
    kind = models.CharField(max_length=20, choices=KINDS)
    target = models.CharField(max_length=255)  # Field-mask path, or the review or question resource name; "claim" for a claim.
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    status = models.CharField(max_length=10, choices=STATES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.get_kind_display()} {self.target} ({self.status})"


class SiteConnection(models.Model):
    """How a customer's website admin can be reached, for exporting content to it later. The secret (password or API token)
    is Fernet-encrypted and never shown again. Not verified against the website."""
    PLATFORMS = [("wordpress", "WordPress"), ("shopify", "Shopify"), ("webflow", "Webflow"), ("squarespace", "Squarespace"),
                 ("wix", "Wix"), ("other", "Other")]
    site = models.OneToOneField(Site, on_delete=models.CASCADE, related_name="connection")
    platform = models.CharField(max_length=20, choices=PLATFORMS)
    admin_url = models.URLField(max_length=500)
    username = models.CharField(max_length=255, blank=True)
    secret = models.TextField()  # Encrypted.
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.site} {self.platform}"


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


class Snapshot(models.Model):
    """What "Since last run" compares for one crawl (dashboard.snapshot of each tracked check) and its headline numbers
    for the trend lines, kept after the bundle is deleted so later runs still have something to compare with."""
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="snapshots")
    name = models.CharField(max_length=255, unique=True)  # The bundle folder, which may be gone.
    created_at = models.DateTimeField(null=True)
    checks = models.JSONField(default=dict)
    metrics = models.JSONField(default=dict)  # dashboard.metrics for the run: its headline numbers, for trend lines.

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


def load_json(path):
    """A bundle JSON file that holds an object, else None (missing, unreadable or tampered)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def parse_time(value):
    try:
        return datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def sync(root=None):
    """Upsert a Run per crawl manifest on disk and drop Runs whose folder is gone; the disk is the record. A new run also
    gets a Snapshot (tracked checks and headline numbers), which stays after its folder is deleted."""
    # ponytail: rescans every manifest; fine for hundreds of bundles, track mtimes if it gets slow.
    seen, snapped = [], set(Snapshot.objects.values_list("name", flat=True))
    # Snapshots from before metrics were stored; filled in while their bundle still exists. A real run always has
    # "pages", so a filled snapshot is never empty again.
    unmeasured = set(Snapshot.objects.filter(metrics={}).values_list("name", flat=True))
    for manifest in (root or settings.COMPANYSCAN_OUTPUT).glob("*/manifest.json"):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            site = origin(normalize(data["input_url"]))
        except (OSError, ValueError, KeyError, TypeError):
            log.warning("sync: skipped unreadable manifest %s", manifest, exc_info=True)
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
        if manifest.parent.name not in snapped:
            checks = {name: snapshot(name, load_json(manifest.parent / f"technical/{name}.json")) for name in SNAPSHOT}
            # get_or_create: the worker's sync and a page's may both find this run new; the second keeps the first's.
            Snapshot.objects.get_or_create(name=manifest.parent.name, defaults={
                "site": Site.objects.get(origin=site), "created_at": parse_time(data.get("created_at")),
                "checks": {name: data for name, data in checks.items() if data}, "metrics": load(manifest.parent)["metrics"]})
            log.info("sync: new run %s", manifest.parent.name)
        elif manifest.parent.name in unmeasured:
            Snapshot.objects.filter(name=manifest.parent.name).update(metrics=load(manifest.parent)["metrics"])
            log.info("sync: backfilled metrics for %s", manifest.parent.name)
    gone, _ = Run.objects.exclude(name__in=seen).delete()
    if gone:
        log.info("sync: dropped %d runs whose bundles are gone", gone)


class Job(models.Model):
    """A crawl, report, re-crawl or blog drafting run, run by the Huey worker. At most one running job per site (DB constraint)."""
    KINDS = [("crawl", "Crawl"), ("recrawl", "Re-crawl"), ("report", "Report"), ("blog", "Blog posts"), ("titles", "Blog titles"), ("google", "Google sync")]
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
