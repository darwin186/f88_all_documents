from django.urls import path

from . import views

app_name = "admindocuments"

urlpatterns = [
    path("", views.dashboard, name="admindocuments_dashboard"),
    path("dashboard/export/", views.dashboard_export, name="admindocuments_dashboard_export"),
    path("incoming-dispatches/", views.incoming_dispatch_list, name="incoming_dispatch_list"),
    path(
        "incoming-dispatches/<int:doc_id>/status/",
        views.incoming_dispatch_change_status,
        name="incoming_dispatch_change_status",
    ),
    path(
        "incoming-dispatches/<int:doc_id>/images/upload/",
        views.incoming_dispatch_upload_images,
        name="incoming_dispatch_upload_images",
    ),
    path("master-data/", views.master_data, name="master_data"),
    path("documents/", views.document_list, name="admindocuments_list"),
    path("documents/export/", views.document_list_export, name="admindocuments_list_export"),
    path("documents/new/", views.document_create, name="admindocuments_create"),
    path("documents/<int:doc_id>/", views.document_detail, name="admindocuments_detail"),
    path("documents/<int:doc_id>/update/", views.document_update, name="admindocuments_update"),
    path("documents/<int:doc_id>/field/", views.document_update_field, name="admindocuments_update_field"),
    path("documents/<int:doc_id>/attachments/upload/", views.document_attachment_upload, name="admindocuments_attachment_upload"),
    path("documents/<int:doc_id>/delete/", views.document_delete, name="admindocuments_delete"),
    path("documents/<int:doc_id>/status/", views.document_change_status, name="admindocuments_change_status"),
    path("documents/<int:doc_id>/attachments/<int:att_id>/delete/", views.document_attachment_delete, name="admindocuments_attachment_delete"),
    path("counters/", views.document_counter_manage, name="admindocuments_counters"),
    path("counters/visual/", views.document_counter_visual, name="admindocuments_counters_visual"),
    path("counters/paper/visual/", views.paper_counter_visual, name="paper_counters_visual"),
    path("paper-documents/", views.paper_document_list, name="paper_document_list"),
    path("paper-documents/<int:doc_id>/", views.paper_document_detail, name="paper_document_detail"),
    path("paper-documents/<int:doc_id>/hide/", views.paper_document_hide, name="paper_document_hide"),
    path("paper-documents/template/", views.paper_document_template, name="paper_document_template"),
    path("paper-documents/import/", views.paper_document_import, name="paper_document_import"),
    path("paper-documents/import-url/", views.paper_document_import_url, name="paper_document_import_url"),
    path("paper-documents/import-commit/", views.paper_document_import_commit, name="paper_document_import_commit"),
]
