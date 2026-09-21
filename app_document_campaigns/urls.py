from django.urls import path

from app_document_campaigns import views
from app_document_campaigns import review_views
from app_document_campaigns import shop_actions
from app_document_campaigns import area_views


app_name = "document_campaigns"

urlpatterns = [
    path("campaigns/<int:campaign_id>/review/errors/<int:error_id>/receipt/", review_views.refresh_folder_receipt, name="refresh_folder_receipt"),
    path("campaigns/<int:campaign_id>/review/bulk/", review_views.bulk_team_review, name="bulk_team_review"),
    path("campaigns/<int:campaign_id>/review/excel/", review_views.queue_review_excel, name="queue_review_excel"),
    path("campaigns/<int:campaign_id>/review/excel/<int:job_id>/", review_views.review_excel_status, name="review_excel_status"),
    path("campaigns/<int:campaign_id>/review/excel/<int:job_id>/download/", review_views.download_review_excel, name="download_review_excel"),
    path("campaigns/<int:campaign_id>/review/", review_views.campaign_review, name="campaign_review"),
    path("campaigns/<int:campaign_id>/review/errors/<int:error_id>/", review_views.save_team_review, name="save_team_review"),
    path("health/", views.health, name="health"),
    path("", views.campaign_list, name="campaign_list"),
    path("campaigns/new/", views.campaign_create, name="campaign_create"),
    path("campaigns/<int:campaign_id>/", views.campaign_detail, name="campaign_detail"),
    path("campaigns/<int:campaign_id>/deadline/", views.update_campaign_deadline, name="update_campaign_deadline"),
    path("campaigns/<int:campaign_id>/settings/", views.update_campaign_settings, name="update_campaign_settings"),
    path("campaigns/<int:campaign_id>/shop-links/<int:shop_id>/issue/", views.issue_campaign_shop_link, name="issue_campaign_shop_link"),
    path("campaigns/<int:campaign_id>/shop-links/<int:shop_id>/email/", shop_actions.email_shop_link, name="email_shop_link"),
    path("campaigns/<int:campaign_id>/email-status/<int:delivery_id>/", shop_actions.shop_email_status, name="shop_email_status"),
    path("campaigns/<int:campaign_id>/shop-links/<int:shop_id>/deadline/", shop_actions.extend_shop_deadline, name="extend_shop_deadline"),
    path("campaigns/<int:campaign_id>/publish-to-shops/", views.publish_campaign_to_shops, name="publish_campaign_to_shops"),
    path("campaigns/<int:campaign_id>/responses/", views.campaign_response_monitor, name="campaign_response_monitor"),
    path("campaigns/<int:campaign_id>/responses/areas/", area_views.campaign_area_monitor, name="campaign_area_monitor"),
    path("campaigns/<int:campaign_id>/responses/areas/<int:area_id>/", area_views.area_manager_detail, name="area_manager_detail"),
    path("campaigns/<int:campaign_id>/responses/areas/<int:area_id>/issue/", area_views.issue_area_manager_link, name="issue_area_manager_link"),
    path("campaigns/<int:campaign_id>/responses/areas/<int:area_id>/email/", area_views.email_area_manager_link, name="email_area_manager_link"),
    path("campaigns/<int:campaign_id>/responses/areas/<int:area_id>/extend/", area_views.extend_area_manager_link, name="extend_area_manager_link"),
    path("campaigns/<int:campaign_id>/responses/contracts/", views.campaign_response_records, name="campaign_response_records"),
    path("campaigns/<int:campaign_id>/responses/shops/<int:shop_id>/", views.shop_response_monitor_detail, name="shop_response_monitor_detail"),
    path("campaigns/<int:campaign_id>/versions/new/", views.create_campaign_version, name="create_campaign_version"),
    path("versions/<int:version_id>/stage-sql/", views.stage_sql_version, name="stage_sql_version"),
    path("versions/<int:version_id>/jobs/latest/", views.latest_import_job, name="latest_import_job"),
    path("versions/<int:version_id>/queue-export/", views.queue_staging_excel_export, name="queue_staging_excel_export"),
    path("versions/<int:version_id>/export-staging/", views.export_staging_excel, name="export_staging_excel"),
    path("versions/<int:version_id>/import-staging/", views.import_staging_excel, name="import_staging_excel"),
    path("versions/<int:version_id>/confirm-staging/", views.confirm_staging_excel, name="confirm_staging_excel"),
    path("respond/<str:raw_token>/", views.shop_response_page, name="shop_response"),
    path("manager-view/<str:raw_token>/", area_views.public_area_manager_view, name="public_area_manager_view"),
    path("api/respond/<str:raw_token>/autosave/", views.autosave_batch, name="autosave_batch"),
    path("api/respond/<str:raw_token>/submit/", views.submit_responses, name="submit_responses"),
]
