from django.urls import path

from app_document_campaigns import views
from app_document_campaigns import review_views
from app_document_campaigns import shop_actions
from app_document_campaigns import area_views
from app_document_campaigns import qtrr_views
from app_document_campaigns import bulk_email_views


app_name = "document_campaigns"

urlpatterns = [
    path("campaigns/<int:campaign_id>/review/errors/<int:error_id>/receipt/", review_views.refresh_folder_receipt, name="refresh_folder_receipt"),
    path("campaigns/<int:campaign_id>/review/bulk/", review_views.bulk_team_review, name="bulk_team_review"),
    path("campaigns/<int:campaign_id>/review/excel/", review_views.queue_review_excel, name="queue_review_excel"),
    path("campaigns/<int:campaign_id>/review/excel/<int:job_id>/", review_views.review_excel_status, name="review_excel_status"),
    path("campaigns/<int:campaign_id>/review/excel/<int:job_id>/download/", review_views.download_review_excel, name="download_review_excel"),
    path("campaigns/<int:campaign_id>/review/", review_views.campaign_review, name="campaign_review"),
    path("campaigns/<int:campaign_id>/qtrr/", qtrr_views.campaign_qtrr_booking, name="campaign_qtrr_booking"),
    path("campaigns/<int:campaign_id>/qtrr/map/", qtrr_views.map_qtrr_codes, name="map_qtrr_codes"),
    path("campaigns/<int:campaign_id>/qtrr/manual-excel/export/", qtrr_views.export_qtrr_mapping_excel, name="export_qtrr_mapping_excel"),
    path("campaigns/<int:campaign_id>/qtrr/manual-excel/import/", qtrr_views.import_qtrr_mapping_excel, name="import_qtrr_mapping_excel"),
    path("campaigns/<int:campaign_id>/qtrr/export/", qtrr_views.export_qtrr_excel, name="export_qtrr_excel"),
    path("campaigns/<int:campaign_id>/review/release-to-area/", review_views.release_team_review_to_area, name="release_team_review_to_area"),
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
    path("campaigns/<int:campaign_id>/email/settings/", shop_actions.save_campaign_email_config, name="campaign_email_settings"),
    path("campaigns/<int:campaign_id>/email/preflight/", shop_actions.campaign_email_preflight, name="campaign_email_preflight"),
    path("campaigns/<int:campaign_id>/email/preview/", shop_actions.campaign_email_preview, name="campaign_email_preview"),
    path("campaigns/<int:campaign_id>/email/test/", shop_actions.send_campaign_test_email, name="campaign_email_test"),
    path("campaigns/<int:campaign_id>/email/batches/prepare/", bulk_email_views.prepare_bulk_email_batches, name="prepare_bulk_email_batches"),
    path("campaigns/<int:campaign_id>/email/batches/send/", bulk_email_views.send_bulk_email_batches, name="send_bulk_email_batches"),
    path("campaigns/<int:campaign_id>/shop-links/<int:shop_id>/deadline/", shop_actions.extend_shop_deadline, name="extend_shop_deadline"),
    path("campaigns/<int:campaign_id>/publish-to-shops/", views.publish_campaign_to_shops, name="publish_campaign_to_shops"),
    path("campaigns/<int:campaign_id>/responses/", views.campaign_response_monitor, name="campaign_response_monitor"),
    path("campaigns/<int:campaign_id>/responses/areas/", area_views.campaign_area_monitor, name="campaign_area_monitor"),
    path("campaigns/<int:campaign_id>/responses/areas/excel/", area_views.queue_area_confirmation_excel, name="queue_area_confirmation_excel"),
    path("campaigns/<int:campaign_id>/responses/areas/excel/<int:job_id>/", area_views.area_confirmation_excel_status, name="area_confirmation_excel_status"),
    path("campaigns/<int:campaign_id>/responses/areas/excel/<int:job_id>/download/", area_views.download_area_confirmation_excel, name="download_area_confirmation_excel"),
    path("campaigns/<int:campaign_id>/responses/areas/email/settings/", area_views.save_area_email_config, name="area_email_settings"),
    path("campaigns/<int:campaign_id>/responses/areas/email/preview/", area_views.area_email_preview, name="area_email_preview"),
    path("campaigns/<int:campaign_id>/responses/areas/email/test/", area_views.send_area_test_email, name="area_email_test"),
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
    path("versions/<int:version_id>/download-cleaned-upload/", views.download_cleaned_upload, name="download_cleaned_upload"),
    path("versions/<int:version_id>/import-staging/", views.import_staging_excel, name="import_staging_excel"),
    path("versions/<int:version_id>/confirm-staging/", views.confirm_staging_excel, name="confirm_staging_excel"),
    path("respond/<str:raw_token>/", views.shop_response_page, name="shop_response"),
    path("manager-view/<str:raw_token>/", area_views.public_area_manager_view, name="public_area_manager_view"),
    path("manager-view/<str:raw_token>/errors/<int:error_id>/confirm/", area_views.confirm_area_error, name="confirm_area_error"),
    path("manager-view/<str:raw_token>/confirm-all/", area_views.confirm_all_area_errors, name="confirm_all_area_errors"),
    path("api/respond/<str:raw_token>/autosave/", views.autosave_batch, name="autosave_batch"),
    path("api/respond/<str:raw_token>/submit/", views.submit_responses, name="submit_responses"),
]
