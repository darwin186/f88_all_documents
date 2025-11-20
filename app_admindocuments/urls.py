from django.urls import path

from . import views

app_name = "admindocuments"

urlpatterns = [
    path("", views.dashboard, name="admindocuments_dashboard"),
    path("dashboard/export/", views.dashboard_export, name="admindocuments_dashboard_export"),
    path("documents/", views.document_list, name="admindocuments_list"),
    path("documents/new/", views.document_create, name="admindocuments_create"),
    path("documents/<int:doc_id>/", views.document_detail, name="admindocuments_detail"),
    path("documents/<int:doc_id>/update/", views.document_update, name="admindocuments_update"),
    path("documents/<int:doc_id>/status/", views.document_change_status, name="admindocuments_change_status"),
    path("paper-documents/", views.paper_document_list, name="paper_document_list"),
]
