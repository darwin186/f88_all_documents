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
from app_documents.views import CustomPasswordResetView


urlpatterns = [
path('admin/', admin.site.urls),
path("", include("app_documents.urls")),
path("admindocuments/", include("app_admindocuments.urls")),
path("lich-lam-viec/", include("app_workshift.urls")),
path(
    "notifications/",
    include(("app_notification.urls", "app_notification"), namespace="app_notification"),
),
    path("accounts/password_reset/", CustomPasswordResetView.as_view(), name="password_reset"),
    path("accounts/", include("django.contrib.auth.urls")),

]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler400 = 'app_documents.views.handle_400'
handler500 = 'app_documents.views.handle_500'
