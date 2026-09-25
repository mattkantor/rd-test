from django.contrib import admin
from django.urls import path

from ..web import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.index, name="index"),
    path("crawl", views.crawl),
    path("report", views.report),
    path("recrawl", views.recrawl),
    path("site/<int:pk>", views.site_page, name="site"),
    path("site/<int:pk>/edit", views.site_edit, name="site_edit"),
    path("site/<int:pk>/job", views.site_job),
    path("run/<str:name>", views.run_dashboard, name="dashboard"),
    path("run/<str:name>/job", views.job_status),
    path("files/<path:path>", views.files),
]
