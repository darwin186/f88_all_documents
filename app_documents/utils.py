# utils.py
from django.contrib.auth.models import User
from .models import UserProfile, UiScreen, UiPermission
from datetime import datetime, timedelta
from app_documents.models import Folder,FolderGroup 
from calendar import monthrange
from django.utils import timezone
from django.db import transaction

UI_SCREENS = [
    {'key': 'receiving_v2', 'name': 'Nhận chứng từ v2', 'path': '/nhan-chung-tu-v2', 'group': 'documents'},
    {'key': 'receiving_import_v2', 'name': 'Import nhận chứng từ', 'path': '/nhan-chung-tu-v2/import', 'group': 'documents'},
    {'key': 'checking_v2', 'name': 'Duyệt chứng từ v2', 'path': '/duyet-chung-tu-v2', 'group': 'documents'},
    {'key': 'gddb_registration', 'name': 'Giao dịch bảo đảm', 'path': '/giao-dich-dam-bao/', 'group': 'documents'},
    {'key': 'kpi_v2', 'name': 'Chỉ tiêu chứng từ v2', 'path': '/chi-tieu-chung-tu-v2', 'group': 'kpi'},
    {'key': 'package_v2', 'name': 'Quản lý thùng v2', 'path': '/package-list-management', 'group': 'package'},
    {'key': 'borrow_request_v2', 'name': 'Yêu cầu mượn v2', 'path': '/yeu-cau-muon-chung-tu-v2/', 'group': 'borrow'},
    {'key': 'borrow_manage_v2', 'name': 'Quản lý mượn v2', 'path': '/quan-ly-muon-chung-tu-v2/', 'group': 'borrow'},
    {'key': 'ctv_accounts', 'name': 'Quản lý tài khoản CTV', 'path': '/quan-ly-tai-khoan-ctv/', 'group': 'admin'},
    {'key': 'workshift_register', 'name': 'Lịch làm việc', 'path': '/lich-lam-viec/', 'group': 'workshift'},
    {'key': 'workshift_tasks', 'name': 'Phân công công việc', 'path': '/lich-lam-viec/tasks/', 'group': 'workshift'},
    {'key': 'workshift_policy', 'name': 'Cấu hình ca làm việc', 'path': '/lich-lam-viec/policy/', 'group': 'workshift'},
    {'key': 'profile', 'name': 'Thông tin cá nhân', 'path': '/thong-tin-ca-nhan/', 'group': 'account'},
    {'key': 'ui_permission', 'name': 'Phân quyền UI', 'path': '/phan-quyen-ui-v2/', 'group': 'admin'},
]

ROLE_CODES = [
    ('super_admin', 'Super Admin'),
    ('admin', 'Admin'),
    ('checker', 'Checker'),
    ('shop', 'PGD'),
    ('supervisor', 'Supervisor'),
    ('risk', 'Risk'),
]


def _default_can_view(screen_key, role_code):
    if role_code in ('admin', 'super_admin'):
        return True
    return screen_key == 'gddb_registration' and role_code == 'checker'


def get_role_codes(user):
    roles = []
    if user.is_superuser:
        roles.append('super_admin')
    if user.groups.filter(name='admin').exists():
        roles.append('admin')
    if user.groups.filter(name='checker').exists():
        roles.append('checker')
    if user.groups.filter(name='shop').exists():
        roles.append('shop')
    if user.groups.filter(name='supervisor').exists():
        roles.append('supervisor')
    if user.groups.filter(name='risk').exists():
        roles.append('risk')
    return roles


def ensure_ui_screens():
    existing = {s.screen_key: s for s in UiScreen.objects.all()}
    to_create = []
    for screen in UI_SCREENS:
        if screen['key'] not in existing:
            to_create.append(UiScreen(
                screen_key=screen['key'],
                screen_name=screen['name'],
                screen_path=screen.get('path'),
                screen_group=screen.get('group'),
            ))
    if to_create:
        UiScreen.objects.bulk_create(to_create)
    existing_pairs = set(UiPermission.objects.values_list('screen__screen_key', 'role_code'))
    screens = UiScreen.objects.all()
    missing_permissions = []
    for screen in screens:
        for code, _ in ROLE_CODES:
            if (screen.screen_key, code) in existing_pairs:
                continue
            missing_permissions.append(UiPermission(
                screen=screen,
                role_code=code,
                can_view=_default_can_view(screen.screen_key, code),
            ))
    if missing_permissions:
        UiPermission.objects.bulk_create(missing_permissions)
    if not UiPermission.objects.exists():
        screens = UiScreen.objects.all()
        perms = []
        for screen in screens:
            for code, _ in ROLE_CODES:
                perms.append(UiPermission(
                    screen=screen,
                    role_code=code,
                    can_view=_default_can_view(screen.screen_key, code),
                ))
        if perms:
            UiPermission.objects.bulk_create(perms)


def get_allowed_screens(user):
    if user.is_superuser:
        return {s['key'] for s in UI_SCREENS}
    ensure_ui_screens()
    role_codes = get_role_codes(user)
    if not role_codes:
        return set()
    permissions = UiPermission.objects.filter(role_code__in=role_codes, can_view=True).select_related('screen')
    if UiPermission.objects.exists() and not permissions.exists():
        return set()
    if not UiPermission.objects.exists() and not permissions.exists():
        # fallback: allow all if no permission configured yet
        return {s['key'] for s in UI_SCREENS}
    return {p.screen.screen_key for p in permissions}


def require_ui_permission(screen_key):
    def decorator(view_func):
        def _wrapped(request, *args, **kwargs):
            allowed = get_allowed_screens(request.user)
            if screen_key not in allowed:
                from django.contrib import messages
                from django.shortcuts import redirect
                messages.error(request, 'Bạn không có quyền truy cập màn hình này.')
                return redirect('home')
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator

def get_user_context(user):
    profile = UserProfile.objects.get(user=user)
    is_super_admin = user.is_superuser
    is_admin = user.groups.filter(name='admin').exists()
    is_checker = user.groups.filter(name='checker').exists()
    is_shop_user = user.groups.filter(name='shop').exists()
    is_risk = user.groups.filter(name='risk').exists()
    is_supervisor = user.groups.filter(name='supervisor').exists()
    
    allowed_screens = get_allowed_screens(user)
    context = {
        'is_super_admin': is_super_admin, # Quyền bự nhất
        'is_admin': is_admin, # Quyền quản trị viên
        'is_checker': is_checker, # Cộng tác viên kiểm duyệt
        'is_shop_user': is_shop_user, # Tài khoản của cửa hàng
        'is_risk': is_risk, # Tài khoản của phòng rủi ro
        'is_supervisor': is_supervisor, # Tài khoản của qlkv qlv 
        'user': user,
        'profile': profile,
        'allowed_screens': allowed_screens,
    }
    return context

def check_group(folder):
    """Hàm kiểm tra và gán group cho một folder dựa trên ngày tạo (folder_created_date). 
    Sau khi được gán group, quyển sẽ được đánh dấu group. Sau khi gán thành công sẽ gỡ 
    flag is_out_of_group. 
    """
    if not folder.folder_created_date:
        raise ValueError("Folder must have a created date to determine its group.")

    created_day = folder.folder_created_date.day

    # Tìm group phù hợp dựa vào `day_from` và `day_to`
    matching_group = FolderGroup.objects.filter(
        day_from__lte=created_day,
        day_to__gte=created_day,
        is_active=True
    ).first()

    # Gán group cho folder nếu tìm thấy
    if matching_group:
        folder.group = matching_group
        folder.is_out_of_group = False
        folder.save(update_fields=['group', 'is_out_of_group'])
    else:
        # Nếu không tìm thấy group phù hợp, đánh dấu is_out_of_group là True
        folder.is_out_of_group = True
        folder.save(update_fields=['is_out_of_group'])

def assign_group_to_folders():
    """Hàm gán group cho tất cả các folder có `is_out_of_group=True`."""
    folders = Folder.objects.filter(is_out_of_group=True)
    for folder in folders:
        check_group(folder)
        
def check_on_time(folder, lasted_received_date_submit):
    """
    Kiểm tra/cập nhật trạng thái đúng hạn và trả về dữ liệu cấu trúc để hiển thị.
    Trả về dict: {'deadline': date|None, 'received_date': date|None, 'is_on_time': bool|None, 'message': str}
    """
    result = {"deadline": None, "received_date": None, "is_on_time": None, "message": ""}
    try:
        deadline = None
        received_date = None
        if folder.group:
            rule = folder.group.rule_deadline
            if rule and rule.is_valid:
                created_month = folder.folder_created_date.month
                created_year = folder.folder_created_date.year
                day_to = folder.group.day_to

                if rule.next_month:
                    # Chuyển sang tháng kế tiếp và dùng deadline_day làm ngày trong tháng đích
                    deadline_year = created_year + 1 if created_month == 12 else created_year
                    deadline_month = 1 if created_month == 12 else created_month + 1
                    last_day_target = monthrange(deadline_year, deadline_month)[1]
                    target_day = min(rule.deadline_day, last_day_target)
                    deadline_date = datetime(deadline_year, deadline_month, target_day)
                else:
                    # Dùng day_to (có clamp cuối tháng) rồi cộng offset deadline_day
                    last_day_current = monthrange(created_year, created_month)[1]
                    base_day = min(day_to, last_day_current)
                    deadline_date = datetime(created_year, created_month, base_day) + timedelta(days=rule.deadline_day)

                deadline = deadline_date
                if timezone.is_naive(deadline):
                    deadline = timezone.make_aware(deadline, timezone.get_current_timezone())

                received_date = lasted_received_date_submit or folder.lastest_received_date
                if received_date and timezone.is_naive(received_date):
                    received_date = timezone.make_aware(received_date, timezone.get_current_timezone())

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
            else:
                folder.is_on_time = None
                folder.is_late = None

        folder.save(update_fields=['is_on_time', 'is_late'])
        result["deadline"] = deadline.date() if deadline else None
        result["received_date"] = received_date.date() if received_date else None
        result["is_on_time"] = folder.is_on_time
        if deadline and received_date:
            status_text = "đúng hạn" if folder.is_on_time else "trễ hạn"
            result["message"] = f"Nhận ngày {received_date.date()} so với hạn {deadline.date()} → {status_text}"
        else:
            result["message"] = "Đã kiểm tra trạng thái đúng/trễ hạn."
        return result
    except Exception as e:
        print(f"Error in check_on_time: {e}")
        result["message"] = "Lỗi khi kiểm tra hạn nhận."
        return result

     
