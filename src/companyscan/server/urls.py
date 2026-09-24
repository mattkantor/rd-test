from django.contrib import admin
from django.urls import path

from ..web import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.index, name="index"),
    path("crawl", views.crawl),
    path("report", views.report),
    path("recrawl", views.recrawl),
    path("run/<str:name>", views.run_dashboard, name="dashboard"),
    path("files/<path:path>", views.files),
]
