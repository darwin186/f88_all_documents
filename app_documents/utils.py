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
    """Hàm kiểm tra và cập nhật trạng thái đúng hạn (on time) của một folder dựa trên group đã gán."""
    try:
        deadline = None
        received_date = None
        # Kiểm tra xem folder có được gán group hay không
        if folder.group : # and folder.is_original and folder.is_issue:
            # Lấy rule từ group đã gán cho folder
            rule = folder.group.rule_deadline
            if rule and rule.is_valid:
                created_month = folder.folder_created_date.month
                created_year = folder.folder_created_date.year
                day_to = folder.group.day_to

                # Tính toán năm và tháng cho deadline
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
                if timezone.is_naive(deadline):
                    deadline = timezone.make_aware(deadline, timezone.get_current_timezone())

                # Sử dụng `lasted_received_date_submit` nếu có, nếu không thì dùng `folder.lastest_received_date`
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
                # Nếu không có rule hoặc rule không hợp lệ
                folder.is_on_time = None
                folder.is_late = None

        # Lưu lại folder sau khi kiểm tra
        folder.save(update_fields=['is_on_time', 'is_late'])
        if deadline and received_date:
            return f"Thời gian nhận thực tế: {received_date.date()} so với hạn deadline {deadline.date()}"
        return "Folder on-time status checked without deadline comparison."
    except Exception as e:
        # Xử lý lỗi, nếu cần thiết
        print(f"Error in check_on_time: {e}")

     
