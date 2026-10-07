"""
URL configuration for documents project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static 
from django.http import Http404
from django.views.generic import RedirectView
from app_documents.views import CustomPasswordResetView
from app_admindocuments.media_views import protected_admindocument_file
from app_document_campaigns import storage_views


urlpatterns = [
path(
    "favicon.ico",
    RedirectView.as_view(
        url="https://f88.vn/images/root/logo-f88-primary.svg?v=20261007",
        permanent=False,
    ),
    name="favicon",
),
path(
    "media/admindocuments/files/<path:relative_path>",
    protected_admindocument_file,
    name="protected_admindocument_file",
),
path("storage/", storage_views.media_storage_browser, name="media_storage_browser"),
path("storage/file/", storage_views.media_file_preview, name="media_file_preview"),
path("storage/archive/", storage_views.queue_media_archive, name="queue_media_archive"),
path("storage/jobs/<int:job_id>/", storage_views.media_archive_job_status, name="media_archive_job_status"),
path('admin/', admin.site.urls),
path("", include("app_documents.urls")),
path("error-campaigns/", include("app_document_campaigns.urls")),
path("admindocuments/", include("app_admindocuments.urls")),
path("lich-lam-viec/", include("app_workshift.urls")),
path("integrations/gapo/", include("gapo_relay.urls")),
    path("accounts/password_reset/", CustomPasswordResetView.as_view(), name="password_reset"),
    path("accounts/", include("django.contrib.auth.urls")),

]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler400 = 'app_documents.views.handle_400'
handler404 = 'documents.error_handlers.handle_404'
handler500 = 'app_documents.views.handle_500'
