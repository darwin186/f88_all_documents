from django.contrib import admin
from .utils import assign_group_to_folders, check_on_time
from datetime import datetime ,timedelta 
from calendar import monthrange
from .models import ( 
    Manager, Shop, Region,Gender, AreaManager, RegionManager, Employee , LoanCustomer, 
    DocumentType, BusinessType, FolderType, DocumentStatus, CheckingStatusType, FolderStatus, CheckingTransactionStatus,PartnerPackageStatus,
    DocumentsDetail, Folder, DocumentsTransactionChecking, FoldersTransactionReceiving,
    Package,LoanDetail, PartnerPackage, ContractDetail, Partner,
    HistoricalDocuments,HistoricalFolder,PackageDocumentHistory, PackageFolderHistory,
    UserProfile,ChangeRequest,
    CheckingAdditional,
    BorrowingDocument,BorrowingStatus, FolderDeadlineRule,FolderGroup,
    BorrowRequest, BorrowRequestItem, BorrowRequestLog,
    DocumentKpiSetting
)
# Register your models here.
admin.site.site_header = "Chứng từ F88"  
admin.site.site_title = "Documents Administration"

 # Gender Admin
class GenderAdmin(admin.ModelAdmin):
    list_display = ('code', 'description')
    search_fields = ('code', 'description')
    list_filter = ('code',)
    list_per_page = 25
admin.site.register(Gender, GenderAdmin)

# AreaManager Admin
class AreaManagerAdmin(admin.ModelAdmin):
    list_display = ('areaManager_id', 'areaManager_code', 'areaManager_name', 'areaManager_email', 'is_active')
    search_fields = ('areaManager_code', 'areaManager_name', 'areaManager_email')
    list_filter = ('is_active',)
    list_per_page = 25
admin.site.register(AreaManager, AreaManagerAdmin)

# RegionManager Admin
class RegionManagerAdmin(admin.ModelAdmin):
    list_display = ('regionManager_id', 'regionManager_code', 'regionManager_name', 'regionManager_email', 'is_active')
    search_fields = ('regionManager_code', 'regionManager_name', 'regionManager_email')
    list_filter = ('is_active',)
    list_per_page = 25
admin.site.register(RegionManager, RegionManagerAdmin)

# FolderGroup Admin
class FolderGroupAdmin(admin.ModelAdmin):
    list_display = ('group_id', 'group_name', 'start_date', 'end_date', 'is_active', 'rule_deadline')
    search_fields = ('group_name','start_date', 'end_date')
    list_filter = ('is_active', 'start_date')
    list_per_page = 25
admin.site.register(FolderGroup, FolderGroupAdmin)

# FolderDeadlineRule Admin
class FolderDeadlineRuleAdmin(admin.ModelAdmin):
    list_display = ('rule_id', 'rule_name', 'deadline_day', 'next_month', 'is_valid')
    search_fields = ('rule_name', 'deadline_day')
    list_per_page = 25
admin.site.register(FolderDeadlineRule, FolderDeadlineRuleAdmin)

# LoanCustomerAdmin
class LoanCustomerAdmin(admin.ModelAdmin):
    list_display = ('customer_code', 'customer_name')
    search_fields = ('customer_code', 'customer_name')
    list_per_page = 25
admin.site.register(LoanCustomer, LoanCustomerAdmin)
class BorrowingDocumentAdmin(admin.ModelAdmin):
    list_display = ('borrow_id', 'documents_id', 'borrow_date', 'appointment_date', 'lender','borrower', 'borrower_detail','ticket_code','return_date', 'borrow_status_id')
    list_filter = ('borrow_date', 'return_date')
    search_fields = ('documents_id__documents_code', 'ticket_code')
    list_select_related = ('documents_id', 'lender', 'borrower', 'borrow_status_id')
    raw_id_fields = ('documents_id', 'lender', 'borrower', 'borrow_status_id')
    list_per_page = 20
admin.site.register(BorrowingDocument,BorrowingDocumentAdmin)

# BorrowingStatusAdmin
class BorrowingStatusAdmin(admin.ModelAdmin):
    list_display = ('borrow_status_code', 'borrow_status_name', 'flag_return', 'flag_is_borrowing', 'flag_is_lost', 'badge_color')
    search_fields = ('borrow_status_code', 'borrow_status_name')
admin.site.register(BorrowingStatus,BorrowingStatusAdmin)


class BorrowRequestAdmin(admin.ModelAdmin):
    list_display = ('request_id', 'borrower', 'status', 'needed_date', 'appointment_date', 'ticket_code', 'created_at')
    search_fields = ('request_id', 'ticket_code', 'external_ref', 'borrower__shop_name')
    list_filter = ('status', 'needed_date', 'appointment_date')
    list_select_related = ('borrower',)
    list_per_page = 25
admin.site.register(BorrowRequest, BorrowRequestAdmin)


class BorrowRequestItemAdmin(admin.ModelAdmin):
    list_display = ('item_id', 'borrow_request', 'documents_id', 'status', 'handed_over_date', 'return_date')
    search_fields = ('borrow_request__request_id', 'documents_id__documents_code')
    list_filter = ('status',)
    list_select_related = ('borrow_request', 'documents_id')
    list_per_page = 25
admin.site.register(BorrowRequestItem, BorrowRequestItemAdmin)


class BorrowRequestLogAdmin(admin.ModelAdmin):
    list_display = ('log_id', 'borrow_request', 'item', 'action', 'from_status', 'to_status', 'created_at', 'created_by')
    search_fields = ('borrow_request__request_id', 'action', 'created_by__username')
    list_filter = ('action', 'created_at')
    list_select_related = ('borrow_request', 'item')
    list_per_page = 25
admin.site.register(BorrowRequestLog, BorrowRequestLogAdmin)

# Document KPI Setting Admin
class DocumentKpiSettingAdmin(admin.ModelAdmin):
    list_display = ('metric_code', 'metric_name', 'target_rate', 'is_active', 'updated_by', 'updated_at')
    search_fields = ('metric_code', 'metric_name')
    list_filter = ('is_active',)
    list_per_page = 25
admin.site.register(DocumentKpiSetting, DocumentKpiSettingAdmin)

class PartnerAdmin(admin.ModelAdmin):
    list_display = ('partner_code', 'partner_name', 'require_partner_selection', 'require_partner_code', 'is_active')
    search_fields = ('partner_code', 'partner_name')
    list_filter = ('is_active', 'require_partner_selection', 'require_partner_code')
    list_per_page = 25

admin.site.register(Partner, PartnerAdmin)

#Business Type
class BusinessTypeAdmin(admin.ModelAdmin):
    list_display = ('business_type_name', 'business_type_code', 'valid_from', 'valid_to', 'is_valid', 'created_by','action_code','need_action_code')
    list_filter = ('is_valid', 'valid_from', 'folder_type_id','action_code','need_action_code')
    search_fields = ('business_type_name', 'business_type_code')
    list_per_page = 25
    actions = ['mark_as_invalid']
admin.site.register(BusinessType,BusinessTypeAdmin)

# Checking Additional
class CheckingAdditionalAdmin(admin.ModelAdmin):
    list_display = ('additional', 'additional_note', 'date_addition', 'is_valid')
    list_filter = ('is_valid', 'date_addition')
    search_fields = ('additional',)
admin.site.register(CheckingAdditional,CheckingAdditionalAdmin)

# CheckingStatusTypeAdmin
class CheckingStatusTypeAdmin(admin.ModelAdmin):
    list_display = ('status_type_code', 'status_type_name')
    search_fields = ('status_type_code', 'status_type_name')
admin.site.register(CheckingStatusType,CheckingStatusTypeAdmin)

# EmployeeAdmin
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('employee_code', 'employee_name')
    search_fields = ('employee_code', 'employee_name')
    list_per_page = 25
admin.site.register(Employee, EmployeeAdmin)

#DocumentType
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = ('document_type_name', 'document_type_code', 'valid_from', 'valid_to', 'is_valid', 'created_by')
    list_filter = ('is_valid', 'valid_from', 'valid_to', 'created_by')
    search_fields = ('document_type_name', 'document_type_code')
admin.site.register(DocumentType,DocumentTypeAdmin)

# ContractDetailAdmin
class ContractDetailAdmin(admin.ModelAdmin):
    list_display = ('contract_code', 'customer_id', 'employee_id')
    search_fields = ('contract  de',)
    list_per_page = 25
admin.site.register(ContractDetail, ContractDetailAdmin)

# Document Detail 
class DocumentsDetailAdmin(admin.ModelAdmin):
    list_display = ('documents_id','documents_code' ,'document_type_id', 'shop_id', 'loan_id','contract_id' ,'documents_created_date', 'folder_id', 'business_type_id', 'manager_id', 'status_id','lastest_checked_date', 'lastest_checked_by', 'document_status_id', 'note', 'package_id')
    search_fields =  ('documents_code', 'shop_id' , 'loan_id', 'documents_created_date', 'lastest_checked_date' , 'folder_id', 'package_id')
    list_filter = ('documents_created_date','lastest_checked_date')
    list_per_page = 50
admin.site.register(DocumentsDetail, DocumentsDetailAdmin)

# Document transaction checking
class DocumentsTransactionCheckingAdmin(admin.ModelAdmin):
    list_display = ('documents_id', 'trans_created_date', 'trans_created_by', 'trans_updated_date', 'checking_status_id')
    search_fields = ('trans_created_by','trans_created_date', 'trans_updated_date' )
    list_filter= ('trans_created_date','trans_created_by')
    list_per_page = 25
admin.site.register(DocumentsTransactionChecking, DocumentsTransactionCheckingAdmin)

# DocumentStatus Admin
class DocumentStatusAdmin(admin.ModelAdmin):
    list_display = ('status_id', 'documents_status_name', 'documents_status_code', 'created_date','is_borrow', 'created_by', 'valid_from', 'valid_to', 'is_selectable', 'badge_color','is_selectable', 'is_lost')
    search_fields = ('documents_status_name', 'documents_status_code', 'created_by')
    list_filter = ('created_date', 'valid_from', 'valid_to')
    list_per_page = 25
admin.site.register(DocumentStatus, DocumentStatusAdmin)

# Region Admin
class RegionAdmin(admin.ModelAdmin):
    list_display = ('region_id', 'region_code', 'region_name')
    search_fields = ('region_code', 'region_name')
    list_filter = ('region_code', 'region_name')
    list_per_page = 25
admin.site.register(Region, RegionAdmin)

# Folder Admin
class FolderAdmin(admin.ModelAdmin):
    list_display = ('folder_id', 'folder_code', 'shop_id', 'folder_created_date', 'lastest_received_date', 'is_original', 'is_issue', 'is_on_time','is_late','is_out_of_group','group')
    search_fields = ('folder_code', 'shop_id__shop_name', 'folder_created_date')
    list_filter = ('folder_created_date', 'is_original', 'is_issue', 'is_out_of_group','is_late', 'is_on_time')
    actions = ['assign_groups','check_folder_on_time']
    list_per_page = 25
    def assign_groups(self, request, queryset):
        # Gọi hàm assign_group_to_folders để gán group cho các folder
        assign_group_to_folders()
        self.message_user(request, "Đã gán group cho các folder chưa có group.")
    assign_groups.short_description = "Gán group cho các folder chưa có group" 
    
    def check_folder_on_time(self, request, queryset): 
        """Hàm kiểm tra và cập nhật trạng thái đúng hạn (on time) của một folder dựa trên group đã gán."""
    
        for folder in queryset:
            if folder.group and folder.is_original and folder.is_issue:
                rule = folder.group.rule_deadline
                if rule and rule.is_valid:
                    created_month = folder.folder_created_date.month
                    created_year = folder.folder_created_date.year
                    day_to = folder.group.day_to

                    # Kiểm tra ngày hợp lệ cuối cùng của tháng
                    if rule.next_month:
                        if created_month == 12:
                            deadline_year = created_year + 1
                            deadline_month = 1
                        else:
                            deadline_year = created_year
                            deadline_month = created_month + 1
                    else:
                        deadline_year = created_year
                        deadline_month = created_month

                    # Lấy ngày cuối cùng của tháng
                    last_day_of_month = monthrange(deadline_year, deadline_month)[1]

                    # Đảm bảo `day_to` không vượt quá ngày cuối cùng của tháng
                    if day_to > last_day_of_month:
                        day_to = last_day_of_month

                    # Tạo đối tượng deadline
                    deadline = datetime(deadline_year, deadline_month, day_to)
                    deadline += timedelta(days=rule.deadline_day)

                    received_date = folder.lastest_received_date

                    # Kiểm tra trạng thái đúng hạn hay trễ hạn
                    if received_date:
                        if received_date <= deadline:
                            folder.is_on_time = True
                            folder.is_late = False
                        else:
                            folder.is_on_time = False
                            folder.is_late = True
                    else:
                        folder.is_on_time = None
                        folder.is_late = None

                    # Cập nhật trạng thái
                    folder.save(update_fields=['is_on_time', 'is_late'])
        self.message_user(request, "Đã kiểm tra trạng thái đúng hạn cho các folder.")
    check_folder_on_time.short_description = "Kiểm tra trạng thái đúng hạn"
admin.site.register(Folder, FolderAdmin)

# FoldersTransactionReceiving Admin
class FoldersTransactionReceivingAdmin(admin.ModelAdmin):
    list_display = ('trans_id', 'folder_id', 'trans_created_date', 'trans_created_by', 'trans_updated_date', 'folder_status_id')
    search_fields = ('folder_id__folder_code', 'trans_created_by__username', 'trans_updated_by__username')
    list_filter = ('trans_created_date', 'trans_updated_date', 'folder_status_id')
    list_per_page = 25
admin.site.register(FoldersTransactionReceiving, FoldersTransactionReceivingAdmin)

# CheckingTransactionStatus Admin
class CheckingTransactionStatusAdmin(admin.ModelAdmin):
    list_display = ('status_id', 'checking_status_name', 'checking_status_code', 'created_date', 'created_by', 'is_allowed_to_borrow', 'is_request_additional', 'valid_from', 'valid_to')
    search_fields = ('checking_status_name', 'checking_status_code', 'created_by')
    list_filter = ('created_date', 'is_allowed_to_borrow', 'is_request_additional', 'valid_from', 'valid_to')
    list_per_page = 25
admin.site.register(CheckingTransactionStatus, CheckingTransactionStatusAdmin)

# FolderStatus Admin
class FolderStatusAdmin(admin.ModelAdmin):
    list_display = ('folder_status_id', 'folder_status_code', 'folder_status_name', 'created_date', 'created_by', 'badge_color' ,'valid_from', 'valid_to', 'is_valid','is_not_received_yet', 'is_received','is_borrow','is_lost','is_transfer')
    search_fields = ('folder_status_code', 'folder_status_name', 'created_by')
    list_filter = ('created_date', 'is_valid', 'valid_from', 'valid_to')
    list_per_page = 25
admin.site.register(FolderStatus, FolderStatusAdmin)

# ManagerAdmin
class ManagerAdmin(admin.ModelAdmin):
    list_display = ('manager_code', 'qlkv_code', 'qlkv_name', 'qlkv_email', 'qlv_code', 'qlv_name', 'qlv_email', 'is_valid','regionManager','areaManager')
    list_filter = ('is_valid', 'valid_from', 'valid_to', 'qlkv_code', 'qlv_code')
    search_fields = ('manager_code', 'qlkv_name', 'qlv_name') 

admin.site.register(Manager, ManagerAdmin)

# LoanDetailAdmin
class LoanDetailAdmin(admin.ModelAdmin):
    list_display = ('loan_code', 'customer_code', 'customer_name', 'employee_code', 'employee_name')
    search_fields = ('loan_code', 'customer_code', 'customer_name', 'employee_code', 'employee_name')
admin.site.register(LoanDetail,LoanDetailAdmin)

#User Profile
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'department', 'region', 'shop', 'employee_code', 'gender')
    list_filter = ('department', 'region', 'shop')
    search_fields = ('user__username', 'employee_code', 'department')
    list_per_page = 25
admin.site.register(UserProfile, UserProfileAdmin)

# ShopAdmin
class ShopAdmin(admin.ModelAdmin):
    list_display = ('shop_code', 'shop_name', 'shop_email', 'is_shop_active', 'created_date', 'region_id', 'for_borrow_only')
    list_filter = ('is_shop_active', 'region_id', 'created_date')
    search_fields = ('shop_code', 'shop_name')
admin.site.register(Shop, ShopAdmin)

# FolderTypeAdmin
class FolderTypeAdmin(admin.ModelAdmin):
    list_display = ('folder_type_code', 'folder_type_name', 'package_type', 'valid_from', 'valid_to', 'is_valid')
    list_filter = ('is_valid', 'valid_from', 'valid_to')
    search_fields = ('folder_type_code', 'folder_type_name')
admin.site.register(FolderType,FolderTypeAdmin)

# PackageAdmin
class PackageAdmin(admin.ModelAdmin):
    list_display = ('package_code', 'package_type', 'created_date', 'region_id')
    list_filter = ('package_type', 'created_date', 'region_id')
    search_fields = ('package_code',)
admin.site.register(Package,PackageAdmin)

# PartnerPackageAdmin
class PartnerPackageAdmin(admin.ModelAdmin):
    list_display = ('partner_package_code', 'partner_name', 'created_date', 'status_id')
    list_filter = ('partner_name', 'status_id', 'created_date')
    search_fields = ('partner_package_code',)
admin.site.register(PartnerPackage,PartnerPackageAdmin)

# PartnerPackageStatusAdmin
class PartnerPackageStatusAdmin(admin.ModelAdmin):
    list_display = ('package_status_name','badge_color', 'is_released', 'is_in_warehouse' ,'is_backed')
    search_fields = ('package_status_name',)
admin.site.register(PartnerPackageStatus,PartnerPackageStatusAdmin)

# HistoricalFolderAdmin
class HistoricalFolderAdmin(admin.ModelAdmin):
    list_display = ('folder_code', 'shop', 'folder_type', 'package', 'region', 'folder_created_date', 'is_original', 'is_issue')
    list_filter = ('folder_created_date', 'region')
    search_fields = ('folder_code','region')
admin.site.register(HistoricalFolder, HistoricalFolderAdmin)

# HistoricalDocumentsAdmin
class HistoricalDocumentsAdmin(admin.ModelAdmin):
    list_display = ('documents_code', 'shop', 'loan', 'package', 'region', 'business_type', 'document_type', 'is_original', 'is_issue')
    list_filter = ('shop', 'loan', 'package', 'region', 'is_original', 'is_issue')
    search_fields = ('documents_code',)
admin.site.register(HistoricalDocuments, HistoricalDocumentsAdmin)

#Change Request
class ChangeRequestAdmin(admin.ModelAdmin):
    list_display = ('request_id', 'user', 'created_date', 'request_type', 'status', 'note')
    list_per_page = 25
    list_filter = ('status',)
    raw_id_fields = ('folder', 'document', 'user')  # Tối ưu hóa với raw_id_fields hoặc sử dụng autocomplete_fields để thay thế
    actions = ['approve_change_request']
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        # Chỉ sử dụng select_related để tránh xung đột với only
        return queryset.select_related('user', 'folder', 'document')
    
    def approve_change_request(self, request, queryset):
        for change_request in queryset:
            if change_request.request_type == 'folder' and change_request.folder:
                # Xử lý yêu cầu thay đổi từ `folder`
                folder = change_request.folder
                folder.lastest_received_date = None
                folder.lastest_received_by = None
                folder.is_on_time = None
                folder.is_late = None
                folder.package_id = None
                folder.note = None
                folder.folder_status_id = FolderStatus.objects.get(folder_status_id = 1 )
                folder.save(update_fields=['lastest_received_date', 'lastest_received_by', 'is_on_time', 'is_late', 'package_id', 'note', 'folder_status_id'])
            
                FoldersTransactionReceiving.objects.filter(folder_id=folder.folder_id).delete()
                PackageFolderHistory.objects.filter(folder_id=folder.folder_id).delete()
                # Set null cho các `DocumentsDetail` thuộc `folder`
                documents = DocumentsDetail.objects.filter(folder_id=folder.folder_id)
                documents.update(
                    package_id=None,
                    note=None,
                    document_status_id= None,
                    status_id = None,
                    lastest_checked_by=None,
                    lastest_checked_date=None,
                )
                
                # Xóa các bản ghi trong `DocumentsTransactionChecking` liên quan đến `DocumentsDetail` của `folder`
                DocumentsTransactionChecking.objects.filter(documents_id__in=documents).delete()
                PackageDocumentHistory.objects.filter(document_id__in=documents).delete()
            elif change_request.request_type == 'document' and change_request.document:
                # Xử lý yêu cầu thay đổi từ `document`
                document = change_request.document
                document.note = None
                document.document_status_id = None
                document.lastest_checked_by = None
                document.lastest_checked_date = None
                document.status_id = None
                document.save(update_fields=[ 'note', 'document_status_id', 'lastest_checked_by', 'lastest_checked_date', 'status_id'])
                DocumentsTransactionChecking.objects.filter(documents_id= document).delete()    
            # Đánh dấu yêu cầu đã được xử lý
            change_request.status = 'done'
            change_request.save()
        self.message_user(request, "Đã xử lý các yêu cầu thay đổi được chọn. Vừa lòng chứ?")
        
    approve_change_request.short_description = "Reset Default Choices requests"
admin.site.register(ChangeRequest, ChangeRequestAdmin)
