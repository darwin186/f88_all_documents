# Urls for the app_documents app
from django.urls import path
from .views import CustomPasswordResetView
from . import views

urlpatterns = [
    path("", views.home_view, name="home"), 
    path('reset_password/', CustomPasswordResetView.as_view(), name='password_reset'),
    # Đường dẫn để chuyển vùng với tham số region_id
    path('switch-region/<int:region_id>/', views.switch_region, name='switch_region'),
    #Checking transaction
    path("duyet-chung-tu", views.checking_transaction_view, name="checking_transaction"),
    path("duyet-chung-tu-v2", views.checking_transaction_view_v2, name="checking_transaction_v2"),
    path('fetch-history/<int:document_id>/', views.fetch_history, name='fetch_history'),
    path('checking_additional_view/<int:document_id>/', views.checking_additional_view, name='checking_additional_view'),
    path("bulk-checking", views.bulk_checking_document_view, name="bulk_checking"),
    
    # additional checking transaction 
    path('quan-ly-hen-bo-sung', views.additional_management_view, name='additional_management'),
    path('additional-management/',views.additional_management_view, name='additional_management'),
    #Receiving transaction
    path('nhan-chung-tu', views.receive_folder_view, name = "receiving_transaction"), 
    path('nhan-chung-tu-v2', views.receive_folder_view_v2, name="receiving_transaction_v2"),
    path('fetch-history-receiving/<int:folder_id>/', views.fetch_history_receiving, name='fetch_history_receiving'), 
    path('fetch-history-receiving-v2/<int:folder_id>/', views.fetch_history_receiving_v2, name='fetch_history_receiving_v2'),
    path('receiving_additional_view/<int:folder_id>/', views.receiving_additional_view, name='receiving_additional_view'),
    path('bulk-receiving', views.bulk_receive_folder_view, name='bulk_receiving'),
    #Create Package 
    path('quan-ly-thung-chung-tu', views.package_management_view, name='package_management'),
    path('package-list-management', views.package_list_management_view, name='package_list_management'),
    path('package-list-management/export/', views.export_package_list_v2, name='package_list_export_v2'),
    path('package-list-management/detail/<int:package_id>/', views.package_list_detail_view, name='package_list_management_detail'),
    path('tao-thung-chung-tu/<int:user_id>', views.create_package_view, name = "create_package"),
    path('package/delete/<int:folder_id>/', views.clear_package_view, name='clear_package'),
    path('package/checkexists/', views.check_package_view, name='check_package_exists'), 
    path('partnerpackage/checkexists/', views.check_partner_package_view, name='check_partnerpackage_exists'),
    path('package/get-next-package-sequence/', views.get_next_package_sequence, name='get-next-package-sequence'),
    path('package/edit/<int:package_id>/', views.edit_package_view, name='edit_package'),
    path('package/change-partnerpackage-status/<int:package_id>/', views.change_partnerpackage_status, name ='change_partnerpackage_status'),
    path('import-packages/', views.import_packages_view, name='import_packages_view'),
    path('export-packages/', views.export_packages_view, name='export_packages_views'),
    path('api/packages/create-v2/', views.api_package_create_v2, name='api_package_create_v2'),
    path('api/folder/receive-v2/', views.api_receive_folder_update_v2, name='api_receive_folder_update_v2'),
    path('api/folder/<int:folder_id>/note/', views.api_folder_note_v2, name='api_folder_note_v2'),
    path('api/document/<int:document_id>/note/', views.api_document_note_v2, name='api_document_note_v2'),
    path('api/package/<int:package_id>/partner/', views.api_package_partner, name='api_package_partner'),
    path('api/package/<int:package_id>/note/', views.api_package_note, name='api_package_note'),
    path('package/bulk-validate/', views.package_bulk_validate, name='package_bulk_validate'),
    path('package/bulk-save/', views.package_bulk_save, name='package_bulk_save'),
    path('nhan-chung-tu-v2/import', views.receiving_import_v2, name='receiving_import_v2'),
    path('nhan-chung-tu-v2/import/validate', views.receiving_import_validate, name='receiving_import_validate'),
    path('nhan-chung-tu-v2/import/save', views.receiving_import_save, name='receiving_import_save'),
    #Historical Data
    path('historical/folders/', views.historical_folder_view, name='historical_folder_view'),
    path('historical/documents/', views.historical_documents_view, name='historical_documents_view'),
    #Dashboard
    path('dashboard', views.documents_dashboard, name = 'dashboard'),
    path('dashboard/folder-received', views.folder_received_dashboard, name='dashboard_folder_received'),
    path('export-excel-folder-fail/', views.export_excel_folder_fail, name='export_excel_folder_fail'),
    path('chi-tieu-chung-tu-v2/productivity/export', views.export_productivity_report, name='export_productivity_report'),
    #Request Change
    path('request-change-folder/<int:folder_id>/', views.request_change_folder_view, name='request_change_folder'),
    path('request-change-document/<int:document_id>/', views.request_change_document_view, name='request_change_document'),
    # Mượn chứng từ
    path('request-borrow-document/', views.request_borrow_document_view, name='request_borrow_document'),
    path('quan-ly-muon-chung-tu-v2/', views.borrow_document_management_v2, name='borrow_management_v2'),
    path('yeu-cau-muon-chung-tu-v2/', views.borrow_request_management_v2, name='borrow_request_management_v2'),
    path('yeu-cau-muon-chung-tu-v2/<int:request_id>/', views.borrow_request_detail_v2, name='borrow_request_detail_v2'),
    path('api/borrow-contact-recipients/search/', views.borrow_contact_recipient_search, name='borrow_contact_recipient_search'),
    path('api/borrow-requests/', views.api_borrow_request_create, name='api_borrow_request_create'),
    path('api/heartbeat/', views.api_user_heartbeat, name='api_user_heartbeat'),
    path('quan-ly-tai-khoan-ctv/', views.online_users_view, name='ctv_account_management_v2'),
    path('thong-tin-ca-nhan/', views.user_profile_v2_view, name='user_profile_v2'),
    path('phan-quyen-ui-v2/', views.ui_permission_v2_view, name='ui_permission_v2'),
    path('chi-tieu-chung-tu-v2', views.document_kpi_dashboard_v2, name='document_kpi_v2'),
    path('chi-tieu-chung-tu-v2/export-pgd', views.export_kpi_shop_detail, name='document_kpi_shop_export'),
    path('manage-borrow/return-or-report-lost/<int:document_id>/<str:action>/', views.manage_borrow_document, name='manage_borrow_document'),
    path('gapo/schedule/', views.gapo_schedule_view, name='gapo_schedule'),
    path('gapo/schedule/ai-draft/', views.gapo_ai_generate_view, name='gapo_ai_generate'),
    path('gapo/webhook/poc/', views.gapo_webhook_poc_view, name='gapo_webhook_poc'),
    path('gapo/webhook/poc/events/', views.gapo_webhook_poc_events_view, name='gapo_webhook_poc_events'),
]   
