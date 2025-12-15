# utils.py
from django.contrib.auth.models import User
from .models import UserProfile 
from datetime import datetime, timedelta
from app_documents.models import Folder,FolderGroup 
from calendar import monthrange
from django.utils import timezone

def get_user_context(user):
    profile = UserProfile.objects.get(user=user)
    is_super_admin = user.is_superuser
    is_admin = user.groups.filter(name='admin').exists()
    is_checker = user.groups.filter(name='checker').exists()
    is_shop_user = user.groups.filter(name='shop').exists()
    is_risk = user.groups.filter(name='risk').exists()
    is_supervisor = user.groups.filter(name='supervisor').exists()
    
    context = {
        'is_super_admin': is_super_admin, # Quyền bự nhất
        'is_admin': is_admin, # Quyền quản trị viên
        'is_checker': is_checker, # Cộng tác viên kiểm duyệt
        'is_shop_user': is_shop_user, # Tài khoản của cửa hàng
        'is_risk': is_risk, # Tài khoản của phòng rủi ro
        'is_supervisor': is_supervisor, # Tài khoản của qlkv qlv 
        'user': user,
        'profile': profile,
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

     
