from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import F
import hashlib
import pytz
# Create your models here.

#Dim Table

class Region(models.Model):

    region_id = models.AutoField(primary_key=True)

    region_code = models.CharField(max_length= 10, null= False, blank= False, unique= True)  

    region_name = models.CharField(max_length= 255, null= False, blank= False, unique= True)

    class Meta:

        db_table = 'd_Region'

        

    def __str__(self):

        return self.region_name

class Gender(models.Model):

    code = models.CharField(max_length=10, unique=True)

    description = models.CharField(max_length=100)

    class Meta:

        db_table = 'd_Gender'

        

    def __str__(self):

            return self.description 



class RegionManager(models.Model):

    regionManager_id = models.AutoField(primary_key=True, db_column= 'region_manager_id')  # Chỉnh sửa tên trường

    regionManager_code = models.CharField(max_length=10, db_column='region_manager_code', unique=True, null=False, blank=False)

    regionManager_name = models.CharField(max_length= 255, unique= False, default= None, db_column='region_manager_name')

    regionManager_email = models.EmailField(max_length=100, null=True, blank=True, db_column='region_manager_email')

    gender = models.ForeignKey(Gender, on_delete=models.SET_NULL, null=True, blank=True)  # Khóa ngoại đến Gender

    is_active = models.BooleanField(default=True)

    class Meta:

        db_table = 'd_RegionManager'

    def __str__(self):

            return self.regionManager_name 

        

class AreaManager(models.Model):

    areaManager_id = models.AutoField(primary_key=True, db_column='area_manager_id')  # Chỉnh sửa tên trường

    areaManager_code = models.CharField(max_length=10 , db_column='area_manager_code', unique=True, null=False, blank=False)

    areaManager_name = models.CharField(max_length= 255, unique= False, default= None , db_column='area_manager_name')

    areaManager_email = models.EmailField(max_length=100, null=True, blank=True , db_column='area_manager_email')

    gender = models.ForeignKey(Gender, on_delete=models.SET_NULL, null=True, blank=True)  # Khóa ngoại đến Gender

    is_active = models.BooleanField(default=True)

    class Meta:

        db_table = 'd_AreaManager'

    

    def __str__(self):

        return self.areaManager_name 

    

# Dim - Organization chart/managers 

class Manager(models.Model):

    manager_id = models.AutoField(primary_key=True)

    manager_code = models.CharField(max_length=100, null = False, unique= True)

    regionManager = models.ForeignKey(RegionManager, related_name='region_manager', on_delete=models.CASCADE, null= True, blank= True, db_column= 'region_manager_id') # Chuyển đổi tên trường thành region_manager_id

    areaManager = models.ForeignKey(AreaManager,related_name='area_manager', on_delete=models.CASCADE, null= True, blank= True, db_column= 'area_manager_id') # Chuyển đổi tên trường thành area_manager_id

    #delegated khúc này

    qlkv_code = models.CharField(max_length= 10)

    qlkv_name = models.CharField(max_length= 255, null= False, blank= False, unique= False, default= None)

    qlkv_email = models.EmailField(max_length= 100, null= True, blank= True, unique= False, default= None)

    qlv_code = models.CharField(max_length= 10, null= False, blank= False, unique= False, default= None)

    qlv_name = models.CharField(max_length= 255, null= False, blank= False, unique= False, default= None)

    qlv_email = models.EmailField(max_length= 100, null= True, blank= True, unique= False, default= None)

    # Tới khúc này

    valid_from = models.DateField(auto_now_add=False, null= True)

    valid_to =  models.DateField(auto_now_add = False, null= True, blank= True)

    is_valid = models.BooleanField(default= True)



    class Meta:

        db_table = 'd_Manager'



    def __str__(self):

        return self.manager_code 



# Dim - Loại giấy chứng từ 

class DocumentType(models.Model):

    document_type_id = models.AutoField(primary_key=True)

    document_type_name = models.CharField(max_length= 255, null= True, blank= True, default= None)

    document_type_code = models.CharField(max_length= 10, null= False, blank= False, unique= True)

    valid_from = models.DateField(auto_now_add=False, null= True)

    valid_to =  models.DateField(auto_now_add = False, null= True, blank= True)

    is_valid = models.BooleanField(default= True)

    created_by = models.ForeignKey(User, db_column = 'created_by', on_delete=models.CASCADE, null= False)

    

    class Meta:

        db_table = 'd_DocumentType'

    

    def __str__(self):

        return self.document_type_name



# Dim - Phân loại quyển chứng từ 

class FolderType(models.Model):

    folder_type_id = models.AutoField(primary_key=True)

    folder_type_code = models.CharField(max_length= 3, null= True, blank= True, unique= True)

    folder_type_name = models.CharField(max_length= 255, null= True, blank= True, default= None) 

    package_type = models.CharField(max_length= 255, null= True, blank= True, default= None)

    badge_color = models.CharField(max_length=50, null=True, blank=True)

    valid_from = models.DateField(auto_now_add=True, null= False)

    valid_to =  models.DateField(auto_now_add = False, null= True, blank= True)

    is_valid = models.BooleanField(default= True)

    created_by = models.ForeignKey(User,db_column = 'created_by' ,on_delete=models.CASCADE, null= False)

    

    class Meta:

        db_table = 'd_FolderType' 

        

    def __str__(self):

        return self.folder_type_name  

    

# Dim - Nghiệp vụ phát sinh chứng từ

class BusinessType(models.Model):

    business_type_id = models.AutoField(primary_key=True)

    business_type_name = models.CharField(max_length= 500, null= True, blank= True, default= None) 

    business_type_code = models.CharField(max_length= 10, null= False, blank= False, unique= False) 

    action_code = models.CharField(max_length= 150, null= True, blank= True) 

    valid_from = models.DateField(auto_now_add=True, null= False)

    valid_to =  models.DateField(auto_now_add = False, null= True, blank= True)

    is_valid = models.BooleanField(default= True)

    created_by = models.ForeignKey(User, db_column = 'created_by', on_delete=models.CASCADE, null= False ) # auto add user login 

    folder_type_id = models.ForeignKey(FolderType, db_column = 'folder_type_id', on_delete=models.CASCADE, null= True)

    allow_checking = models.BooleanField(default=False) # Cho phép kiểm chứng chứng từ hay không

    need_action_code = models.BooleanField(default=False) # Cần mã hành động hay không để phân biệt các nghiệp vụ khác nhau của business_Type_code

    class Meta:

        db_table = 'd_BusinessType'

    

    def __str__(self):

        return self.business_type_name

    

# Dim - Phòng giao dịch       

class Shop(models.Model):

    shop_id = models.AutoField(primary_key=True) 

    shop_code = models.PositiveSmallIntegerField(null =True, blank = True, unique= True) # Code 4 chữ số

    shop_name = models.CharField(max_length= 255, null= False, blank= False, unique= False)

    shop_email = models.EmailField(max_length= 100, null= True, blank= True, unique= False)

    is_shop_active = models.BooleanField(default= True) 

    shop_closed_date = models.DateField(auto_now_add=False, null= True, blank= True) 

    created_date = models.DateField(auto_now_add=True, null= False, blank= False)

    manager_id = models.ForeignKey(Manager, db_column ='manager_id' ,  on_delete=models.CASCADE, null= False)

    region_id = models.ForeignKey(Region, db_column = 'region_id', on_delete=models.CASCADE, null= True)

    for_borrow_only = models.BooleanField(default=False)

    default_gddb_identity = models.ForeignKey(
        "CollateralRegistrationExternalIdentity",
        db_column="default_gddb_identity_id",
        related_name="default_shops",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:

        db_table = 'd_Shops'

        

    def __str__(self):

        return self.shop_name



# Model - User Profile

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    department = models.CharField(max_length= 100, null= False, blank= False, unique= False, default= None) 
    region = models.ForeignKey(Region, db_column='region_id', on_delete=models.CASCADE, null= True)
    shop = models.ForeignKey(Shop, db_column='shop_id', on_delete=models.CASCADE, null= True)
    default_receive_location = models.ForeignKey(
        'app_admindocuments.AdmParcelReceiveLocation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='default_users',
    )
    gapo_user_id = models.CharField(max_length=50, null=True, blank=True, unique=True)
    employee_code = models.CharField(max_length= 10, null= True, blank= True, unique= False, default= None)

    gender = models.ForeignKey(Gender, on_delete=models.SET_NULL, null=True, blank=True)

    date_of_birth = models.DateField(null=True, blank=True)

    avatar = models.FileField(upload_to='avatars/', null=True, blank=True)

    class Meta:

        db_table = 'd_UserProfile' 

    def __str__(self):

        return self.user.username

    @property

    def get_avatar(self):

        if self.avatar:

            return self.avatar.url

        return ""

    

class FolderStatus(models.Model):

    folder_status_id = models.AutoField(primary_key=True)

    folder_status_code = models.CharField(max_length= 3, null= False, blank= False, unique= True, default= None)      

    folder_status_name = models.CharField(max_length= 255, null= True, blank= True, unique= True, default= None)

    created_date = models.DateTimeField(auto_now_add=True, null= False)

    created_by = models.ForeignKey(User, db_column = 'created_by', on_delete=models.CASCADE, null= False)

    valid_from = models.DateTimeField(null= True, blank= True)

    valid_to = models.DateTimeField(null= True, blank= True)

    is_valid = models.BooleanField(default= True)

    is_not_received_yet = models.BooleanField(default=False)

    is_received = models.BooleanField(default=False)

    is_borrow = models.BooleanField(default=False)

    is_lost = models.BooleanField(default=False)

    is_transfer = models.BooleanField(default=False) 

    badge_color = models.CharField(max_length=50, null= True )

    class Meta:

        db_table= 'd_FolderStatus' 

        

    def __str__(self):

        return self.folder_status_name



# Dim - Khách hàng vay

class LoanCustomer(models.Model):  

    customer_id = models.AutoField(primary_key=True)

    customer_code = models.CharField(max_length= 100, null= False, blank= True, unique= True, default= None) 

    customer_name = models.CharField(max_length= 255, null= True, blank= True, unique= False, default= None)

    

    class Meta:

        db_table = 'd_LoanCustomer'

    

    def __str__(self):

        return self.customer_code



# Dim - Employee

class Employee(models.Model):

    employee_id = models.AutoField(primary_key=True)

    employee_code = models.CharField(max_length= 100, null= False, blank= False, unique= True) 

    employee_name = models.CharField(max_length= 255, null= True, blank= True, unique= False)

    

    class Meta: 

        db_table = 'd_Employee' 

    def __str__ (self):

        return self.employee_code



# Dim - Contract 

class ContractDetail (models.Model):

    contract_id = models.AutoField(primary_key=True)

    contract_code = models.CharField(max_length= 30, null= False, blank= True, unique= True, default= None)  

    customer_id = models.ForeignKey(LoanCustomer, db_column='customer_id', on_delete=models.SET_NULL, null= True)

    employee_id = models.ForeignKey(Employee, db_column='employee_id', on_delete=models.SET_NULL, null= True)

    class Meta:

        db_table = 'd_ContractDetail' 

    

    def __str__(self):

        return self.contract_code

    

# Dim - Chi tiết hợp đồng vay

class LoanDetail(models.Model):

    loan_id = models.AutoField(primary_key=True)

    loan_code = models.CharField(max_length= 15, null= False, blank= True, unique= True, default= None) 

    customer_id = models.ForeignKey(LoanCustomer, db_column='customer_id', on_delete=models.SET_NULL, null= True) 

    employee_id = models.ForeignKey(Employee, db_column='employee_id', on_delete=models.SET_NULL, null= True) 

    ## delegated

    customer_code = models.CharField(max_length= 100, null= True, blank= True, unique= False, default= None) # delegated

    customer_name = models.CharField(max_length= 255, null= True, blank= True, unique= False, default= None) # delegated

    employee_code = models.CharField(max_length= 100, null= True, blank= True, unique= False, default= None) # delegated

    employee_name = models.CharField(max_length= 255, null= True, blank= True, unique= False, default= None) # delegated

    

    class Meta:

        db_table = 'd_LoanDetail' 

    

    def __str__(self):

        return self.loan_code

class CheckingStatusType(models.Model):
    status_type_id = models.AutoField(primary_key=True) 
    status_type_code = models.IntegerField(null= False, blank= False, unique= True)
    status_type_name = models.CharField(max_length= 500, null= True, blank= True, default= None)
    is_missing_document = models.BooleanField(default=False)
    class Meta:
        db_table = 'd_CheckingStatusType' 
    

    def __str__(self):

        return self.status_type_name

    

# Dim - Trạng thái duyệt chứng từ

class CheckingTransactionStatus(models.Model):

    status_id = models.AutoField(primary_key=True)

    checking_status_name = models.CharField(max_length= 300, null= False, blank= False, unique= True, default= None)

    checking_status_code = models.CharField(max_length=10)

    created_date = models.DateTimeField(auto_now_add=True, null= False)

    created_by = models.ForeignKey(User, db_column = 'created_by', on_delete=models.CASCADE, null= False)

    valid_from = models.DateTimeField(null= True, blank= True)

    valid_to = models.DateTimeField(null= True, blank= True)

    is_allowed_to_borrow = models.BooleanField(default= True) 

    is_request_additional = models.BooleanField(default=False)

    checking_status_type = models.ForeignKey(CheckingStatusType, db_column = 'checking_status_type', on_delete=models.CASCADE, null= True)

    class Meta:

        db_table = 'f_CheckingStatus'    



    def __str__(self):

        return self.checking_status_name

    

# Dim - Trạng thái chứng từ 

class DocumentStatus(models.Model):

    status_id = models.AutoField(primary_key=True)

    documents_status_name = models.CharField(max_length= 300, null= False, blank= False, unique= True, default= None)

    documents_status_code = models.CharField(max_length=10)

    created_date = models.DateTimeField(auto_now_add=True, null= False)

    created_by = models.ForeignKey(User, db_column = 'created_by', on_delete=models.CASCADE, null= False)

    valid_from = models.DateTimeField(null= True, blank= True)

    valid_to = models.DateTimeField(null= True, blank= True)

    is_borrow = models.BooleanField(default=False)

    is_checked = models.BooleanField(default=False)

    is_selectable = models.BooleanField(default=False)

    is_lost = models.BooleanField(default=False)

    badge_color = models.CharField(max_length=50, null= True )

    

    class Meta:

        db_table = 'd_DocumentsStatus' 

        

    def __str__(self):

        return self.documents_status_name



# Dim - Trạng thái thùng hàng đối tác      

class PartnerPackageStatus(models.Model):

    status_id = models.AutoField(primary_key=True)

    package_status_name = models.CharField(max_length= 300, null= False, blank= False, unique= True, default= None)

    badge_color = models.CharField(max_length=50, null= True ) 

    is_released = models.BooleanField(default=False) 

    is_backed = models.BooleanField(default=False)

    is_in_warehouse = models.BooleanField(default=False)

    class Meta: 

        db_table = 'd_PartnerPackageStatus' 

    

    def __str__(self):

        return self.package_status_name



class Partner(models.Model):

    partner_id = models.AutoField(primary_key=True)

    partner_code = models.CharField(max_length=10, unique=True)

    partner_name = models.CharField(max_length=255, unique=True)

    is_active = models.BooleanField(default=True)

    require_partner_code = models.BooleanField(default=False)

    require_partner_selection = models.BooleanField(default=True)

    badge_color = models.CharField(max_length=50, null=True, blank=True)



    class Meta:

        db_table = 'd_Partner'

        verbose_name = 'Partner Vendor'

        verbose_name_plural = 'Partners'



    def __str__(self):

        return f"{self.partner_name} ({self.partner_code})"

        

# Mã thùng F88 

class Package(models.Model):

    package_id = models.AutoField(primary_key=True)

    package_code = models.CharField(max_length= 30, null= False, blank= False, unique= True, default= None) # Mã Thùng F88 quy ước (VH-yymmdd-xx)

    # package_choice_date = models.DateField(auto_now_add=False, null= False) # Ngày chọn thùng hàng 

    # number_of_package_per_date = models.PositiveSmallIntegerField(null= False, blank= False) # Số lượng thùng hàng chọn trong ngày

    package_type = models.ForeignKey(FolderType, db_column = 'package_type', on_delete=models.CASCADE, null= True) # Loại thùng hàng

    created_date = models.DateTimeField(auto_now_add=True, null= False) # Ngày tạo thùng hàng

    updated_date = models.DateTimeField(auto_now_add=False, null= True, blank= True) # Ngày cập nhật thùng hàng

    created_by = models.ForeignKey(User, db_column = 'created_by', on_delete=models.CASCADE, null= True) # Người tạo thùng hàng

    package_code_old = models.CharField(max_length= 30, null= True, blank= True, unique= True, default= None) # Mã thùng hàng cũ

    region_id = models.ForeignKey( Region, db_column='region_id', null= True, blank= True, on_delete=models.CASCADE ) # Vùng của thùng tại thời điểm tạo

    note = models.TextField(null=True, blank=True)

    

    class Meta:

        db_table = 'd_Package'     

    

    def __str__(self):

        return self.package_code

 

# Dim Thùng hàng của đối tác với mỗi thùng hàng sẽ có một mã thùng hàng đối tác tương ứng mã thùng F88

class PartnerPackage(models.Model):

    package_id = models.OneToOneField( Package, db_column='package_id', on_delete=models.CASCADE, null= True)

    partner_package_code = models.CharField(max_length= 50, null= True, blank= True, unique= True, default= None) 

    partner_name = models.CharField(max_length=10 ,null= True, blank= True, unique= False, default= None)

    partner = models.ForeignKey(Partner, db_column='partner_id', on_delete=models.SET_NULL, null=True, blank=True)

    created_date = models.DateTimeField(auto_now_add=False, null= False) # Ngày tạo thùng hàng  

    updated_date = models.DateTimeField(auto_now_add=False, null= True, blank= True) # Ngày cập nhật thùng hàng

    status_id = models.ForeignKey( PartnerPackageStatus, db_column='partnerpackagestatus_id', on_delete=models.CASCADE, null= True) # Trạng thái của thùng hàng đối tác

    created_by = models.ForeignKey(User, db_column='created_by', on_delete=models.CASCADE, null= True) # Người tạo thùng hàng đối tác

    class Meta: 

        db_table = 'd_PartnerPackage'  



    def __str__(self):

        return self.partner_package_code or f"{self.package_id.package_code if self.package_id else 'PartnerPackage'}"





class PartnerPackageHistory(models.Model):

    history_id = models.AutoField(primary_key=True)

    package = models.ForeignKey(Package, db_column='package_id', on_delete=models.CASCADE, related_name='partnerpackage_history')

    action = models.CharField(max_length=50)  # status_change, partner_change, partner_code_change

    old_value = models.CharField(max_length=255, null=True, blank=True)

    new_value = models.CharField(max_length=255, null=True, blank=True)

    note = models.CharField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    created_by = models.ForeignKey(User, db_column='created_by', on_delete=models.SET_NULL, null=True, blank=True)



    class Meta:

        db_table = 'd_PartnerPackageHistory'

        ordering = ['-created_at']



    def __str__(self):

        return f"{self.package.package_code if self.package else 'Package'} - {self.action}"

    

# Rule áp dụng cho gửi chứng từ đúng hạn

class FolderDeadlineRule(models.Model):

    rule_id = models.AutoField(primary_key=True)

    rule_name = models.CharField(max_length=100, unique=True)  # Tên của rule

    deadline_day = models.IntegerField()  # Ngày deadline cụ thể

    next_month = models.BooleanField(default=False)  # Deadline có thuộc tháng tiếp theo không

    is_valid = models.BooleanField(default=True)  # Quy tắc có đang hoạt động không

    valid_from = models.DateField(null=True, blank=True)  # Ngày bắt đầu áp dụng rule Optional

    valid_to = models.DateField(null=True, blank=True)  # Ngày kết thúc áp dụng rule Optional

    class Meta:

        db_table = 'd_Folder_deadline_rule'



    def __str__(self):

        return self.rule_name  

    

# Dim FolderGroup => Chia các folder theo các quy định về deadlines

class FolderGroup(models.Model):

    group_id = models.AutoField(primary_key=True)

    group_name = models.CharField(max_length=100, unique=True)  # Tên group

    start_date = models.DateField(null=True, blank=True)  # Ngày bắt đầu áp dụng cho group

    end_date = models.DateField(null=True, blank=True)  # Ngày kết thúc áp dụng cho group, để trống nếu chưa kết thúc

    is_active = models.BooleanField(default=True)  # Group có đang hoạt động hay không

    day_from = models.IntegerField(null=True, blank=True) # Config để tạo group dựa trên folder_created_date

    day_to = models.IntegerField(null=True, blank=True) # Config để tạo group dựa trên folder_created_date

    rule_deadline = models.ForeignKey(FolderDeadlineRule, db_column='rule_id', on_delete=models.CASCADE, null=True)

    

    class Meta:

        db_table = 'd_Folder_group'

    

    def __str__(self):

        return self.group_name

    

# Dim - Chi tiết quyển chứng từ       

class Folder(models.Model):

    folder_id = models.AutoField(primary_key=True)

    folder_code = models.CharField(max_length= 50, null= False, blank= False, unique= True, default= None)

    shop_id = models.ForeignKey(Shop, db_column = 'shop_id', on_delete=models.CASCADE, null= True) 

    folder_type_id = models.ForeignKey(FolderType, db_column = 'folder_type_id', on_delete=models.CASCADE , null= True)

    folder_status_id = models.ForeignKey(FolderStatus, db_column = 'folder_status_id', on_delete=models.CASCADE, null= True, blank= True) # user

    manager_id = models.ForeignKey(Manager, db_column = 'manager_id', on_delete=models.CASCADE, null= True, blank= True) # user

    folder_created_date = models.DateField(auto_now_add=False, null= False) 

    note = models.TextField(null= True, blank= True) # user input

    package_id = models.ForeignKey( Package, db_column = 'package_id', on_delete=models.CASCADE, null= True, blank= True) # user input

    lastest_received_date = models.DateTimeField(null=True, blank=True) # user input

    lastest_received_by = models.ForeignKey(User, db_column='lastest_received_by', on_delete=models.CASCADE, null= True, blank= True) # user input

    is_original = models.BooleanField(default= True) # True: Chứng từ gốc, False: Chứng từ sao chép

    is_issue = models.BooleanField(null=True) # True: Chứng từ đã phát hành, False: Chứng từ chưa phát hành

    row_created_date = models.DateTimeField(auto_now_add=True, null= True)

    group = models.ForeignKey(FolderGroup, db_column='group_id', on_delete=models.SET_NULL, null=True)  # Gắn với Group

    is_on_time = models.BooleanField(null=True, blank=True)  # Đánh dấu đúng hạn

    is_late = models.BooleanField(null=True, blank=True)  # Đánh dấu trễ hạn

    is_out_of_group = models.BooleanField(default=True)  # Đánh dấu folder không thuộc group nào

    folder_appointment = models.BooleanField(default=False, db_index=True)

    folder_appointment_date = models.DateField(null=True, blank=True, db_index=True)

    folder_appointment_reason = models.TextField(null=True, blank=True)

    folder_appointment_created_at = models.DateTimeField(null=True, blank=True)

    folder_appointment_updated_at = models.DateTimeField(null=True, blank=True)

    folder_appointment_resolved_at = models.DateTimeField(null=True, blank=True)

    folder_appointment_created_by = models.ForeignKey(
        User,
        db_column='folder_appointment_created_by',
        related_name='folder_appointments_created',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    folder_appointment_resolved_by = models.ForeignKey(
        User,
        db_column='folder_appointment_resolved_by',
        related_name='folder_appointments_resolved',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:

        db_table = 'f_FolderDetail'

    

    def __str__(self):

        return self.folder_code


class FolderAppointmentLog(models.Model):
    ACTION_SCHEDULED = 'scheduled'
    ACTION_RESCHEDULED = 'rescheduled'
    ACTION_RECEIVED = 'received'
    ACTION_CANCELLED = 'cancelled'
    ACTION_CHOICES = [
        (ACTION_SCHEDULED, 'Tạo lịch hẹn'),
        (ACTION_RESCHEDULED, 'Cập nhật lịch hẹn'),
        (ACTION_RECEIVED, 'Đã nhận quyển'),
        (ACTION_CANCELLED, 'Hủy lịch hẹn'),
    ]

    appointment_log_id = models.AutoField(primary_key=True)
    folder = models.ForeignKey(
        Folder,
        db_column='folder_id',
        related_name='appointment_logs',
        on_delete=models.CASCADE,
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    appointment_date = models.DateField(null=True, blank=True)
    reason = models.TextField(null=True, blank=True)
    event_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        User,
        db_column='actor_id',
        related_name='folder_appointment_logs',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'f_FolderAppointmentLog'
        ordering = ['-event_at', '-appointment_log_id']
        indexes = [
            models.Index(fields=['folder', 'event_at'], name='folder_appt_folder_event_idx'),
            models.Index(fields=['action', 'event_at'], name='folder_appt_action_event_idx'),
        ]



# Danh mục lỗi quyển chứng từ

class FolderIssueType(models.Model):

    issue_type_id = models.AutoField(primary_key=True)

    issue_type_name = models.CharField(max_length=255, unique=True)

    is_active = models.BooleanField(default=True)

    is_no_issue = models.BooleanField(default=False)

    badge_color = models.CharField(max_length=20, null=True, blank=True)

    sort_order = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.ForeignKey(

        User,

        db_column='created_by',

        on_delete=models.SET_NULL,

        null=True,

        blank=True,

        related_name='folder_issue_types_created',

    )

    updated_by = models.ForeignKey(

        User,

        db_column='updated_by',

        on_delete=models.SET_NULL,

        null=True,

        blank=True,

        related_name='folder_issue_types_updated',

    )



    class Meta:

        db_table = 'd_FolderIssueType'

        ordering = ['sort_order', 'issue_type_name']



    def __str__(self):

        return self.issue_type_name





# Log lỗi quyển chứng từ

class FolderIssue(models.Model):

    issue_id = models.AutoField(primary_key=True)

    folder = models.ForeignKey(Folder, db_column='folder_id', on_delete=models.CASCADE)

    issue_type = models.ForeignKey(FolderIssueType, db_column='issue_type_id', on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)

    created_by = models.ForeignKey(User, db_column='created_by', on_delete=models.SET_NULL, null=True, blank=True)



    class Meta:

        db_table = 'f_FolderIssue'

        unique_together = ('folder', 'issue_type')



    def __str__(self):

        return f"{self.folder.folder_code} - {self.issue_type.issue_type_name}"





class UiScreen(models.Model):

    screen_id = models.AutoField(primary_key=True)

    screen_key = models.CharField(max_length=100, unique=True)

    screen_name = models.CharField(max_length=255)

    screen_path = models.CharField(max_length=255, null=True, blank=True)

    screen_group = models.CharField(max_length=100, null=True, blank=True)

    is_active = models.BooleanField(default=True)



    class Meta:

        db_table = 'd_UiScreen'

        ordering = ['screen_group', 'screen_name']



    def __str__(self):

        return self.screen_name





class UiPermission(models.Model):
    permission_id = models.AutoField(primary_key=True)

    screen = models.ForeignKey(UiScreen, db_column='screen_id', on_delete=models.CASCADE)

    role_code = models.CharField(max_length=50)

    can_view = models.BooleanField(default=False)

    updated_at = models.DateTimeField(auto_now=True)

    updated_by = models.ForeignKey(User, db_column='updated_by', on_delete=models.SET_NULL, null=True, blank=True)



    class Meta:

        db_table = 'f_UiPermission'

        unique_together = ('screen', 'role_code')



    def __str__(self):
        return f"{self.role_code} - {self.screen.screen_key}"


class CollateralRegistrationStatus(models.TextChoices):
    PENDING = "pending", "Chưa đăng kí"
    REGISTERED = "registered", "Đã đăng kí"
    NOT_REGISTERED = "not_registered", "Không đăng kí"


class CollateralRegistrationImportBatch(models.Model):
    batch_id = models.AutoField(primary_key=True)
    source_type = models.CharField(max_length=30, default="api")
    source_url = models.TextField(null=True, blank=True)
    total_rows = models.PositiveIntegerField(default=0)
    created_rows = models.PositiveIntegerField(default=0)
    updated_rows = models.PositiveIntegerField(default=0)
    skipped_rows = models.PositiveIntegerField(default=0)
    duplicate_rows = models.PositiveIntegerField(default=0)
    error_rows = models.PositiveIntegerField(default=0)
    summary = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, db_column="created_by", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = "f_CollateralRegistrationImportBatch"
        ordering = ["-created_at"]

    def __str__(self):
        return f"GDDB import #{self.batch_id}"


class CollateralRegistrationApiToken(models.Model):
    token_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    token_prefix = models.CharField(max_length=16, editable=False)
    owner = models.ForeignKey(
        User,
        db_column="owner_id",
        related_name="gddb_api_tokens",
        on_delete=models.PROTECT,
    )
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        db_column="created_by",
        related_name="gddb_api_tokens_created",
        on_delete=models.PROTECT,
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        User,
        db_column="revoked_by",
        related_name="gddb_api_tokens_revoked",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "f_CollateralRegistrationApiToken"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.token_prefix}...)"


class CollateralRegistrationExternalIdentity(models.Model):
    identity_id = models.AutoField(primary_key=True)
    external_code = models.CharField(max_length=100, unique=True)
    display_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        db_column="created_by",
        related_name="gddb_external_identities_created",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        User,
        db_column="updated_by",
        related_name="gddb_external_identities_updated",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "d_CollateralRegistrationExternalIdentity"
        ordering = ["external_code"]

    def __str__(self):
        return self.external_code


class CollateralRegistration(models.Model):
    registration_id = models.AutoField(primary_key=True)
    contract_code = models.CharField(max_length=50)
    license_plate = models.CharField(max_length=50, null=True, blank=True)
    chassis_number = models.CharField(max_length=100, null=True, blank=True)
    engine_number = models.CharField(max_length=100, null=True, blank=True)
    gddb_status = models.CharField(
        max_length=30,
        choices=CollateralRegistrationStatus.choices,
        default=CollateralRegistrationStatus.PENDING,
    )
    contract_status = models.CharField(max_length=100, null=True, blank=True)
    source_created_date = models.DateField(null=True, blank=True)
    disbursement_date = models.DateField(null=True, blank=True)
    shop_name = models.CharField(max_length=255, null=True, blank=True)
    disbursement_source = models.CharField(max_length=255, null=True, blank=True)
    post_update_status = models.CharField(max_length=255, null=True, blank=True)
    postmini_updated = models.CharField(max_length=255, default="Chưa cập nhật", blank=True)
    source_user = models.CharField(max_length=255, null=True, blank=True)
    reason = models.TextField(null=True, blank=True)
    note = models.TextField(null=True, blank=True)
    previous_application_no = models.CharField(max_length=100, null=True, blank=True)
    previous_registration_date = models.DateField(null=True, blank=True)
    registered_by_name = models.CharField(max_length=255, null=True, blank=True)
    registered_identity = models.ForeignKey(
        CollateralRegistrationExternalIdentity,
        db_column="registered_identity_id",
        related_name="registrations",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    it_ticket_code = models.CharField(max_length=255, null=True, blank=True)
    pgd_note = models.TextField(null=True, blank=True)
    duplicate_of = models.ForeignKey(
        "self",
        db_column="duplicate_of_id",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="duplicate_records",
    )
    is_duplicate = models.BooleanField(default=False)
    source_system = models.CharField(max_length=100, null=True, blank=True)
    external_ref = models.CharField(max_length=100, null=True, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    import_batch = models.ForeignKey(
        CollateralRegistrationImportBatch,
        db_column="batch_id",
        related_name="registrations",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    dedupe_key = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, db_column="created_by", related_name="gddb_created", on_delete=models.SET_NULL, null=True, blank=True)
    updated_by = models.ForeignKey(User, db_column="updated_by", related_name="gddb_updated", on_delete=models.SET_NULL, null=True, blank=True)
    registered_at = models.DateTimeField(null=True, blank=True)
    registered_by = models.ForeignKey(User, db_column="registered_by", related_name="gddb_registered", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = "f_CollateralRegistration"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["gddb_status", "is_duplicate"]),
            models.Index(fields=["contract_code"]),
            models.Index(fields=["license_plate"]),
            models.Index(fields=["chassis_number"]),
            models.Index(fields=["engine_number"]),
        ]

    def __str__(self):
        return f"{self.contract_code} - {self.license_plate or self.chassis_number or self.engine_number}"

    @staticmethod
    def normalize_key_part(value):
        return "".join(str(value or "").strip().upper().split())

    @classmethod
    def build_dedupe_key(cls, contract_code, license_plate="", chassis_number="", engine_number=""):
        raw_key = "|".join([
            cls.normalize_key_part(contract_code),
            cls.normalize_key_part(license_plate),
            cls.normalize_key_part(chassis_number),
            cls.normalize_key_part(engine_number),
        ])
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def save(self, *args, **kwargs):
        self.dedupe_key = self.build_dedupe_key(
            self.contract_code,
            self.license_plate,
            self.chassis_number,
            self.engine_number,
        )
        if self.gddb_status == CollateralRegistrationStatus.REGISTERED and not self.registered_at:
            self.registered_at = timezone.now()
        super().save(*args, **kwargs)


class CollateralRegistrationLog(models.Model):
    log_id = models.AutoField(primary_key=True)
    registration = models.ForeignKey(CollateralRegistration, db_column="registration_id", related_name="logs", on_delete=models.CASCADE)
    action = models.CharField(max_length=50)
    from_status = models.CharField(max_length=30, null=True, blank=True)
    to_status = models.CharField(max_length=30, null=True, blank=True)
    note = models.TextField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, db_column="created_by", related_name="gddb_logs", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = "f_CollateralRegistrationLog"
        ordering = ["-created_at"]

    def __str__(self):
        return f"GDDB log {self.log_id}"




class DataImportAttribute(models.Model):

    DATA_TYPE_TEXT = 'text'

    DATA_TYPE_INTEGER = 'integer'

    DATA_TYPE_DECIMAL = 'decimal'

    DATA_TYPE_DATE = 'date'

    DATA_TYPE_DATETIME = 'datetime'

    DATA_TYPE_CHOICES = [
        (DATA_TYPE_TEXT, 'Text'),
        (DATA_TYPE_INTEGER, 'Integer'),
        (DATA_TYPE_DECIMAL, 'Decimal'),
        (DATA_TYPE_DATE, 'Date'),
        (DATA_TYPE_DATETIME, 'Datetime'),
    ]
    attribute_id = models.AutoField(primary_key=True)
    attribute_code = models.CharField(max_length=50, unique=True)
    attribute_name = models.CharField(max_length=255)
    data_type = models.CharField(max_length=20, choices=DATA_TYPE_CHOICES, default=DATA_TYPE_TEXT)
    description = models.CharField(max_length=255, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, db_column='created_by', on_delete=models.SET_NULL, null=True, blank=True, related_name='data_import_attributes_created')
    updated_by = models.ForeignKey(User, db_column='updated_by', on_delete=models.SET_NULL, null=True, blank=True, related_name='data_import_attributes_updated')



    class Meta:

        db_table = 'd_DataImportAttribute'

        ordering = ['attribute_name']



    def __str__(self):

        return self.attribute_name





class DataImportProfile(models.Model):

    TARGET_RECEIVING_OFFLINE = 'receiving_offline'

    TARGET_CHOICES = [

        (TARGET_RECEIVING_OFFLINE, 'Nhận chứng từ offline'),

    ]



    profile_id = models.AutoField(primary_key=True)

    profile_code = models.CharField(max_length=50, unique=True)

    profile_name = models.CharField(max_length=255)

    target_code = models.CharField(max_length=50, choices=TARGET_CHOICES, default=TARGET_RECEIVING_OFFLINE)

    description = models.CharField(max_length=255, null=True, blank=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.ForeignKey(User, db_column='created_by', on_delete=models.SET_NULL, null=True, blank=True, related_name='data_import_profiles_created')

    updated_by = models.ForeignKey(User, db_column='updated_by', on_delete=models.SET_NULL, null=True, blank=True, related_name='data_import_profiles_updated')



    class Meta:

        db_table = 'd_DataImportProfile'

        ordering = ['profile_name']



    def __str__(self):

        return self.profile_name





class DataImportMapping(models.Model):

    mapping_id = models.AutoField(primary_key=True)

    profile = models.ForeignKey(DataImportProfile, db_column='profile_id', on_delete=models.CASCADE, related_name='mappings')

    attribute = models.ForeignKey(DataImportAttribute, db_column='attribute_id', on_delete=models.CASCADE, related_name='mappings')

    system_field_key = models.CharField(max_length=100)

    source_header = models.CharField(max_length=255, null=True, blank=True)

    sort_order = models.IntegerField(default=0)

    is_required = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.ForeignKey(User, db_column='created_by', on_delete=models.SET_NULL, null=True, blank=True, related_name='data_import_mappings_created')

    updated_by = models.ForeignKey(User, db_column='updated_by', on_delete=models.SET_NULL, null=True, blank=True, related_name='data_import_mappings_updated')



    class Meta:

        db_table = 'd_DataImportMapping'

        unique_together = (

            ('profile', 'attribute'),

            ('profile', 'system_field_key'),

        )

        ordering = ['sort_order', 'mapping_id']



    def __str__(self):

        return f"{self.profile.profile_name} - {self.attribute.attribute_name}"



# Chi tiết chứng từ 

class DocumentsDetail(models.Model):

    documents_id = models.AutoField(primary_key=True)

    documents_code = models.CharField(max_length= 50, null= False, blank= False, unique= True, default= None)

    document_type_id = models.ForeignKey(DocumentType, db_column = 'document_type_id', on_delete=models.SET_NULL, null= True)

    shop_id = models.ForeignKey(Shop, db_column = 'shop_id'  ,on_delete=models.CASCADE, null= False)

    loan_id = models.ForeignKey(LoanDetail,db_column = 'loan_id' , on_delete=models.CASCADE, null= True)

    contract_id = models.ForeignKey(ContractDetail, db_column = 'contract_id', on_delete=models.SET_NULL, null= True)

    documents_created_date = models.DateField(auto_now_add=False, null= False)

    folder_id = models.ForeignKey(Folder, db_column = 'folder_id', on_delete=models.CASCADE, null= True, blank= True)

    business_type_id = models.ForeignKey(BusinessType, db_column = 'business_type_id',on_delete=models.SET_NULL, null= True)

    manager_id = models.ForeignKey(Manager, db_column ='manager_id' ,  on_delete=models.CASCADE, null= False)

    status_id = models.ForeignKey(CheckingTransactionStatus,db_column = 'check_status_id', on_delete=models.CASCADE, null= True, blank= True)

    lastest_checked_date = models.DateTimeField(null=True, blank=True)

    lastest_checked_by = models.ForeignKey(User, db_column='lastest_checked_by', on_delete=models.CASCADE, null= True, blank= True)

    document_status_id = models.ForeignKey(DocumentStatus, db_column = 'document_status_id', on_delete=models.CASCADE, null= True, blank= True)

    note = models.TextField(null= True, blank= True) 

    package_id = models.ForeignKey( Package, db_column = 'package_id', on_delete=models.CASCADE, null= True, blank= True)

    is_pending_metadata = models.BooleanField(default=False)

    class Meta:

        db_table = 'f_DocumentsDetail'

        

    def __str__(self):

        return self.documents_code



# Đề xuất thay đổi khi nhận sai từ người dùng

class ChangeRequest(models.Model):

    class RequestType(models.TextChoices):

        FOLDER = 'folder', 'Folder'

        DOCUMENT = 'document', 'Document'

    class RequestStatus(models.TextChoices):

        PENDING = 'pending', 'Pending'

        DONE = 'done', 'Done'



    request_id = models.AutoField(primary_key=True)

    folder = models.ForeignKey(Folder, on_delete=models.CASCADE, null=True, blank=True)

    document = models.ForeignKey(DocumentsDetail, on_delete=models.CASCADE, null=True, blank=True)

    user = models.ForeignKey(User, on_delete=models.CASCADE)  # Người dùng đề xuất thay đổi

    created_date = models.DateTimeField(auto_now_add=True)

    request_type = models.CharField(max_length=50, choices=RequestType.choices)  # Lựa chọn loại request: folder hoặc document

    status = models.CharField(max_length=50, default='pending',choices=RequestStatus.choices )  # Trạng thái của request

    note = models.TextField(null=True, blank=True)

    class Meta:

        db_table = 'f_Change_request'



    def __str__(self):

        return self.request_type #f"Request {self.request_type} for {self.document if self.request_type == 'document' else self.folder}"



class CheckingAdditional(models.Model):

    additional = models.OneToOneField( DocumentsDetail, db_column='additional', on_delete=models.CASCADE, null= False, unique= True)    

    additional_note = models.TextField( null= True, blank= True)

    date_addition = models.DateField( auto_now_add=False, null= True, blank= True)

    additional_created_date = models.DateTimeField( auto_now_add=True, null= True)

    additional_created_by = models.ForeignKey( User, db_column='additional_created_by',on_delete=models.CASCADE, null= False)

    additional_updated_date = models.DateTimeField( auto_now_add=False, null= True, blank= True) 

    is_valid = models.BooleanField(default= True) # Mặc định khi mới tạo thì là True 

    

    class Meta:

        db_table = 'f_CheckingAdditional'



# Các Giao dịch kiểm chứng từ

class DocumentsTransactionChecking(models.Model): 

    trans_id = models.AutoField(primary_key=True)

    documents_id = models.ForeignKey( DocumentsDetail, db_column='documents_id', on_delete=models.CASCADE, null= False)

    trans_created_date = models.DateTimeField( auto_now_add=True, null= False)

    trans_created_by = models.ForeignKey(User, db_column= 'trans_created_by',related_name='checking_created_transaction' ,on_delete=models.CASCADE, null= True)

    trans_updated_date = models.DateTimeField(auto_now_add=False, null= True, blank= True)

    trans_updated_by = models.ForeignKey( User,db_column= 'trans_updated_by',related_name='checking_updated_transaction' , on_delete=models.CASCADE, null= True, blank= True) 

    checking_status_id = models.ForeignKey( CheckingTransactionStatus,db_column = 'checking_status_id', on_delete=models.CASCADE, null= True) 

                  

    class Meta:

        db_table = 'f_DocumentsTransactionChecking'



# Các giao dịch nhận quyển chứng từ 

class FoldersTransactionReceiving(models.Model):

    trans_id = models.AutoField(primary_key=True)

    folder_id = models.ForeignKey(Folder, db_column = 'folder_id', on_delete=models.CASCADE, null= False)

    trans_created_date = models.DateTimeField(auto_now_add=True, null= True)

    trans_created_by = models.ForeignKey(User, db_column = 'trans_created_by',related_name='folder_created_transactions', on_delete=models.CASCADE, null= True)

    trans_updated_date = models.DateTimeField(auto_now_add=False, null= True,blank= True)

    trans_updated_by = models.ForeignKey(User, db_column = 'trans_updated_by', related_name='folder_upated_transactions' ,on_delete=models.CASCADE, null= True)

    folder_status_id = models.ForeignKey(FolderStatus, db_column = 'folder_status_id', on_delete=models.CASCADE, null= True, blank= True)

     

    class Meta:

        db_table = 'f_FoldersTransactionReceiving'

 

 # Lịch sử luân chuyển Thùng - chứng từ

class PackageDocumentHistory(models.Model): 

    trans_id = models.AutoField(primary_key=True)

    document_id = models.ForeignKey( DocumentsDetail, db_column='document_id', on_delete=models.CASCADE, null= False)

    package_id = models.ForeignKey( Package, db_column='package_id', on_delete=models.CASCADE, null= False)

    trans_created_date = models.DateTimeField(auto_now_add=True, null= True) 

    trans_created_by = models.ForeignKey(User, db_column='trans_created_by',related_name='documentpackage_created_transactions', on_delete=models.CASCADE, null= True)

    

    class Meta:

        db_table = 'f_PackageDocumentHistory'



# Lịch sử luân chuyển thùng - quyển chứng từ

class PackageFolderHistory(models.Model):

    trans_id = models.AutoField(primary_key=True)

    folder_id = models.ForeignKey(Folder, db_column='folder_id', on_delete=models.CASCADE, null= False)

    package_id = models.ForeignKey( Package, db_column='package_id', on_delete=models.CASCADE, null= False)

    trans_created_date = models.DateTimeField(auto_now_add=True, null= True) 

    trans_created_by = models.ForeignKey(User, db_column='trans_created_by', related_name='folderpackage_created_transactions', on_delete=models.CASCADE, null= True)



    class Meta:

        db_table = 'f_PackageFolderHistory'



# Trạng thái giao dịch mượn chứng từ 

class BorrowingStatus(models.Model):

    borrow_status_id = models.AutoField(primary_key=True)

    borrow_status_code = models.CharField(max_length= 3, null= False, blank= False, unique= True, default= None)

    borrow_status_name = models.CharField(max_length= 255, null= False, blank= False, unique= True, default= None)

    flag_return = models.BooleanField(default=False)

    flag_is_borrowing = models.BooleanField(default=False)

    flag_is_lost = models.BooleanField(default=False)

    badge_color = models.CharField(max_length=50, null= True ) 

    class Meta: 

        db_table = 'd_BorrowingStatus'



class GapoScheduledMessage(models.Model):
    class Status(models.TextChoices):

        PENDING = "pending", "Pending"

        SENT = "sent", "Sent"

        FAILED = "failed", "Failed"

        CANCELLED = "cancelled", "Cancelled"



    class TargetType(models.TextChoices):

        RECEIVER = "receiver", "Người nhận"

        THREAD = "thread", "Cuộc hội thoại"

        COLLAB = "collab", "Nhóm cộng tác"



    class BodyType(models.TextChoices):

        TEXT = "text", "Text"

        QUICK_REPLIES = "quick_replies", "Quick replies"

        CAROUSEL = "carousel", "Carousel"

        DYNAMIC = "dynamic", "Dynamic"



    id = models.AutoField(primary_key=True)

    receiver_id = models.CharField(max_length=50, blank=True, default="")

    thread_id = models.BigIntegerField(null=True, blank=True)

    collab_id = models.CharField(max_length=50, blank=True, default="")

    message = models.TextField()

    body_type = models.CharField(

        max_length=30,

        choices=BodyType.choices,

        default=BodyType.TEXT,

    )

    body_metadata = models.JSONField(default=dict, blank=True)

    schedule_at = models.DateTimeField()

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    sent_at = models.DateTimeField(null=True, blank=True)

    last_error = models.TextField(null=True, blank=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="gapo_schedules")

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)



    class Meta:

        db_table = "f_GapoScheduledMessage"

        ordering = ["-created_at"]



    def __str__(self):

        return f"{self.get_target_type_display()}: {self.target_value}"



    @property

    def target_type(self):

        if self.thread_id:

            return self.TargetType.THREAD

        if self.collab_id:

            return self.TargetType.COLLAB

        return self.TargetType.RECEIVER



    @property

    def target_value(self):
        if self.thread_id:
            return str(self.thread_id)
        if self.collab_id:
            return self.collab_id
        return self.receiver_id

    def get_target_type_display(self):
        return self.TargetType(self.target_type).label


class GapoWebhookEvent(models.Model):
    event_type = models.CharField(max_length=100, blank=True, default="")
    bot_id = models.CharField(max_length=50, blank=True, default="")
    message_id = models.CharField(max_length=100, blank=True, default="")
    thread_id = models.CharField(max_length=50, blank=True, default="")
    collab_id = models.CharField(max_length=50, blank=True, default="")
    sender_id = models.CharField(max_length=50, blank=True, default="")
    message_text = models.TextField(blank=True, default="")
    http_method = models.CharField(max_length=10, blank=True, default="POST")
    request_path = models.CharField(max_length=255, blank=True, default="")
    remote_addr = models.CharField(max_length=64, blank=True, default="")
    headers = models.JSONField(default=dict, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    raw_body = models.TextField(blank=True, default="")
    is_json_valid = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "f_GapoWebhookEvent"
        ordering = ["-created_at"]

    def __str__(self):
        return self.event_type or f"Webhook event #{self.pk}"
     
# Các giao dịch mượn chứng từ 
class BorrowingDocument(models.Model):
    borrow_id = models.AutoField(primary_key=True)

    documents_id = models.ForeignKey( DocumentsDetail, db_column='documents_id', on_delete=models.CASCADE)

    borrow_date = models.DateField(auto_now_add=False, null= False) # Ngày mượn chứng từ

    appointment_date = models.DateField(auto_now_add=False, null= True) # Ngày hẹn trả chứng từ

    lender = models.ForeignKey(User, db_column='lender', related_name= 'lender', on_delete=models.CASCADE, null= False) # Người cho mượn

    borrower = models.ForeignKey(Shop, db_column='borrower', related_name='borrower' ,on_delete=models.CASCADE, null= False)# Người mượn

    borrower_detail = models.CharField(max_length= 255, null= True, blank= True, unique= False, default= None) # Người mượn ghi rõ họ tên

    return_date = models.DateField(auto_now_add=False, null= True) # Ngày trả chứng từ

    ticket_code = models.CharField(max_length= 50, null= True, blank= True, unique= False, default= None) # Mã phiếu mượn chứng từ

    note = models.TextField(null= True, blank= True)

    borrow_status_id = models.ForeignKey(BorrowingStatus, db_column='borrow_status_id', on_delete=models.CASCADE, null= True)

    class Meta:

        db_table = 'f_BorrowingDocument'

        

    def __str__(self):

        return f"{self.documents_id.documents_code}"





class BorrowRequestStatus(models.TextChoices):

    DRAFT = "draft", "Nháp"

    PENDING = "pending", "Chờ xử lý"

    ASSIGNED = "assigned", "Đã gán chứng từ"

    HANDED_OVER = "handed_over", "Đã bàn giao"

    PARTIALLY_RETURNED = "partially_returned", "Trả một phần"

    RETURNED = "returned", "Đã trả"

    CANCELLED = "cancelled", "Hủy"

    REJECTED = "rejected", "Từ chối"





class BorrowRequestItemStatus(models.TextChoices):

    PENDING = "pending", "Chờ gán"

    ASSIGNED = "assigned", "Đã gán"

    HANDED_OVER = "handed_over", "Đã bàn giao"

    RETURNED = "returned", "Đã trả"

    LOST = "lost", "Báo mất"

    CANCELLED = "cancelled", "Hủy"





class BorrowRequest(models.Model):
    request_id = models.AutoField(primary_key=True)
    borrower = models.ForeignKey(Shop, db_column="borrower", related_name="borrow_requests", on_delete=models.CASCADE)
    requester = models.ForeignKey(User, db_column="requester", related_name="borrow_requesters", on_delete=models.SET_NULL, null=True, blank=True)
    contact_recipient = models.ForeignKey(
        "app_admindocuments.AdmParcelRecipientCatalog",
        db_column="contact_recipient_id",
        related_name="borrow_requests",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    contact_name = models.CharField(max_length=255, null=True, blank=True)
    contact_employee_code = models.CharField(max_length=50, null=True, blank=True)
    contact_gapo_user_id = models.CharField(max_length=100, null=True, blank=True)
    reference_code = models.CharField(max_length=50, null=True, blank=True)
    needed_date = models.DateField(auto_now_add=False, null=False)
    appointment_date = models.DateField(auto_now_add=False, null=True, blank=True)

    ticket_code = models.CharField(max_length=100, null=True, blank=True)

    contact_email = models.EmailField(null=True, blank=True)

    contact_phone = models.CharField(max_length=30, null=True, blank=True)

    note = models.TextField(null=True, blank=True)

    status = models.CharField(max_length=30, choices=BorrowRequestStatus.choices, default=BorrowRequestStatus.PENDING)

    source_system = models.CharField(max_length=50, null=True, blank=True)

    external_ref = models.CharField(max_length=100, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.ForeignKey(User, db_column="created_by", related_name="borrow_request_created", on_delete=models.SET_NULL, null=True, blank=True)

    updated_by = models.ForeignKey(User, db_column="updated_by", related_name="borrow_request_updated", on_delete=models.SET_NULL, null=True, blank=True)



    class Meta:

        db_table = "f_BorrowRequest"



    def __str__(self):

        return f"BorrowRequest {self.request_id}"





class BorrowRequestItem(models.Model):

    item_id = models.AutoField(primary_key=True)

    borrow_request = models.ForeignKey(BorrowRequest, db_column="request_id", related_name="items", on_delete=models.CASCADE)

    documents_id = models.ForeignKey(DocumentsDetail, db_column="documents_id", related_name="borrow_request_items", on_delete=models.SET_NULL, null=True, blank=True)

    appointment_date = models.DateField(auto_now_add=False, null=True, blank=True)

    status = models.CharField(max_length=30, choices=BorrowRequestItemStatus.choices, default=BorrowRequestItemStatus.PENDING)

    note = models.TextField(null=True, blank=True)

    handed_over_date = models.DateTimeField(null=True, blank=True)

    return_date = models.DateTimeField(null=True, blank=True)

    legacy_borrowing = models.ForeignKey(BorrowingDocument, db_column="borrow_id", related_name="request_items", on_delete=models.SET_NULL, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.ForeignKey(User, db_column="created_by", related_name="borrow_request_item_created", on_delete=models.SET_NULL, null=True, blank=True)

    updated_by = models.ForeignKey(User, db_column="updated_by", related_name="borrow_request_item_updated", on_delete=models.SET_NULL, null=True, blank=True)



    class Meta:

        db_table = "f_BorrowRequestItem"



    def __str__(self):

        return f"BorrowRequestItem {self.item_id}"





class BorrowRequestLog(models.Model):

    log_id = models.AutoField(primary_key=True)

    borrow_request = models.ForeignKey(BorrowRequest, db_column="request_id", related_name="logs", on_delete=models.CASCADE)

    item = models.ForeignKey(BorrowRequestItem, db_column="item_id", related_name="logs", on_delete=models.SET_NULL, null=True, blank=True)

    action = models.CharField(max_length=50)

    from_status = models.CharField(max_length=30, null=True, blank=True)

    to_status = models.CharField(max_length=30, null=True, blank=True)

    note = models.TextField(null=True, blank=True)

    meta = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    created_by = models.ForeignKey(User, db_column="created_by", related_name="borrow_request_logs", on_delete=models.SET_NULL, null=True, blank=True)



    class Meta:

        db_table = "f_BorrowRequestLog"



    def __str__(self):

        return f"BorrowRequestLog {self.log_id}"

    

class HistoricalFolder(models.Model):

    folder_id = models.AutoField(primary_key=True)

    folder_code = models.CharField(max_length=50, null=True, blank=True, unique=True)  # Mã quyển chứng từ

    shop = models.ForeignKey(Shop, db_column='shop_id', on_delete=models.SET_NULL, null=True, blank=True) 

    folder_type = models.ForeignKey(FolderType, db_column='folder_type_id', on_delete=models.SET_NULL, null=True, blank=True)

    package = models.ForeignKey(Package, db_column='package_id', on_delete=models.SET_NULL, null=True, blank=True)

    folder_status = models.ForeignKey(FolderStatus, db_column='folder_status_id', on_delete=models.SET_NULL, null=True, blank=True)

    region = models.ForeignKey(Region, db_column = 'region_id', on_delete=models.CASCADE, null= True)

    folder_created_date = models.DateField(auto_now_add=False, null= False)

    additional_data = models.JSONField(null=True, blank=True)  # Lưu trữ các dữ liệu linh hoạt khác

    archived_at = models.DateTimeField(auto_now_add=True)  # Thời gian được migrate lên hệ thống

    created_by = models.ForeignKey(User, db_column='created_by', on_delete=models.SET_NULL, null=True)  # Người lưu trữ

    is_original = models.BooleanField(default= True) # True: Quyển từ gốc, False: Quyển bổ sung

    is_issue = models.BooleanField(null=True) # True: quyển có chứng từ , False: Quyển không có chứng từ

    note = models.TextField(null= True, blank= True) 

    class Meta:

        db_table = 'historical_folder'

    

class HistoricalDocuments(models.Model):

    documents_id = models.AutoField(primary_key=True)

    documents_code = models.CharField(max_length=50, null=True, blank=True, unique=True)  # Mã chứng từ

    shop = models.ForeignKey(Shop, db_column='shop_id', on_delete=models.SET_NULL, null=True, blank=True)

    loan = models.ForeignKey(LoanDetail, db_column='loan_id', on_delete=models.SET_NULL, null=True, blank=True)

    package = models.ForeignKey(Package, db_column='package_id',on_delete=models.SET_NULL ,null=True, blank=True)

    region = models.ForeignKey(Region, db_column = 'region_id', on_delete=models.CASCADE, null= True)

    business_type = models.CharField(max_length= 500, db_column='business_type_name', null=True, blank=True)

    document_type = models.TextField(db_column='document_type_name', null=True, blank=True) 

    additional_data = models.JSONField(null=True, blank=True)  # Lưu trữ các dữ liệu linh hoạt khác không có structure

    archived_at = models.DateTimeField(auto_now_add=True)  # Thời gian được migrate

    created_by = models.ForeignKey(User, db_column='created_by', on_delete=models.SET_NULL, null=True)  # Người lưu trữ

    condition = models.TextField(null= True, blank= True) # Tình trạng chứng từ lưu free text

    is_original = models.BooleanField(default= True) # True: Quyển từ gốc, False: Quyển bổ sung

    is_issue = models.BooleanField(null=True) # True: quyển có chứng từ , False: Quyển không có chứng từ

    note =  models.TextField(null= True, blank= True) 

    class Meta:

        db_table = 'historical_documents'



class DocumentKpiSetting(models.Model):

    metric_code = models.CharField(max_length=60, unique=True)

    metric_name = models.CharField(max_length=255)

    target_rate = models.DecimalField(max_digits=6, decimal_places=2, default=90.0)

    is_active = models.BooleanField(default=True)

    updated_by = models.ForeignKey(User, db_column='updated_by', on_delete=models.SET_NULL, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)



    class Meta:

        db_table = 'd_DocumentKpiSetting'



    def __str__(self):

        return self.metric_name





class UserPresenceDaily(models.Model):

    user = models.ForeignKey(User, db_column='user_id', on_delete=models.CASCADE, related_name='presence_daily')

    work_date = models.DateField()

    first_seen_at = models.DateTimeField(null=True, blank=True)

    last_seen_at = models.DateTimeField(null=True, blank=True)

    total_active_seconds = models.PositiveIntegerField(default=0)

    total_active_minutes = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)



    class Meta:

        db_table = 'f_UserPresenceDaily'

        unique_together = ('user', 'work_date')

        ordering = ['-work_date', '-last_seen_at']



    def __str__(self):

        return f"{self.user.username} - {self.work_date}"





class UserPresenceHourly(models.Model):

    user = models.ForeignKey(User, db_column='user_id', on_delete=models.CASCADE, related_name='presence_hourly')

    work_date = models.DateField()

    hour = models.PositiveSmallIntegerField()

    active_seconds = models.PositiveIntegerField(default=0)

    first_seen_at = models.DateTimeField(null=True, blank=True)

    last_seen_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)



    class Meta:

        db_table = 'f_UserPresenceHourly'

        unique_together = ('user', 'work_date', 'hour')

        ordering = ['-work_date', '-hour']



    def __str__(self):

        return f"{self.user.username} - {self.work_date} {self.hour:02d}:00"

    

