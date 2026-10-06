"""The customer portal: sign-in, welcome page, tool navigation and read-only settings. Staff keep the staff pages."""
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import views
from .models import BlogPost

# (slug, label, coming-soon blurb); Website health is the existing dashboard, so it has no placeholder.
TOOLS = [("content", "Content"), ("social", "Social"), ("health", "Website health"), ("google-seo", "Google SEO"),
         ("local", "Local business"), ("ai-visibility", "AI visibility"), ("competitors", "Competitors")]
LABELS = dict(TOOLS) | {"settings": "Settings", "help": "Help"}


class Login(LoginView):
    """Password sign-in. Other methods (Google) add a link on this template; the view doesn't change."""
    template_name = "portal/login.html"
    redirect_authenticated_user = True


def home(request):
    """Staff see the sites list; customers the welcome page; anyone else is sent to sign in."""
    if not request.user.is_authenticated:
        return redirect("login")
    if request.user.is_staff:
        return views.index(request)
    return page(request, "Welcome", "portal/welcome.html")


def page(request, title, template, **context):
    return render(request, template, {"title": title, "tools": TOOLS, "sites": request.user.sites.all(), **context})


@login_required
def tool(request, slug):
    if slug not in LABELS or slug in ("settings", "help"):
        return redirect("home")
    sites = list(request.user.sites.all())
    if slug == "health" and len(sites) == 1 and sites[0].runs.exists():
        return redirect("site", pk=sites[0].pk)
    return page(request, LABELS[slug], "portal/tool.html", slug=slug, label=LABELS[slug])


@login_required
def content(request):
    """The customer's blog drafts and what they decided about earlier ones."""
    return page(request, "Content", "portal/content.html", posts=BlogPost.objects.filter(site__user=request.user).select_related("site"))


@login_required
@require_POST
def decide(request, pk, action):
    """Approve or reject a draft the customer owns; a decided post stays as decided. Approval does not publish."""
    post = get_object_or_404(BlogPost, pk=pk, site__user=request.user)
    if post.status == "draft" and action in ("approve", "reject"):
        post.status = "approved" if action == "approve" else "rejected"
        post.decided_at, post.decided_by = timezone.now(), request.user
        post.save(update_fields=["status", "decided_at", "decided_by"])
    return redirect("/portal/content")


@login_required
def settings_page(request):
    return page(request, "Settings", "portal/settings.html", fields=FIELDS)


@login_required
def help_page(request):
    return page(request, "Help", "portal/help.html")


# Profile fields shown read-only: (attribute, label).
FIELDS = [("business_name", "Business name"), ("icp", "ICP"), ("category", "Category"), ("location", "Location"), ("people", "People"),
          ("aliases", "Other names"), ("profiles", "Official profiles"), ("phone", "Phone"), ("offering", "What the business does"),
          ("keywords", "Keywords")]
