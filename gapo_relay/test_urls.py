from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("integrations/gapo/", include("gapo_relay.urls")),
]
