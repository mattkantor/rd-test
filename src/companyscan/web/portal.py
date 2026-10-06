"""The customer portal: sign-in, welcome page, tool navigation and read-only settings. Staff keep the staff pages."""
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render

from . import views

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
def settings_page(request):
    return page(request, "Settings", "portal/settings.html", fields=FIELDS)


@login_required
def help_page(request):
    return page(request, "Help", "portal/help.html")


# Profile fields shown read-only: (attribute, label).
FIELDS = [("business_name", "Business name"), ("icp", "ICP"), ("category", "Category"), ("location", "Location"), ("people", "People"),
          ("aliases", "Other names"), ("profiles", "Official profiles")]
