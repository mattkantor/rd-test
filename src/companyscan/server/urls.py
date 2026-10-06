from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.urls import path

from ..web import local, portal, views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", portal.home, name="home"),
    path("login", portal.Login.as_view(), name="login"),
    path("logout", LogoutView.as_view(), name="logout"),
    path("portal/content", portal.content),
    path("portal/content/plan/<int:site_pk>", portal.plan),
    path("portal/content/<int:pk>/<str:action>", portal.decide),
    path("portal/local", local.local),
    path("portal/local/<int:site_pk>/pick", local.pick),
    path("portal/local/<int:site_pk>/sync", local.sync),
    path("portal/local/<int:site_pk>/disconnect", local.disconnect),
    path("portal/local/proposal/<int:pk>/<str:action>", local.decide),
    path("google/connect/<int:site_pk>", local.connect, name="google_connect"),
    path("google/callback", local.callback),
    path("portal/settings", portal.settings_page),
    path("portal/help", portal.help_page),
    path("portal/<slug:slug>", portal.tool),
    path("crawl", views.crawl),
    path("report", views.report),
    path("recrawl", views.recrawl),
    path("site/<int:pk>", views.site_page, name="site"),
    path("site/<int:pk>/edit", views.site_edit, name="site_edit"),
    path("site/<int:pk>/questions", views.new_questions),
    path("site/<int:pk>/job", views.site_job),
    path("sites/<uuid:public_id>", views.public_site, name="public_site"),
    path("run/<str:name>", views.run_dashboard, name="dashboard"),
    path("run/<str:name>/job", views.job_status),
    path("run/<str:name>/scorecard.pdf", views.scorecard, name="scorecard"),
    path("run/<str:name>/fixpack.zip", views.fixpack, name="fixpack"),
    path("files/<path:path>", views.files),
]
