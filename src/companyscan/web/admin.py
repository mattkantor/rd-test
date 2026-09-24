from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html

from ..dimensions import DIMENSIONS
from . import tasks
from .models import Job, Run, Site, sync
from .views import crawl_url

admin.site.site_header = admin.site.site_title = "Company Footprint"


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ["origin"]
    search_fields = ["origin"]


@admin.register(Run)
class RunAdmin(admin.ModelAdmin):
    list_display = ["name", "site", "created_at", "status", "pages", "dashboard"]
    list_filter = ["status", "site"]
    search_fields = ["name", "site__origin"]
    readonly_fields = ["site", "name", "created_at", "status", "pages", "dimensions", "dashboard"]
    actions = ["generate_report", "recrawl"]

    def changelist_view(self, request, extra_context=None):
        sync()  # Pick up bundles written by the CLI.
        return super().changelist_view(request, extra_context)

    def has_add_permission(self, request):
        return False  # Runs come from crawls; see sync().

    @admin.display(description="Dashboard")
    def dashboard(self, run):
        return format_html('<a href="{}">Open</a>', reverse("dashboard", args=[run.name]))

    def start(self, request, queryset, kind, label, new_run, dimensions=()):
        for run in queryset:
            url = crawl_url(run.dir)
            job = url and tasks.start(url, kind, label, tasks.new_run(url) if new_run else run.name, dimensions)
            self.message_user(request, f"{run}: {'queued' if job else 'not started (unknown crawl or a job is already running)'}",
                              messages.SUCCESS if job else messages.WARNING)

    @admin.action(description="Generate report")
    def generate_report(self, request, queryset):
        self.start(request, queryset, "report", "Starting report…", False)

    @admin.action(description="Re-crawl with every check + report")
    def recrawl(self, request, queryset):
        self.start(request, queryset, "recrawl", "Re-crawling with every check, then the report…", True, DIMENSIONS)


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ["site", "kind", "state", "label", "run", "started", "finished"]
    list_filter = ["state", "kind"]
    search_fields = ["site__origin", "run"]
    readonly_fields = [f.name for f in Job._meta.fields if f.name != "state"]  # State stays editable to clear a stuck job.
