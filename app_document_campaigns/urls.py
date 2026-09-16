from django.urls import path

from app_document_campaigns import views


app_name = "document_campaigns"

urlpatterns = [
    path("health/", views.health, name="health"),
    path("", views.campaign_list, name="campaign_list"),
    path("campaigns/new/", views.campaign_create, name="campaign_create"),
    path("campaigns/<int:campaign_id>/", views.campaign_detail, name="campaign_detail"),
    path("campaigns/<int:campaign_id>/deadline/", views.update_campaign_deadline, name="update_campaign_deadline"),
    path("campaigns/<int:campaign_id>/settings/", views.update_campaign_settings, name="update_campaign_settings"),
    path("campaigns/<int:campaign_id>/shop-links/<int:shop_id>/issue/", views.issue_campaign_shop_link, name="issue_campaign_shop_link"),
    path("campaigns/<int:campaign_id>/publish-to-shops/", views.publish_campaign_to_shops, name="publish_campaign_to_shops"),
    path("campaigns/<int:campaign_id>/responses/", views.campaign_response_monitor, name="campaign_response_monitor"),
    path("campaigns/<int:campaign_id>/responses/shops/<int:shop_id>/", views.shop_response_monitor_detail, name="shop_response_monitor_detail"),
    path("campaigns/<int:campaign_id>/versions/new/", views.create_campaign_version, name="create_campaign_version"),
    path("versions/<int:version_id>/stage-sql/", views.stage_sql_version, name="stage_sql_version"),
    path("versions/<int:version_id>/jobs/latest/", views.latest_import_job, name="latest_import_job"),
    path("versions/<int:version_id>/queue-export/", views.queue_staging_excel_export, name="queue_staging_excel_export"),
    path("versions/<int:version_id>/export-staging/", views.export_staging_excel, name="export_staging_excel"),
    path("versions/<int:version_id>/import-staging/", views.import_staging_excel, name="import_staging_excel"),
    path("versions/<int:version_id>/confirm-staging/", views.confirm_staging_excel, name="confirm_staging_excel"),
    path("respond/<str:raw_token>/", views.shop_response_page, name="shop_response"),
    path("api/respond/<str:raw_token>/autosave/", views.autosave_batch, name="autosave_batch"),
    path("api/respond/<str:raw_token>/submit/", views.submit_responses, name="submit_responses"),
]
