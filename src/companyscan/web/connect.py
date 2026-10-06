"""Settings subpage where a customer connects their website admin to one of their sites, for exports later."""
from django import forms
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from ..google import oauth
from .models import SiteConnection
from .portal import page


class ConnectionForm(forms.Form):
    platform = forms.ChoiceField(choices=SiteConnection.PLATFORMS)
    admin_url = forms.URLField(label="Admin URL", max_length=500, help_text="Where you sign in to manage the website")
    username = forms.CharField(max_length=255, required=False)
    secret = forms.CharField(label="Password or API token", widget=forms.PasswordInput(render_value=False), required=False,
                             help_text="Stored encrypted and never shown again. Leave blank to keep the saved one.")


@login_required
def website(request):
    sites = list(request.user.sites.all())
    chosen = next((s for s in sites if str(s.pk) == request.GET.get("site", "")), sites[0] if sites else None)
    connection = SiteConnection.objects.filter(site=chosen).first() if chosen else None
    form = None
    if chosen:
        initial = {"platform": connection.platform, "admin_url": connection.admin_url, "username": connection.username} if connection else None
        form = ConnectionForm(request.POST or None, initial=initial)
        if request.method == "POST" and form.is_valid():
            data = form.cleaned_data
            if not (data["secret"] or connection):
                form.add_error("secret", "Enter the password or token.")
            else:
                try:
                    secret = oauth.encrypt(data["secret"]) if data["secret"] else connection.secret
                except ValueError as exc:  # No encryption key configured: refuse to store it in the clear.
                    form.add_error(None, str(exc))
                else:
                    SiteConnection.objects.update_or_create(site=chosen, defaults={
                        "platform": data["platform"], "admin_url": data["admin_url"], "username": data["username"], "secret": secret})
                    return redirect(f"/portal/settings/website?site={chosen.pk}&saved=1")
    return page(request, "Website connection", "portal/website.html", chosen=chosen, form=form, connected=bool(connection),
                saved=request.GET.get("saved") == "1")


@login_required
@require_POST
def disconnect(request, site_pk):
    """Delete the stored credentials of one of the customer's sites."""
    site = get_object_or_404(request.user.sites, pk=site_pk)
    SiteConnection.objects.filter(site=site).delete()
    return redirect(f"/portal/settings/website?site={site.pk}")
