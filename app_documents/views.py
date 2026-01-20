from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.urls import reverse, path
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.views import PasswordResetView
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone, dateparse
from django.utils.dateparse import parse_datetime
from django.conf import settings
from django.db import IntegrityError, transaction, connection
from django.db.models import Count, Max, Q, Min, Prefetch
from django.forms.models import model_to_dict
from django.core.serializers.json import DjangoJSONEncoder
from urllib.parse import urlencode
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
import csv
import json
import re
import logging
import os
import secrets
import requests
import pandas as pd
from datetime import datetime, timedelta
import calendar
from django.db.models.functions import ExtractHour, TruncMonth
import openpyxl
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo
from io import BytesIO
# Import các model
from .models import (
    Manager,
    Shop,
    DocumentType,
    BusinessType,
    FolderType,
    DocumentsDetail, 
    LoanDetail, 
    ContractDetail,
    Employee,
    LoanCustomer,
    CheckingTransactionStatus, 
    DocumentsTransactionChecking, 
    FoldersTransactionReceiving,
    UserProfile,
    CheckingAdditional, 
    DocumentStatus,
    PackageDocumentHistory,
    FolderStatus,
    Folder,
    PackageFolderHistory,
    Package,
    PartnerPackage,
    PartnerPackageStatus,
    PartnerPackageHistory,
    Partner,
    Region,
    HistoricalFolder,
    HistoricalDocuments,
    DocumentKpiSetting,
    ChangeRequest,
    BorrowingDocument,
    BorrowingStatus,
    BorrowRequest,
    BorrowRequestItem,
    BorrowRequestLog,
    BorrowRequestStatus,
    BorrowRequestItemStatus,
    GapoScheduledMessage
)
# Import các form
from .forms import PackageForm, GapoPasswordResetForm, GapoScheduleForm
# Import các custom utilities
from .access_controls import AccessControls
from .utils import get_user_context, check_on_time
from .dashboard import parse_dates, get_dashboard_metrics, get_folder_received_metrics
from .tasks import send_gapo_scheduled_message

AI_STYLE_HINTS = {
    "formal": "Viết ngắn gọn, lịch sự, trang trọng, dùng đại từ phù hợp công việc.",
    "friendly": "Viết thân thiện, gần gũi, rõ ràng, tránh từ ngữ quá trang trọng.",
    "fun": "Viết vui vẻ, dí dỏm, tích cực nhưng vẫn lịch sự.",
}
class CustomPasswordResetView(PasswordResetView):
    form_class = GapoPasswordResetForm
    email_template_name = 'registration/password_reset_email.html'
    subject_template_name = 'registration/password_reset_subject.txt'
    html_email_template_name = 'registration/password_reset_email.html'
    
    def form_valid(self, form):
        gapo_url = getattr(settings, 'GAPO_API_URL', '')
        gapo_api_key = getattr(settings, 'GAPO_BOT_API_KEY', '')
        gapo_bot_id = getattr(settings, 'GAPO_BOT_ID', '')
        if not (gapo_url and gapo_api_key and gapo_bot_id):
            messages.error(self.request, "Chưa cấu hình GAPO bot. Liên hệ quản trị.")
            return self.form_invalid(form)
        user = form.get_user()
        if not user:
            messages.error(self.request, "Không tìm thấy tài khoản phù hợp.")
            return self.form_invalid(form)
        try:
            self._send_gapo_reset(user, gapo_url, gapo_api_key, gapo_bot_id)
            messages.success(self.request, "Thông tin đã được gửi qua địa chỉ GAPO của bạn.")
            return HttpResponseRedirect(self.get_success_url())
        except ValueError as ve:
            messages.error(self.request, str(ve))
        except Exception as exc:
            logger.error("Gửi reset password qua GAPO thất bại", exc_info=exc)
            messages.error(self.request, "Gửi qua GAPO thất bại. Vui lòng thử lại sau.")
        return self.form_invalid(form)

    def _send_gapo_reset(self, user, gapo_url, gapo_api_key, gapo_bot_id):
        profile = getattr(user, "userprofile", None)
        gapo_user_id = getattr(profile, "gapo_user_id", None)
        if not gapo_user_id:
            raise ValueError(f"User {user.username} chưa có GAPO ID. Liên hệ admin để cập nhật.")
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = self.token_generator.make_token(user)
        reset_path = reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
        reset_url = self.request.build_absolute_uri(reset_path)
        payload = {
            "bot_id": gapo_bot_id,
            "receiver_id": int(gapo_user_id),
            "body": {
                "type": "text",
                "text": f"Bạn yêu cầu đặt lại mật khẩu. Nhấn vào liên kết sau để đặt lại: {reset_url}",
                "is_markdown_text": True
            },
        }
        headers = {
            "x-gapo-api-key": gapo_api_key,
            "Content-Type": "application/json",
        }
        print(payload)
        response = requests.post(gapo_url, json=payload, headers=headers, timeout=10)
        if response.status_code >= 400:
            print(response.text)
            raise ValueError(f"GAPO trả về lỗi {response.status_code}: {response.text}")
        
logger = logging.getLogger(__name__)

@login_required
def switch_region(request, region_id):
    user_profile = UserProfile.objects.get(user=request.user)  # Lấy UserProfile của user hiện tại
    try:
        # Tìm region dựa trên region_id từ URL và kiểm tra quyền truy cập
        selected_region = Region.objects.get(region_id=region_id)  # Lấy Region từ region_id
        # Cập nhật region trong UserProfile
        user_profile.region = selected_region
        user_profile.save()  # Lưu thay đổi vào database
        # Cập nhật region_id vào session
        request.session['region_id'] = selected_region.region_id
        messages.success(request, f"Bạn đã chuyển sang vùng {selected_region.region_name}")
    except Region.DoesNotExist:
        messages.error(request, "Vùng không tồn tại hoặc bạn không có quyền truy cập. Vui lòng thử lại.")

    return redirect(request.META.get('HTTP_REFERER', 'home'))  # Chuyển hướng lại trang trước đó hoặc về trang chủ

@login_required
def home_view(request): 
    # Get user context from the utility function
    user = request.user
    user_context = get_user_context(user)
    regions = Region.objects.all()
    context = {
        **user_context,
          'user': user,
           'regions':regions
          }
    return render(request, 'home.html', context)

def handle_400(request, exception):
    return render(request, '400.html', status=400)

def handle_500(request):
    return render(request, '500.html', status=500)

#---------------------CHECKING TRANSACTION---------------------
# view danh sách chứng từ
@login_required
def checking_transaction_view(request, template_name="app_documents/app_checkingtransaction.html", redirect_name="checking_transaction"):
    user = request.user
    user_context = get_user_context(user)
    documents_detail = DocumentsDetail.objects.none()  # Khởi tạo documents_detail là None 
    if not user_context['is_admin'] and not user_context['is_checker']:
        return redirect('home')
    else:
        #Handle GET requests từ form duyệt chứng từ 
        if request.method == 'GET':
            filters = {}
            choice_shop = request.GET.get('choice_shop')
            choice_loan_code = request.GET.get('choice_loan_code')
            choice_contract_code = request.GET.get('choice_contract_code')
            choice_user_duyet = request.GET.get('choice_user_duyet')
            choice_check_date = request.GET.get('filtercheckdate')
            choice_document_date = request.GET.get('filterdocumentdate')
            choice_document_status = request.GET.get('choicedocumentstatus')
            choice_check_status = request.GET.get('choicecheckstatus')
            choice_business_type = request.GET.get('choicebusinesstype')
            region_filter = AccessControls.get_filters_for_user(user)
            range_date= 15
            if choice_shop:
                try: 
                    if choice_shop.isdigit():
                        filters['shop_id__shop_id'] = choice_shop
                    else:
                        choice_shop = str(choice_shop).strip()
                        filters['shop_id__shop_name__iexact'] = choice_shop
                except ValueError:
                    choice_shop = str(choice_shop).strip()
                    filters['shop_id__shop_name__icontains'] = choice_shop
                if choice_user_duyet:
                    filters['lastest_checked_by__username__icontains'] = choice_user_duyet
                if choice_check_date:
                    date_range = choice_check_date.split(' to ')
                    if len(date_range) == 2:
                        # Trường hợp có cả ngày bắt đầu và kết thúc
                        check_date_start, check_date_end = date_range
                        check_date_start = datetime.strptime(check_date_start, "%Y-%m-%d").date()
                        check_date_end =  datetime.strptime(check_date_end, "%Y-%m-%d").date()
                        if (check_date_end - check_date_start).days > range_date:
                            messages.info(request, f'Chỉ cho phép xuất dữ liệu Ngày duyệt {range_date} ngày liên tục.')
                            check_date_end_short7 = check_date_start + timedelta(days=range_date)
                            filters['lastest_checked_date__date__range'] = [check_date_start, check_date_end_short7]
                        else:
                            filters['lastest_checked_date__date__range'] = [check_date_start, check_date_end]
                    elif len(date_range) == 1:
                        # Trường hợp chỉ có một ngày, xem xét nó là ngày bắt đầu và sử dụng cho cả hai ngày bắt đầu và kết thúc
                        check_date = datetime.strptime(date_range[0], "%Y-%m-%d").date()
                        filters['lastest_checked_date__date__range'] = [check_date, check_date]
                if choice_document_date:
                    date_parts = choice_document_date.split(' to ')
                    if len(date_parts) == 2:
                        document_date_start, document_date_end = date_parts
                        document_date_start =datetime.strptime(document_date_start, "%Y-%m-%d").date()
                        document_date_end = datetime.strptime(document_date_end, "%Y-%m-%d").date()
                        if (document_date_end - document_date_start).days > range_date:
                            messages.info(request, f'Chỉ cho phép xuất dữ liệu Ngày chứng từ {range_date} ngày liên tục.')
                            document_date_end_short7 = document_date_start + timedelta(days=range_date)
                            filters['documents_created_date__range'] = [document_date_start, document_date_end_short7]
                        else:
                            filters['documents_created_date__range'] = [document_date_start, document_date_end]
                    elif len(date_parts) == 1:
                        # Trường hợp chỉ có một ngày, xem xét nó là ngày bắt đầu và sử dụng cho cả hai ngày bắt đầu và kết thúc
                        create_date = datetime.strptime(date_parts[0], "%Y-%m-%d").date()
                        filters['documents_created_date__range'] = [create_date, create_date]
                if choice_document_status:
                    filters['document_status_id'] = choice_document_status   
                if choice_check_status:
                    filters['status_id'] = choice_check_status          
                if choice_business_type:
                    filters['business_type_id'] = choice_business_type
            if choice_loan_code:
                filters['loan_id__loan_code__icontains'] = choice_loan_code
            if choice_contract_code:
                filters['contract_id__contract_code__icontains'] = choice_contract_code
            if len(filters)==0:
                # Nếu không có bộ lọc nào được thiết lập thì lấy tất cả dữ liệu documents_detail
                documents_detail = DocumentsDetail.objects.none()
            #Lấy dữ liệu documents_detail dựa trên các bộ lọc đã thiết lập
            else:
                filters['business_type_id__allow_checking']=True
                # Lọc dữ liệu dựa trên role của user là checker thì chỉ lấy dữ liệu của region của user
                region_shop=AccessControls.filter_shop_region_based_on_role(user)
                filters.update(region_shop)
                documents_detail = DocumentsDetail.objects.filter(**filters).select_related('checkingadditional').order_by('documents_created_date', 'loan_id','document_type_id', 'contract_id').select_related('package_id')
            paginator = Paginator(documents_detail, 50)  # Show 50 documents per page
            page_number = request.GET.get('page')
            documents_detail = paginator.get_page(page_number)
            change_requests = ChangeRequest.objects.filter(document__in=documents_detail, status='pending')
            change_requests_map = {req.document_id: req for req in change_requests}   
        #Handle POST từ form duyệt chứng từ 
        if request.method == 'POST':
            if 'formcheck' :
                # Submit mới 
                documents_id_submit = request.POST.get('documents_id_submit')
                checking_status_submit = request.POST.get('checking_status_submit')
                lasted_checked_date_submit  = timezone.now()
                note_submit = request.POST.get('checking_note_submit')
                package_code_submit = request.POST.get('package_code_submit')
                # Submit cũ 
                checking_status_previous = request.POST.get('checking_status_previous')
                package_id_previous = request.POST.get('package_id_previous')
                # Save to database
                documents_detail_instance = DocumentsDetail.objects.filter(documents_id = documents_id_submit)     
                documents_detail_instance_log = DocumentsDetail.objects.get(documents_id = documents_id_submit)     
                # Kiểm tra status_id cũ có khác status_id mới không? Nếu khác thì lưu lại ở Documents_transaction_checking_change_log
                is_checkingstatus_changed = False
                message_success_content = ''
                if checking_status_submit:
                    if checking_status_submit != checking_status_previous:
                        is_checkingstatus_changed = True
                        # # Use the update() method to update all matching rows in the queryset
                        documents_detail_instance.update(
                                                    status_id = checking_status_submit, 
                                                    lastest_checked_date= lasted_checked_date_submit, 
                                                    lastest_checked_by = user)
                        # Log the change
                        if is_checkingstatus_changed:
                            checking_status_instance_log = CheckingTransactionStatus.objects.get(status_id=checking_status_submit) 
                            # documents_detail_instance.update(lastest_checked_date= lasted_checked_date_submit, lastest_checked_by = user) 
                            DocumentsTransactionChecking.objects.create(
                                        documents_id = documents_detail_instance_log,
                                        trans_created_date = lasted_checked_date_submit,
                                        trans_created_by=user,
                                        checking_status_id = checking_status_instance_log,
                                    )
                            message_success_content += f"Thay đổi trạng thái thành công cho chứng từ {documents_detail_instance_log.documents_code}\n" 
                            # Nếu trạng thái chứng từ thay đổi và trạng thái kiểm chứng từ cũ là hẹn bổ sung thì đánh dấu is_valid trong AdditionalChecking là False
                            if not checking_status_instance_log.is_request_additional:
                                CheckingAdditional.objects.filter(additional=documents_detail_instance_log).update(is_valid=False) 
                            # Nếu trạng thái chứng từ đổi thành hẹn bổ sung thì đánh dấu is_valid trong AdditionalChecking là True
                            if checking_status_instance_log.is_request_additional:
                                CheckingAdditional.objects.filter(additional=documents_detail_instance_log).update(is_valid=True)
                            # Chuyển trạng thái nếu chưa có trạng thái hoặc trạng thái là đã nhận thành đã duyệt  
                            if documents_detail_instance_log.document_status_id == None: 
                                documents_detail_instance.update(document_status_id = DocumentStatus.objects.get(documents_status_code='102'))
                            if documents_detail_instance_log.document_status_id == DocumentStatus.objects.get(documents_status_code='101'): 
                                documents_detail_instance.update(document_status_id =  DocumentStatus.objects.get(documents_status_code='102'))
                                # Cập nhật ghi chú 
                if note_submit:
                    document_detail_instance_get_note = documents_detail_instance_log.note
                    if note_submit != document_detail_instance_get_note :
                        documents_detail_instance.update(note = note_submit)
                        message_success_content += f"Thêm ghi chú thành công cho chứng từ {documents_detail_instance_log.documents_code}\n"               
                if package_code_submit:
                    try: 
                        if Package.objects.filter(package_code = package_code_submit).exists():
                            package_id = Package.objects.get(package_code = package_code_submit)
                            documents_detail_instance.update(package_id = package_id)
                            message_success_content += f"Gán thùng thành công cho chứng từ {documents_detail_instance_log.documents_code}\n" 
                            # Lưu lại log gán thùng chứng từ 
                            PackageDocumentHistory.objects.create(
                                document_id = documents_detail_instance_log,
                                package_id = package_id,
                                trans_created_date = timezone.now(),
                                trans_created_by = user
                            )
                        else:
                            noti_error = f"Thùng {package_code_submit} không tồn tại. Vui lòng chọn một mã thùng đã tồn tại"  
                            messages.add_message(request, messages.ERROR, noti_error)
                            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
                    except IntegrityError:
                        noti_error = f"Thùng {package_code_submit} không tồn tại. Vui lòng chọn một mã thùng đã tồn tại"  
                        messages.add_message(request, messages.ERROR, noti_error)
                        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
                if message_success_content !='':
                    messages.add_message(request, messages.SUCCESS, message_success_content)
                # Tạo dictionary chứa thông tin lọc từ dữ liệu POST
                filter_params = {
                    'choice_shop': request.POST.get('filter_choice_shop'),
                    'choice_loan_code': request.POST.get('filter_choice_loan_code'),
                    'choice_user_duyet': request.POST.get('filter_choice_user_duyet'),
                    'filtercheckdate': request.POST.get('filter_filtercheckdate'),
                    'filterdocumentdate': request.POST.get('filter_filterdocumentdate'),
                    'choicedocumentstatus': request.POST.get('filter_choicedocumentstatus'),
                    'choicecheckstatus': request.POST.get('filter_choicecheckstatus'),
                    'choicebusinesstype': request.POST.get('filter_choicebusinesstype'),
                    'page': request.POST.get('filter_page'),
                }
                # Chuyển về trang hiển thị dữ liệu với các thông số lọc đã thiết lập
                redirect_url = f"{reverse(redirect_name)}?{urlencode(filter_params)}"
                return HttpResponseRedirect(redirect_url)  
        # Build the query string without 'page' parameter
        query_string = '&'.join(f"{key}={value}" for key, value in request.GET.items() if key != 'page')
        user_by_role = AccessControls.get_users_based_on_role(user)
        drop_list_checking_status = CheckingTransactionStatus.objects.all() 
        drop_list_shops = Shop.objects.filter(**region_filter)
        drop_list_users = user_by_role
        drop_list_document_status = DocumentStatus.objects.all()
        drop_list_business_type = BusinessType.objects.all()
        drop_list_borrowing_status = BorrowingStatus.objects.all()
        drop_list_shops_borrow = Shop.objects.filter( for_borrow_only=True)
        regions = Region.objects.all()
        context = {
            # 'is_admin': is_admin,
            # 'is_shop_user': is_shop_user,
            # 'is_checker': is_checker,
            # 'is_risk': is_risk,
            # 'is_supervisor': is_supervisor,
            **user_context,
            'user': user,
            'documents_detail': documents_detail,
            'drop_list_checking_status': drop_list_checking_status,
            'drop_list_shops':drop_list_shops,
            'drop_list_users': drop_list_users, 
            'drop_list_document_status': drop_list_document_status,
            'drop_list_business_type': drop_list_business_type,
            'query_string': query_string,
            'regions':regions, 
            'change_requests_map':change_requests_map,
            'drop_list_borrowing_status': drop_list_borrowing_status,
            'drop_list_shops_borrow':drop_list_shops_borrow
        }
        context['query_string'] = query_string
        return render(request, template_name, context)

@login_required
def checking_transaction_view_v2(request):
    user = request.user
    user_context = get_user_context(user)
    documents_detail = DocumentsDetail.objects.none()
    if not user_context['is_admin'] and not user_context['is_checker']:
        return redirect('home')

    change_requests_map = {}
    if request.method == 'GET':
        filters = {}
        choice_shop = request.GET.get('choice_shop')
        choice_loan_code = request.GET.get('choice_loan_code')
        choice_contract_code = request.GET.get('choice_contract_code')
        choice_user_duyet = request.GET.get('choice_user_duyet')
        choice_check_date = request.GET.get('filtercheckdate')
        choice_document_date = request.GET.get('filterdocumentdate')
        choice_document_status = request.GET.get('choicedocumentstatus')
        choice_check_status = request.GET.get('choicecheckstatus')
        choice_business_type = request.GET.get('choicebusinesstype')
        sort_raw = request.GET.get('sort', '').strip()
        region_filter = AccessControls.get_filters_for_user(user)
        range_date = 15
        if choice_shop:
            try:
                if choice_shop.isdigit():
                    filters['shop_id__shop_id'] = choice_shop
                else:
                    choice_shop = str(choice_shop).strip()
                    filters['shop_id__shop_name__iexact'] = choice_shop
            except ValueError:
                choice_shop = str(choice_shop).strip()
                filters['shop_id__shop_name__icontains'] = choice_shop
            if choice_user_duyet:
                filters['lastest_checked_by__username__icontains'] = choice_user_duyet
            if choice_check_date:
                date_range = choice_check_date.split(' to ')
                if len(date_range) == 2:
                    check_date_start, check_date_end = date_range
                    check_date_start = datetime.strptime(check_date_start, "%Y-%m-%d").date()
                    check_date_end = datetime.strptime(check_date_end, "%Y-%m-%d").date()
                    if (check_date_end - check_date_start).days > range_date:
                        messages.info(request, f'Chỉ cho phép xuất dữ liệu Ngày duyệt {range_date} ngày liên tục.')
                        check_date_end_short7 = check_date_start + timedelta(days=range_date)
                        filters['lastest_checked_date__date__range'] = [check_date_start, check_date_end_short7]
                    else:
                        filters['lastest_checked_date__date__range'] = [check_date_start, check_date_end]
                elif len(date_range) == 1:
                    check_date = datetime.strptime(date_range[0], "%Y-%m-%d").date()
                    filters['lastest_checked_date__date__range'] = [check_date, check_date]
            if choice_document_date:
                date_parts = choice_document_date.split(' to ')
                if len(date_parts) == 2:
                    document_date_start, document_date_end = date_parts
                    document_date_start = datetime.strptime(document_date_start, "%Y-%m-%d").date()
                    document_date_end = datetime.strptime(document_date_end, "%Y-%m-%d").date()
                    if (document_date_end - document_date_start).days > range_date:
                        messages.info(request, f'Chỉ cho phép xuất dữ liệu Ngày chứng từ {range_date} ngày liên tục.')
                        document_date_end_short7 = document_date_start + timedelta(days=range_date)
                        filters['documents_created_date__range'] = [document_date_start, document_date_end_short7]
                    else:
                        filters['documents_created_date__range'] = [document_date_start, document_date_end]
                elif len(date_parts) == 1:
                    create_date = datetime.strptime(date_parts[0], "%Y-%m-%d").date()
                    filters['documents_created_date__range'] = [create_date, create_date]
            if choice_document_status:
                filters['document_status_id'] = choice_document_status
            if choice_check_status:
                filters['status_id'] = choice_check_status
            if choice_business_type:
                filters['business_type_id'] = choice_business_type
        if choice_loan_code:
            filters['loan_id__loan_code__icontains'] = choice_loan_code
        if choice_contract_code:
            filters['contract_id__contract_code__icontains'] = choice_contract_code
        if len(filters) == 0:
            documents_detail = DocumentsDetail.objects.none()
        else:
            filters['business_type_id__allow_checking'] = True
            region_shop = AccessControls.filter_shop_region_based_on_role(user)
            filters.update(region_shop)
            documents_detail = DocumentsDetail.objects.filter(**filters).select_related(
                'checkingadditional',
                'package_id',
                'package_id__partnerpackage',
                'package_id__partnerpackage__status_id',
                'shop_id',
                'loan_id',
                'loan_id__employee_id',
                'contract_id',
                'contract_id__employee_id',
                'folder_id',
                'folder_id__folder_type_id',
                'folder_id__folder_status_id',
                'document_type_id',
                'business_type_id',
                'document_status_id',
                'status_id',
                'lastest_checked_by',
            )
            default_doc_status = DocumentStatus.objects.filter(is_selectable=True).order_by('status_id').first()
            if default_doc_status:
                DocumentsDetail.objects.filter(
                    **filters,
                    document_status_id__isnull=True,
                    folder_id__folder_status_id__is_received=True,
                ).update(document_status_id=default_doc_status)
            if sort_raw:
                sort_map = {
                    'shop': 'shop_id__shop_name',
                    '-shop': '-shop_id__shop_name',
                    'document_date': 'documents_created_date',
                    '-document_date': '-documents_created_date',
                    'document_type': 'document_type_id__document_type_name',
                    '-document_type': '-document_type_id__document_type_name',
                    'business_type': 'business_type_id__business_type_name',
                    '-business_type': '-business_type_id__business_type_name',
                    'document_status': 'document_status_id__documents_status_name',
                    '-document_status': '-document_status_id__documents_status_name',
                    'checking_status': 'status_id__checking_status_name',
                    '-checking_status': '-status_id__checking_status_name',
                    'checking_date': 'lastest_checked_date',
                    '-checking_date': '-lastest_checked_date',
                    'checking_user': 'lastest_checked_by__username',
                    '-checking_user': '-lastest_checked_by__username',
                    'package_code': 'package_id__package_code',
                    '-package_code': '-package_id__package_code',
                }
                sort_parts = [p for p in sort_raw.split(',') if p]
                resolved_sorts = [sort_map.get(p) for p in sort_parts if sort_map.get(p)]
                if resolved_sorts:
                    documents_detail = documents_detail.order_by(*resolved_sorts)
                else:
                    documents_detail = documents_detail.order_by('documents_created_date', 'loan_id', 'contract_id', 'document_type_id')
            else:
                documents_detail = documents_detail.order_by('documents_created_date', 'loan_id', 'contract_id', 'document_type_id')

        paginator = Paginator(documents_detail, 50)
        page_number = request.GET.get('page')
        documents_detail = paginator.get_page(page_number)
        change_requests = ChangeRequest.objects.filter(document__in=documents_detail, status='pending')
        change_requests_map = {req.document_id: req for req in change_requests}

    if request.method == 'POST':
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
        if 'formcheck':
            documents_id_submit = request.POST.get('documents_id_submit')
            checking_status_submit = request.POST.get('checking_status_submit')
            lasted_checked_date_submit = timezone.now()
            note_submit = request.POST.get('checking_note_submit')
            package_code_submit = request.POST.get('package_code_submit')
            checking_status_previous = request.POST.get('checking_status_previous')
            documents_detail_instance = DocumentsDetail.objects.filter(documents_id=documents_id_submit)
            documents_detail_instance_log = DocumentsDetail.objects.get(documents_id=documents_id_submit)
            is_checkingstatus_changed = False
            message_success_content = ''
            folder_received = bool(documents_detail_instance_log.folder_id and documents_detail_instance_log.folder_id.folder_status_id and documents_detail_instance_log.folder_id.folder_status_id.is_received)
            has_package = bool(documents_detail_instance_log.package_id and documents_detail_instance_log.package_id.package_code)
            if checking_status_submit:
                if not folder_received or not has_package:
                    error_msg = 'Chỉ duyệt chứng từ đã nhận và có mã thùng.'
                    if is_ajax:
                        return JsonResponse({'success': False, 'error': error_msg}, status=400)
                    messages.add_message(request, messages.ERROR, error_msg)
                    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
                checked_status = DocumentStatus.objects.filter(is_checked=True).order_by('status_id').first()
                if not checked_status:
                    error_msg = 'Chưa cấu hình trạng thái chứng từ đã duyệt.'
                    if is_ajax:
                        return JsonResponse({'success': False, 'error': error_msg}, status=400)
                    messages.add_message(request, messages.ERROR, error_msg)
                    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
                checking_status_instance_log = CheckingTransactionStatus.objects.get(status_id=checking_status_submit)
                if checking_status_submit != checking_status_previous:
                    is_checkingstatus_changed = True
                    documents_detail_instance.update(
                        status_id=checking_status_submit,
                        lastest_checked_date=lasted_checked_date_submit,
                        lastest_checked_by=user)
                    if is_checkingstatus_changed:
                        DocumentsTransactionChecking.objects.create(
                            documents_id=documents_detail_instance_log,
                            trans_created_date=lasted_checked_date_submit,
                            trans_created_by=user,
                            checking_status_id=checking_status_instance_log,
                        )
                        message_success_content += f"Thay đổi trạng thái thành công cho chứng từ {documents_detail_instance_log.documents_code}\n"
                        if documents_detail_instance_log.document_status_id is None or (
                            documents_detail_instance_log.document_status_id and documents_detail_instance_log.document_status_id.is_selectable
                        ):
                            documents_detail_instance.update(document_status_id=checked_status)
                if not checking_status_instance_log.is_request_additional:
                    CheckingAdditional.objects.filter(additional=documents_detail_instance_log).update(is_valid=False)
                if checking_status_instance_log.is_request_additional:
                    additional_date = request.POST.get('additional_date')
                    additional_note = request.POST.get('additional_note')
                    if not additional_date:
                        if is_ajax:
                            return JsonResponse({'success': False, 'error': 'Vui lòng chọn ngày hẹn bổ sung.'}, status=400)
                        messages.add_message(request, messages.ERROR, 'Vui lòng chọn ngày hẹn bổ sung.')
                        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
                    additional_obj, created = CheckingAdditional.objects.get_or_create(
                        additional=documents_detail_instance_log,
                        defaults={
                            'is_valid': True,
                            'additional_note': additional_note if additional_note else None,
                            'date_addition': additional_date,
                            'additional_created_by': user,
                        },
                    )
                    if not created:
                        CheckingAdditional.objects.filter(additional=documents_detail_instance_log).update(
                            is_valid=True,
                            additional_note=additional_note if additional_note else None,
                            date_addition=additional_date,
                            additional_updated_date=timezone.now(),
                        )
            if note_submit:
                document_detail_instance_get_note = documents_detail_instance_log.note
                if note_submit != document_detail_instance_get_note:
                    documents_detail_instance.update(note=note_submit)
                    message_success_content += f"Thêm ghi chú thành công cho chứng từ {documents_detail_instance_log.documents_code}\n"
            if package_code_submit:
                is_selectable = bool(documents_detail_instance_log.document_status_id and documents_detail_instance_log.document_status_id.is_selectable)
                is_checked = bool(documents_detail_instance_log.document_status_id and documents_detail_instance_log.document_status_id.is_checked)
                if (not is_selectable and not is_checked) or not folder_received:
                    error_msg = 'Chỉ đổi thùng khi chứng từ đã nhận và trạng thái cho phép.'
                    if is_ajax:
                        return JsonResponse({'success': False, 'error': error_msg}, status=400)
                    messages.add_message(request, messages.ERROR, error_msg)
                    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
                try:
                    if Package.objects.filter(package_code=package_code_submit).exists():
                        package_id = Package.objects.get(package_code=package_code_submit)
                        documents_detail_instance.update(package_id=package_id)
                        message_success_content += f"Gán thùng thành công cho chứng từ {documents_detail_instance_log.documents_code}\n"
                        PackageDocumentHistory.objects.create(
                            document_id=documents_detail_instance_log,
                            package_id=package_id,
                            trans_created_date=timezone.now(),
                            trans_created_by=user
                        )
                    else:
                        noti_error = f"Thùng {package_code_submit} không tồn tại. Vui lòng chọn một mã thùng đã tồn tại"
                        if is_ajax:
                            return JsonResponse({'success': False, 'error': noti_error}, status=400)
                        messages.add_message(request, messages.ERROR, noti_error)
                        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
                except IntegrityError:
                    noti_error = f"Thùng {package_code_submit} không tồn tại. Vui lòng chọn một mã thùng đã tồn tại"
                    if is_ajax:
                        return JsonResponse({'success': False, 'error': noti_error}, status=400)
                    messages.add_message(request, messages.ERROR, noti_error)
                    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            if message_success_content != '':
                messages.add_message(request, messages.SUCCESS, message_success_content)
            if is_ajax:
                documents_detail_instance_log = DocumentsDetail.objects.select_related(
                    'status_id', 'lastest_checked_by', 'document_status_id'
                ).get(documents_id=documents_id_submit)
                checking_user_full = ''
                if documents_detail_instance_log.lastest_checked_by:
                    checking_user_full = f"{documents_detail_instance_log.lastest_checked_by.last_name} {documents_detail_instance_log.lastest_checked_by.first_name}".strip()
                return JsonResponse({
                    'success': True,
                    'checking_status_id': documents_detail_instance_log.status_id.status_id if documents_detail_instance_log.status_id else '',
                    'checking_status_name': documents_detail_instance_log.status_id.checking_status_name if documents_detail_instance_log.status_id else '',
                    'checking_date': documents_detail_instance_log.lastest_checked_date.strftime('%Y-%m-%d %H:%M') if documents_detail_instance_log.lastest_checked_date else '',
                    'checking_user': documents_detail_instance_log.lastest_checked_by.username if documents_detail_instance_log.lastest_checked_by else '',
                    'checking_user_full': checking_user_full,
                    'document_status_name': documents_detail_instance_log.document_status_id.documents_status_name if documents_detail_instance_log.document_status_id else '',
                    'document_status_color': documents_detail_instance_log.document_status_id.badge_color if documents_detail_instance_log.document_status_id else '',
                    'document_status_is_selectable': documents_detail_instance_log.document_status_id.is_selectable if documents_detail_instance_log.document_status_id else False,
                    'document_status_is_checked': documents_detail_instance_log.document_status_id.is_checked if documents_detail_instance_log.document_status_id else False,
                })
            filter_params = {
                'choice_shop': request.POST.get('filter_choice_shop'),
                'choice_loan_code': request.POST.get('filter_choice_loan_code'),
                'choice_user_duyet': request.POST.get('filter_choice_user_duyet'),
                'filtercheckdate': request.POST.get('filter_filtercheckdate'),
                'filterdocumentdate': request.POST.get('filter_filterdocumentdate'),
                'choicedocumentstatus': request.POST.get('filter_choicedocumentstatus'),
                'choicecheckstatus': request.POST.get('filter_choicecheckstatus'),
                'choicebusinesstype': request.POST.get('filter_choicebusinesstype'),
                'page': request.POST.get('filter_page'),
                'sort': request.POST.get('filter_sort'),
            }
            redirect_url = f"{reverse('checking_transaction_v2')}?{urlencode(filter_params)}"
            return HttpResponseRedirect(redirect_url)

    current = documents_detail.number if documents_detail else 1
    total_pages = documents_detail.paginator.num_pages if documents_detail else 1
    start_range = max(current - 2, 1)
    end_range = min(current + 2, total_pages)
    page_range_custom = list(range(1, min(2, total_pages) + 1))
    page_range_custom += list(range(start_range, end_range + 1))
    page_range_custom += list(range(max(total_pages - 1, 1), total_pages + 1))
    page_range_custom = sorted(set([p for p in page_range_custom if 1 <= p <= total_pages]))

    def base_field(part):
        return part.lstrip('-')

    sort_fields = ['shop', 'document_date', 'document_type', 'business_type', 'document_status', 'checking_status', 'checking_date', 'checking_user', 'package_code']
    sort_toggle = {}
    current_sort_parts = [p for p in request.GET.get('sort', '').split(',') if p]
    for f in sort_fields:
        current_dir = None
        for p in current_sort_parts:
            if base_field(p) == f:
                current_dir = p.startswith('-')
                break
        if current_dir is None:
            toggled = f
        elif current_dir is False:
            toggled = f'-{f}'
        else:
            toggled = f
        remaining = [p for p in current_sort_parts if base_field(p) != f]
        new_parts = [toggled] + remaining
        sort_toggle[f] = ','.join(new_parts)

    qs_no_page = request.GET.copy()
    qs_no_page.pop('page', None)
    qs_no_page.pop('sort', None)
    base_qs = qs_no_page.urlencode()

    query_string = '&'.join(f"{key}={value}" for key, value in request.GET.items() if key != 'page')
    user_by_role = AccessControls.get_users_based_on_role(user)
    drop_list_checking_status = CheckingTransactionStatus.objects.all()
    drop_list_shops = Shop.objects.filter(**region_filter)
    drop_list_users = user_by_role
    drop_list_document_status = DocumentStatus.objects.all()
    drop_list_business_type = BusinessType.objects.all()
    drop_list_borrowing_status = BorrowingStatus.objects.all()
    drop_list_shops_borrow = Shop.objects.filter(for_borrow_only=True)
    regions = Region.objects.all()
    context = {
        **user_context,
        'user': user,
        'documents_detail': documents_detail,
        'drop_list_checking_status': drop_list_checking_status,
        'drop_list_shops': drop_list_shops,
        'drop_list_users': drop_list_users,
        'drop_list_document_status': drop_list_document_status,
        'drop_list_business_type': drop_list_business_type,
        'query_string': query_string,
        'regions': regions,
        'change_requests_map': change_requests_map,
        'drop_list_borrowing_status': drop_list_borrowing_status,
        'drop_list_shops_borrow': drop_list_shops_borrow,
        'page_range_custom': page_range_custom,
        'base_qs': base_qs,
        'sort_param': request.GET.get('sort', ''),
        'sort_toggle': sort_toggle,
    }
    return render(request, "app_documents/app_checkingtransaction_v2.html", context)

# Lịch sử duyệt chứng từ
@login_required
def fetch_history(request, document_id):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        history = DocumentsTransactionChecking.objects.filter(documents_id=document_id).values(
            'trans_created_date', 
            'trans_created_by__username', 
            'checking_status_id__checking_status_name'
            ).order_by('-trans_created_date')
        package_history = PackageDocumentHistory.objects.filter(document_id=document_id).values(
            'trans_created_date',
            'trans_created_by__username',
            'trans_created_by__first_name',
            'trans_created_by__last_name',
            'package_id__package_code'
            ).order_by('-trans_created_date')
        return JsonResponse({
            'checking_history': list(history),
            'package_history': list(package_history),
        })
    else:
        return JsonResponse({'error': 'Invalid request'}, status=400)
    
# Chứng từ hẹn bổ sung 
@login_required
def checking_additional_view(request, document_id):
    document = get_object_or_404(DocumentsDetail, pk=document_id)
    if request.method == 'POST':
        additional_note = request.POST.get('additional_note')
        date_addition = request.POST.get('date_addition')
        previous_check_status = request.POST.get('previous_check_status')
        additional_create_date = timezone.now()
        if additional_note or date_addition:
            try:
                # Try to create a new CheckingAdditional instance
                CheckingAdditional.objects.create(
                    additional=document,
                    additional_note=additional_note, 
                    date_addition=date_addition,
                    additional_created_date=additional_create_date, 
                    additional_created_by=request.user,
                    is_valid=True
                )
                messages.success(request, f'Hẹn bổ sung thành công cho chứng từ mã {document.documents_code}')  
                # Nếu user đã CheckingAdditional thành công thì chuyển trạng thái của checkingdocuments status_id thành trạng thái hẹn bổ sung
                additional_status = CheckingTransactionStatus.objects.filter(is_request_additional=True).order_by('status_id').first()
                if not additional_status:
                    messages.error(request, 'Chưa cấu hình trạng thái hẹn bổ sung.')
                    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
                already_documents_status_102 = DocumentStatus.objects.get(documents_status_code = '102') # Instance của trạng thái chứng từ đã duyệt
                DocumentsDetail.objects.filter(documents_id = document_id).update(
                                                                                status_id = additional_status.status_id ,
                                                                                document_status_id = already_documents_status_102.status_id,
                                                                                lastest_checked_date = timezone.now(),
                                                                                lastest_checked_by = request.user)
                # Nếu trạng thái hiện tại của chứng từ khác hẹn bổ sung thì có nghĩa là đang thay đổi trạng thái, từ đó log thay đổi.
                if previous_check_status != str(additional_status.status_id):
                    DocumentsTransactionChecking.objects.create(
                                        documents_id = document,
                                        trans_created_date = additional_create_date,
                                        trans_created_by=request.user,
                                        checking_status_id = additional_status,
                                        )
            except IntegrityError:
                # Handle the case where a CheckingAdditional instance already exists for this document
                existing_additional = CheckingAdditional.objects.get(additional=document)
                existing_additional.additional_note = additional_note
                existing_additional.date_addition = date_addition
                existing_additional.is_valid = True
                existing_additional.save()
                messages.info(request, 'Cập nhật dữ liệu hẹn chứng từ thành công')
                # Nếu user đã CheckingAdditional thành công thì chuyển trạng thái của checkingdocuments status_id thành trạng thái hẹn bổ sung
                additional_status = CheckingTransactionStatus.objects.filter(is_request_additional=True).order_by('status_id').first()
                if additional_status:
                    DocumentsDetail.objects.filter(documents_id = document_id).update(status_id = additional_status)
            # Redirect về trang trước đó
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))   # Redirect to the desired URL after handling the form submission
    return redirect('checking_transaction')  # Redirect if it's not a POST request or if something goes wrong

# Duyệt nhiều chứng từ
@login_required
def bulk_checking_document_view(request):
    try:
        data = json.loads(request.body)
        selected_items = data.get('selectedItems', [])
        selected_documents = [item.removeprefix('checkingitem') for item in selected_items]
        checking_note_submit = data.get('checking_note_submit')
        documents_status_choice = data.get('documents_status_choice')
        additional_bulk_date_choice = data.get('additional_bulk_date_choice')
        additional_bulk_note_choice = data.get('additional_bulk_note_choice')
        checking_time = timezone.now()
        user = request.user
        if not selected_items or not documents_status_choice:
            return JsonResponse({'success': False, 'error': 'Invalid data'})
        documents_status_choice_instance = CheckingTransactionStatus.objects.get(status_id=documents_status_choice)
        if documents_status_choice_instance.is_request_additional and not additional_bulk_date_choice:
            return JsonResponse({'success': False, 'error': 'Vui lòng chọn ngày hẹn bổ sung.'}, status=400)
        selected_qs = DocumentsDetail.objects.filter(documents_id__in=selected_documents).select_related(
            'loan_id',
            'contract_id',
            'folder_id',
            'folder_id__folder_status_id',
            'package_id',
        )
        checked_status = DocumentStatus.objects.filter(is_checked=True).order_by('status_id').first()
        if not checked_status:
            return JsonResponse({'success': False, 'error': 'Chưa cấu hình trạng thái chứng từ đã duyệt.'}, status=400)
        if selected_qs.count() != len(selected_documents):
            return JsonResponse({'success': False, 'error': 'Không tìm thấy đủ chứng từ đã chọn.'})
        group_keys = set()
        for doc in selected_qs:
            if not doc.package_id or not doc.package_id.package_code:
                return JsonResponse({'success': False, 'error': 'Chỉ duyệt chứng từ có mã thùng.'}, status=400)
        for doc in selected_qs:
            if getattr(doc, 'loan_id', None) and getattr(doc.loan_id, 'loan_code', None):
                group_keys.add(f"loan:{doc.loan_id.loan_code}")
            elif getattr(doc, 'contract_id', None) and getattr(doc.contract_id, 'contract_code', None):
                group_keys.add(f"contract:{doc.contract_id.contract_code}")
            else:
                group_keys.add(f"unknown:{doc.documents_id}")
        if len(group_keys) > 1:
            return JsonResponse({'success': False, 'error': 'Chỉ được duyệt nhiều chứng từ cùng HĐCC hoặc GNN.'}, status=400)
        try:
            with transaction.atomic():
                updated_rows = []
                for document_id in selected_documents:
                    documents_detail_instance = DocumentsDetail.objects.filter(documents_id=document_id)
                    documents_detail_instance_log = DocumentsDetail.objects.get(documents_id=document_id)
                    documents_detail_instance.update(
                        status_id = documents_status_choice_instance, 
                        document_status_id = checked_status,
                        lastest_checked_date= checking_time, 
                        note=checking_note_submit if checking_note_submit else None,
                        lastest_checked_by = user
                    )
                    DocumentsTransactionChecking.objects.create(
                        documents_id = documents_detail_instance_log,
                        trans_created_date = checking_time,
                        trans_created_by=user,
                        checking_status_id = documents_status_choice_instance,
                        )
                    #Tạo bổ sung cho chứng từ nếu trạng thái là hẹn bổ sung
                    if documents_status_choice_instance.is_request_additional:
                        CheckingAdditional.objects.create(
                            additional = documents_detail_instance_log, 
                            is_valid=True,
                            additional_note = additional_bulk_note_choice if additional_bulk_note_choice else None,
                            date_addition = additional_bulk_date_choice if additional_bulk_date_choice else None,
                            additional_created_date = checking_time,
                            additional_created_by = user
                            )
                    updated_doc = DocumentsDetail.objects.select_related(
                        'status_id', 'lastest_checked_by', 'document_status_id'
                    ).get(documents_id=document_id)
                    checking_user_full = ''
                    if updated_doc.lastest_checked_by:
                        checking_user_full = f"{updated_doc.lastest_checked_by.last_name} {updated_doc.lastest_checked_by.first_name}".strip()
                    updated_rows.append({
                        'documents_id': updated_doc.documents_id,
                        'checking_status_id': updated_doc.status_id.status_id if updated_doc.status_id else '',
                        'checking_status_name': updated_doc.status_id.checking_status_name if updated_doc.status_id else '',
                        'checking_date': updated_doc.lastest_checked_date.strftime('%Y-%m-%d %H:%M') if updated_doc.lastest_checked_date else '',
                        'checking_user': updated_doc.lastest_checked_by.username if updated_doc.lastest_checked_by else '',
                        'checking_user_full': checking_user_full,
                        'document_status_name': updated_doc.document_status_id.documents_status_name if updated_doc.document_status_id else '',
                        'document_status_color': updated_doc.document_status_id.badge_color if updated_doc.document_status_id else '',
                        'document_status_is_selectable': updated_doc.document_status_id.is_selectable if updated_doc.document_status_id else False,
                        'document_status_is_checked': updated_doc.document_status_id.is_checked if updated_doc.document_status_id else False,
                    })
                messages.success(request, f'Duyệt {len(selected_items)} quyển chứng từ thành công') 
                return JsonResponse({'success': True, 'updated': updated_rows})
        except Exception as e:
            messages.error(request, 'Có lỗi xảy ra, vui lòng thử lại sau')
            return JsonResponse({'success': False, 'error': 'Có lỗi xảy ra'} )
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
        
# ADDITIONAL CHECKING TRANSACTION MANGAMENT
# Export to excel của checking management view
def export_to_excel(queryset):
    wb = Workbook()
    ws = wb.active
    ws.title = "Checking Additional"

    columns = [
        "STT", "Phòng giao dịch", "Ngày chứng từ", "Thông tin", "Loại chứng từ",
        "Loại quyển", "Ngày đến hạn bổ sung", "Người tạo bổ sung", "Trạng thái duyệt", "Thông tin duyệt", "Note bổ sung"
    ]
    ws.append(columns)
    header_fill = PatternFill(start_color='00833E', end_color='00833E', fill_type='solid')
    header_font = Font(bold=True, color="FFFFFF")

    for cell in ws[1]:  # ws[1] tương đương với hàng đầu tiên
        cell.fill = header_fill
        cell.font = header_font
    for index, additional in enumerate(queryset, start=1):
        row = [
            index,
            additional.additional.shop_id.shop_name,
            additional.additional.documents_created_date.strftime('%Y-%m-%d'),
            f"Mã HĐ: {additional.additional.loan_id.loan_code}\nTên KH: {additional.additional.loan_id.customer_name}",
            additional.additional.document_type_id.document_type_name,
            additional.additional.folder_id.folder_type_id.folder_type_name,
            additional.date_addition.strftime('%Y-%m-%d'),
            str(additional.additional_created_by),  # Chuyển đối tượng User thành chuỗi
            additional.additional.status_id.checking_status_name if additional.additional.status_id else "Chưa duyệt",
            f"{additional.additional.lastest_checked_date.strftime('%Y-%m-%d %H:%M') if additional.additional.lastest_checked_date else ''}\n{str(additional.additional.lastest_checked_by) if additional.additional.lastest_checked_by else ''}",
            additional.additional_note
        ]
        ws.append(row)
        # Thiết lập màu nền và font cho header

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=additional_checking.xlsx'
    wb.save(response)
    return response

# Additional checking management view
@login_required
def additional_management_view(request):
    user = request.user
    user_context = get_user_context(user)
    # is_admin = user.is_superuser
    # is_checker = user.groups.filter(name='checker').exists()
    region_filter = AccessControls.get_filters_for_user(user)
    # if not is_admin and not is_checker:
    if not user_context['is_admin'] and not user_context['is_checker']:
        messages.error(request, "Unauthorized access.")
        return redirect('home')
        # Only show valid additional checking records and order by date of addition and prefetch related additional and has date_addition in current month
    now = timezone.now()
    current_month = now.month
    current_year = now.year
    checking_additional = CheckingAdditional.objects.filter( is_valid=True,
                                                            date_addition__year=current_year,
                                                            date_addition__month=current_month
                                                           ).order_by('date_addition').prefetch_related('additional')
    # Filter Part
    if request.method == 'GET':
        filters = {}
        choice_shop = request.GET.get('choice_shop') 
        choice_folder_type = request.GET.get('choice_folder_type')
        filterdocumentdate = request.GET.get('filterdocumentdate')
        filteradditionaldate = request.GET.get('filteradditionaldate') 
        filtermonthdocumentdate = request.GET.get('filtermonthdocumentdate')
        if choice_shop:
            try:
                if choice_shop.isdigit():
                    filters['additional__shop_id__shop_id'] = choice_shop
                else:
                    choice_shop = str(choice_shop).strip()
                    filters['additional__shop_id__shop_name__iexact'] = choice_shop
            except ValueError:
                choice_shop = str(choice_shop).strip()
                filters['additional__shop_id__shop_name__icontains'] = choice_shop
        if choice_folder_type:
            filters['additional__folder_id__folder_type_id'] = choice_folder_type
        if filtermonthdocumentdate: 
            month_parts = filtermonthdocumentdate.split('.')
            if len(month_parts) == 2:
                doc_month, doc_year = month_parts
                filters['additional__documents_created_date__month'] = doc_month
                filters['additional__documents_created_date__year'] = doc_year
        if filterdocumentdate:
            date_parts = filterdocumentdate.split(' to ')
            if len(date_parts) == 2:
                document_date_start, document_date_end = date_parts
                filters['additional__documents_created_date__range'] = [datetime.strptime(document_date_start, "%Y-%m-%d").date(), 
                                                                        datetime.strptime(document_date_end, "%Y-%m-%d").date()]
            elif len(date_parts) == 1:
                create_date = datetime.strptime(date_parts[0], "%Y-%m-%d").date()
                filters['additional__documents_created_date__range'] = [create_date, create_date] 
        if filteradditionaldate:
            date_parts = filteradditionaldate.split(' to ')
            if len(date_parts) == 2:
                additional_date_start, additional_date_end = date_parts
                filters['date_addition__range'] = [datetime.strptime(additional_date_start, "%Y-%m-%d").date(), 
                                                    datetime.strptime(additional_date_end, "%Y-%m-%d").date()]
            elif len(date_parts) == 1:
                additional_date = datetime.strptime(date_parts[0], "%Y-%m-%d").date()
                filters['date_addition__range'] = [additional_date, additional_date]
       
        if len(filters)==0:
            checking_additional = checking_additional
        else:
            checking_additional = CheckingAdditional.objects.filter(**filters,is_valid=True).order_by('date_addition').prefetch_related('additional')
    # Check if export is requested
    if request.GET.get('export') == '1':
        return export_to_excel(checking_additional)
    paginator = Paginator(checking_additional, 50)  # Show 50 documents per page
    page_number = request.GET.get('page')
    checking_additional = paginator.get_page(page_number) 
    drop_list_folder_type = FolderType.objects.all()
    drop_list_shops = Shop.objects.filter(**region_filter)
    regions = Region.objects.all()
    context = {
        # 'is_admin': is_admin,
        # 'is_checker': is_checker,
        **user_context,
        'user': user,
        'now': now,
        'checking_additional': checking_additional,
        'drop_list_folder_type': drop_list_folder_type,
        'drop_list_shops': drop_list_shops,
        'regions' : regions
    }
    return render(request, 'app_documents/app_additional_management.html', context)

#-------------------FOLDER TRANSACTION -------------------
# Folder transaction view
@login_required
def receive_folder_view(request, template_name="app_documents/app_receivingtransaction.html", redirect_name="receiving_transaction"): 
    user = request.user 
    user_context = get_user_context(user)
    folder_detail = Folder.objects.none()  # Khởi tạo folder_detail là None 
    if not user_context['is_admin'] and not user_context['is_checker']:
        messages.error(request, "Unauthorized access.")
        return redirect('home')
    else:
        region_filter = AccessControls.get_filters_for_user(user)
        if request.method == 'GET':
            filters = {}
            choice_shop = request.GET.get('choice_shop')
            choice_user_nhan = request.GET.get('choice_user_nhan')
            choice_folder_type = request.GET.get('choice_folder_type')
            choice_folder_status = request.GET.get('choice_folder_status')
            choice_folder_date = request.GET.get('filter_folder_date')
            choice_folder_code = request.GET.get('choice_folder_code')
            choice_receive_date = request.GET.get('filter_receive_date')
            # choice_package_code = request.GET.get('package_code_submit') 
            filter_package = request.GET.get('filter_package')
            range_date = 15
            #Handle GET requests từ form nhận hồ sơ
            if choice_shop:
                try: 
                    if choice_shop.isdigit():
                        filters['shop_id__shop_id'] = choice_shop  
                    else:
                        choice_shop = str(choice_shop).strip()
                        filters['shop_id__shop_name__iexact'] = choice_shop
                        # filters shop theo region 
                except ValueError: 
                    # Tim kiếm gần giống: 
                    choice_shop = str(choice_shop).strip()
                    filters['shop_id__shop_name__icontains'] = choice_shop 
                if choice_user_nhan:
                    filters['lastest_received_by__username__icontains'] = choice_user_nhan
                if choice_folder_type:
                    filters['folder_type_id'] = choice_folder_type
                if choice_receive_date:
                    date_range = choice_receive_date.split(' to ')
                    if len(date_range) == 2:
                        # Trường hợp có cả ngày bắt đầu và kết thúc
                        receive_date_start, receive_date_end = date_range
                        receive_date_start = datetime.strptime(receive_date_start, "%Y-%m-%d").date()
                        receive_date_end = datetime.strptime(receive_date_end, "%Y-%m-%d").date()
                        if (receive_date_end - receive_date_start).days > range_date:
                            messages.info(request, f'Chỉ cho phép xuất dữ liệu Ngày nhận {range_date} ngày liên tục.')
                            receive_date_end_short7 = receive_date_start + timedelta(days=range_date)
                            filters['lastest_received_date__date__range'] = [receive_date_start, receive_date_end_short7]
                        else:
                            # Chỉ cho phép xuất dữ liệu 7 ngày liên tục, nếu lớn hơn thì cảnh báo info và xuất dữ liệu 7 ngày kể từ start
                            filters['lastest_received_date__date__range'] = [receive_date_start, receive_date_end]
                    elif len(date_range) == 1:
                        # Trường hợp chỉ có một ngày, xem xét nó là ngày bắt đầu và sử dụng cho cả hai ngày bắt đầu và kết thúc
                        receive_date = datetime.strptime(date_range[0], "%Y-%m-%d").date()
                        filters['lastest_received_date__date__range'] = [receive_date, receive_date]
                if choice_folder_date:
                    date_parts = choice_folder_date.split(' to ')
                    if len(date_parts) == 2:
                        # Trường hợp có cả ngày bắt đầu và kết thúc 
                        folder_date_start, folder_date_end = date_parts
                        folder_date_start = datetime.strptime(folder_date_start, "%Y-%m-%d").date() 
                        folder_date_end = datetime.strptime(folder_date_end, "%Y-%m-%d").date() 
                        if(folder_date_end - folder_date_start).days > 15:
                            messages.info(request, f'Chỉ cho phép xuất dữ liệu Ngày chứng từ {range_date} ngày liên tục.')
                            folder_date_end_short7 = folder_date_start + timedelta(days=7)
                            filters['folder_created_date__range'] = [folder_date_start, folder_date_end_short7]
                        else:
                            filters['folder_created_date__range'] = [folder_date_start, folder_date_end]
                    elif len(date_parts) == 1:
                        # Trường hợp chỉ có một ngày, xem xét nó là ngày bắt đầu và sử dụng cho cả hai ngày bắt đầu và kết thúc
                        create_date = datetime.strptime(date_parts[0], "%Y-%m-%d").date()
                        filters['folder_created_date__range'] = [create_date, create_date]         
                if choice_folder_status:
                    filters['folder_status_id'] = choice_folder_status         
            if choice_folder_code:
                filters['folder_code__icontains'] = choice_folder_code
            if filter_package:
                # Relate with 2 columns 
                if filter_package.startswith('CIMB') or filter_package.startswith('VH'):
                    filters['package_id__package_code'] = filter_package
                else:
                    filters['package_id__partnerpackage__partner_package_code'] = filter_package 
            if len(filters) == 0:
                # Nếu không có bộ lọc nào được thiết lập thì lấy tất cả dữ liệu documents_detail
                folder_detail = Folder.objects.none()
            #Lấy dữ liệu documents_detail dựa trên các bộ lọc đã thiết lập
            else:
                region_shop = AccessControls.filter_shop_region_based_on_role(user)
                filters.update(region_shop)
                folder_detail = Folder.objects.filter(**filters).prefetch_related('package_id').order_by('folder_created_date')
            # Sau khi có folder_detail dựa trên bộ lọc
            paginator = Paginator(folder_detail, 50)
            page_number = request.GET.get('page')
            folder_detail = paginator.get_page(page_number)
            # Lấy ChangeRequest liên quan đến từng folder (có status là 'pending')
            change_requests = ChangeRequest.objects.filter(folder__in=folder_detail, status='pending')
            change_requests_map = {req.folder_id: req for req in change_requests}     
        #Handle POST từ form nhận hồ sơ
        if request.method == 'POST':
            if 'formreceive' :
                # Submit mới 
                folder_id_submit = request.POST.get('folder_id_submit')
                folder_status_submit = request.POST.get('folder_status_submit')
                lasted_received_date_submit  = request.POST.get('filter_True_Lastest_Receive_Date')
                if lasted_received_date_submit == '':
                    lasted_received_date_submit = timezone.now()
                else:
                    # Nếu cần xử lý chuỗi thành datetime, hãy thực hiện tại đây
                    lasted_received_date_submit = parse_datetime(lasted_received_date_submit)
                note_submit = request.POST.get('folder_note_submit')
                choice_package_code = request.POST.get('package_code_submit')
                # Submit cũ 
                folder_status_previous = request.POST.get('folder_status_previous')
                folder_detail_instance = Folder.objects.filter(folder_id = folder_id_submit) 
                folder_detail_instance_log = Folder.objects.get(folder_id = folder_id_submit) 
                is_folderstatus_changed = False 
                messages_success_content = ''
                # Kiểm tra folder_status_id cũ có khác folder_status_id mới không? Nếu khác thì lưu lại ở Folders_transaction_receiving_change_log
                if folder_status_submit:
                    # Nếu trạng thái quyển submit khác với trạng thái quyển hiện tại thì cập nhật trạng thái mới.
                    if folder_status_submit != folder_status_previous:
                        if Package.objects.filter(package_code = choice_package_code).exists():
                            is_folderstatus_changed = True
                            folder_detail_instance.update(  folder_status_id = folder_status_submit, 
                                                            lastest_received_date= lasted_received_date_submit, 
                                                            lastest_received_by = user)
                            result_check = check_on_time(folder_detail_instance_log, lasted_received_date_submit)
                            messages.add_message(request, messages.INFO, result_check.get("message", "")) 
                            # Nếu trạng thái được thay đổi thì lưu lại log trong bảng FolderTransactionReceiving
                            if is_folderstatus_changed:
                                # Lấy ins của trạng thái quyển mới
                                folder_status_instance_log = FolderStatus.objects.get(folder_status_id=folder_status_submit) 
                                # Tạo log thay đổi trạng thái quyển
                                FoldersTransactionReceiving.objects.create(
                                    folder_id = folder_detail_instance_log, 
                                    trans_updated_date=lasted_received_date_submit,
                                    trans_created_by=user,
                                    folder_status_id = folder_status_instance_log
                                )
                                # Bắn message thành công
                                messages_success_content += f"Thay đổi trạng thái thành công cho quyển {folder_detail_instance_log.folder_code}\n" 
                # Nếu nhận được ghi chú thì kiểm tra ghi chú cũ có khác với ghi chú mới không? Nếu khác thì cập nhật ghi chú mới.                     
                if note_submit:
                    # Lấy ra ghi chú của quyển hiện tại
                    folder_detail_instance_get_note = Folder.objects.get(folder_id = folder_id_submit) 
                    if note_submit != folder_detail_instance_get_note.note : 
                        folder_detail_instance.update(note = note_submit)
                        # Bắn tin nhắn ghi chú thành công
                        messages_success_content += f"Thêm ghi chú thành công cho quyển {folder_detail_instance_get_note.folder_code}\n" 
                # Nếu nhận được mã thùng mới, kiểm tra xem mã thùng đã có trong hệ thống chưa? Nếu có trong hệ thống thì cho nhập, nếu không thì báo lỗi chưa có thùng
                if choice_package_code:
                    try: 
                        if Package.objects.filter(package_code = choice_package_code).exists():
                            create_package_time = timezone.now()
                            package_id = Package.objects.get(package_code = choice_package_code)
                            folder_detail_instance.update(package_id = package_id)
                            messages_success_content += f"Gán thùng thành công cho quyển {folder_detail_instance_log.folder_code}" 
                            PackageFolderHistory.objects.create(
                                folder_id = folder_detail_instance_log,
                                package_id = package_id,
                                trans_created_date = create_package_time,
                                trans_created_by = user
                            )
                            # Kiểm tra package_id tại documents_detail đã tồn tại folder_id chưa? Nếu chưa thì thêm vào package_id của folder tại package_id của documents_detail
                            if DocumentsDetail.objects.filter(folder_id = folder_id_submit).exists():
                                document_details = DocumentsDetail.objects.select_for_update().filter(folder_id = folder_id_submit)
                                with transaction.atomic():
                                    for document in document_details:
                                        document.package_id = package_id
                                        document.save()                    
                                        PackageDocumentHistory.objects.create(
                                            document_id = document,
                                            package_id = package_id,
                                            trans_created_date=create_package_time,
                                            trans_created_by=user )
                        # Nếu thùng không tồn tại thì thông báo lỗi
                        else:
                            noti_error = f"Thùng {choice_package_code} không tồn tại"  
                            messages.add_message(request, messages.ERROR, noti_error)
                            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
                    except IntegrityError: 
                        #Nếu thùng không tồn tại thì thông báo lỗi 
                        noti_error = f"Thùng {choice_package_code} không tồn tại" 
                        messages.add_message(request, messages.ERROR, noti_error) 
                        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
                if messages_success_content !='':
                    messages.add_message(request, messages.SUCCESS, messages_success_content) 
                # Tạo dictionary chứa thông tin lọc từ dữ liệu POST
                filter_params = {
                    'choice_shop': request.POST.get('filter_choice_shop'),
                    'choice_folder_code': request.POST.get('filter_choice_folder_code'),
                    'choice_user_nhan': request.POST.get('filter_choice_user_nhan'),
                    'filter_receive_date': request.POST.get('filter_choice_receive_date'),
                    'filter_folder_date': request.POST.get('filter_choice_folder_date'),
                    'choice_folder_type': request.POST.get('filter_choice_folder_type'),
                    'choice_folder_status': request.POST.get('filter_choice_folder_status'),
                    'page': request.POST.get('filter_page'),
                }
                # Chuyển về trang hiển thị dữ liệu với các thông số lọc đã thiết lập
                redirect_url = f"{reverse(redirect_name)}?{urlencode(filter_params)}"
                return HttpResponseRedirect(redirect_url)  
        user_by_role = AccessControls.get_users_based_on_role(user)
        query_string = '&'.join(f"{key}={value}" for key, value in request.GET.items() if key != 'page')
        drop_list_shops = Shop.objects.filter(**region_filter)
        drop_list_users = user_by_role
        drop_list_folder_type = FolderType.objects.all()
        drop_list_folder_status = FolderStatus.objects.all()
        drop_list_folder_status_received = FolderStatus.objects.filter(is_received=True)
        regions = Region.objects.all()
        context = {
            **user_context,
            'user': user,
            'folder_detail': folder_detail,
            'drop_list_shops': drop_list_shops,
            'drop_list_users': drop_list_users,
            'drop_list_folder_type': drop_list_folder_type,
            'drop_list_folder_status': drop_list_folder_status,
            'drop_list_folder_status_received': drop_list_folder_status_received,
            'regions': regions,
            'change_request':change_requests_map,
        }
        context['query_string'] = query_string
        return render(request, template_name, context)


def receive_folder_view_v2(request):
    """
    Trang nhận chứng từ ver2 (UI mới, layout giống package-list).
    """
    user = request.user
    user_context = get_user_context(user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        messages.error(request, "Unauthorized access.")
        return redirect('home')

    filters = {}
    choice_shop = request.GET.get('choice_shop', '').strip()
    choice_folder_code = request.GET.get('choice_folder_code', '').strip()
    choice_folder_status = request.GET.get('choice_folder_status', '').strip()
    choice_folder_type = request.GET.get('choice_folder_type', '').strip()
    choice_lastest_receiver = request.GET.get('choice_lastest_receiver', '').strip()
    choice_package_code = request.GET.get('filter_package', '').strip()
    choice_receive_date = request.GET.get('filter_receive_date', '').strip()
    choice_folder_date = request.GET.get('filter_folder_date', '').strip()
    sort_raw = request.GET.get('sort', '-folder_created_date').strip()

    range_date = 30  # giới hạn 30 ngày

    region_shop_filter = AccessControls.filter_shop_region_based_on_role(user)
    drop_list_shops = Shop.objects.filter(is_shop_active=True, for_borrow_only=False, **region_shop_filter).order_by('shop_name')
    drop_list_folder_status = FolderStatus.objects.filter(is_valid=True).order_by('folder_status_name')
    drop_list_folder_status_received = FolderStatus.objects.filter(is_received=True, is_valid=True).order_by('folder_status_name')
    drop_list_folder_type = FolderType.objects.filter(is_valid=True).order_by('folder_type_name')
    drop_list_users = User.objects.filter(is_active=True).order_by('username')
    package_types = FolderType.objects.filter(is_valid=True).order_by('package_type', 'folder_type_name')
    partners_active = Partner.objects.filter(is_active=True).order_by('partner_name')
    partners_options_json = json.dumps(
        list(partners_active.values('partner_id', 'partner_name', 'partner_code', 'require_partner_selection', 'require_partner_code')),
        cls=DjangoJSONEncoder,
        ensure_ascii=False,
    )
    region_options_json = json.dumps(
        list(Region.objects.values('region_code', 'region_name')),
        cls=DjangoJSONEncoder,
        ensure_ascii=False,
    )

    if choice_shop:
        if choice_shop.isdigit():
            filters['shop_id__shop_id'] = choice_shop
        else:
            filters['shop_id__shop_name__icontains'] = choice_shop
    if choice_folder_code:
        filters['folder_code__icontains'] = choice_folder_code
    if choice_folder_status:
        filters['folder_status_id'] = choice_folder_status
    if choice_folder_type:
        filters['folder_type_id'] = choice_folder_type
    if choice_lastest_receiver:
        filters['lastest_received_by__username__icontains'] = choice_lastest_receiver
    if choice_package_code:
        filters['package_id__package_code__icontains'] = choice_package_code

    def _apply_date_range(input_str, field_lookup):
        if not input_str:
            return
        date_parts = input_str.split(' to ')
        if len(date_parts) == 2:
            start = datetime.strptime(date_parts[0], "%Y-%m-%d").date()
            end = datetime.strptime(date_parts[1], "%Y-%m-%d").date()
            if (end - start).days > range_date:
                messages.info(request, f"Chỉ cho phép tìm trong tối đa {range_date} ngày.")
                end = start + timedelta(days=range_date)
            filters[field_lookup] = [start, end]
        elif len(date_parts) == 1 and date_parts[0]:
            single = datetime.strptime(date_parts[0], "%Y-%m-%d").date()
            filters[field_lookup] = [single, single]

    _apply_date_range(choice_receive_date, 'lastest_received_date__date__range')
    _apply_date_range(choice_folder_date, 'folder_created_date__range')

    if len(filters) == 0:
        folder_detail_qs = Folder.objects.none()
    else:
        filters.update(region_shop_filter)

        sort_map = {
            'folder_code': 'folder_code',
            '-folder_code': '-folder_code',
            'shop': 'shop_id__shop_name',
            '-shop': '-shop_id__shop_name',
            'folder_type': 'folder_type_id__folder_type_name',
            '-folder_type': '-folder_type_id__folder_type_name',
            'folder_created_date': 'folder_created_date',
            '-folder_created_date': '-folder_created_date',
            'lastest_received_date': 'lastest_received_date',
            '-lastest_received_date': '-lastest_received_date',
            'folder_status': 'folder_status_id__folder_status_name',
            '-folder_status': '-folder_status_id__folder_status_name',
            'is_original': 'is_original',
            '-is_original': '-is_original',
        }
        sort_fields_map = {
            'folder_code': 'folder_code',
            '-folder_code': '-folder_code',
            'shop': 'shop_id__shop_name',
            '-shop': '-shop_id__shop_name',
            'folder_type': 'folder_type_id__folder_type_name',
            '-folder_type': '-folder_type_id__folder_type_name',
            'folder_created_date': 'folder_created_date',
            '-folder_created_date': '-folder_created_date',
            'lastest_received_date': 'lastest_received_date',
            '-lastest_received_date': '-lastest_received_date',
            'folder_status': 'folder_status_id__folder_status_name',
            '-folder_status': '-folder_status_id__folder_status_name',
            'is_original': 'is_original',
            '-is_original': '-is_original',
        }

        sort_parts = [p for p in sort_raw.split(',') if p]
        resolved_sorts = [sort_fields_map.get(p) for p in sort_parts if sort_fields_map.get(p)]
        if not resolved_sorts:
            resolved_sorts = ['-folder_created_date']

        folder_detail_qs = Folder.objects.filter(**filters).select_related(
            'shop_id', 'folder_type_id', 'folder_status_id', 'lastest_received_by', 'package_id'
        ).order_by(*resolved_sorts)

    paginator = Paginator(folder_detail_qs, 25)
    page_number = request.GET.get('page')
    folder_detail = paginator.get_page(page_number)

    current = folder_detail.number if folder_detail else 1
    total_pages = paginator.num_pages if paginator else 1
    start_range = max(current - 2, 1)
    end_range = min(current + 2, total_pages)
    page_range_custom = list(range(1, min(2, total_pages) + 1))
    page_range_custom += list(range(start_range, end_range + 1))
    page_range_custom += list(range(max(total_pages - 1, 1), total_pages + 1))
    page_range_custom = sorted(set([p for p in page_range_custom if 1 <= p <= total_pages]))

    # sort toggle map for template
    def base_field(part):
        return part.lstrip('-')

    sort_fields = ['folder_code', 'shop', 'folder_type', 'folder_created_date', 'lastest_received_date', 'folder_status', 'is_original']
    sort_toggle = {}
    current_sort_parts = [p for p in sort_raw.split(',') if p]
    for f in sort_fields:
        current_dir = None
        for p in current_sort_parts:
            if base_field(p) == f:
                current_dir = p.startswith('-')
                break
        if current_dir is None:
            toggled = f
        elif current_dir is False:
            toggled = f'-{f}'
        else:
            toggled = f
        remaining = [p for p in current_sort_parts if base_field(p) != f]
        new_parts = [toggled] + remaining
        sort_toggle[f] = ','.join(new_parts)

    qs_no_page = request.GET.copy()
    qs_no_page.pop('page', None)
    qs_no_page.pop('sort', None)
    base_qs = qs_no_page.urlencode()

    context = {
        **user_context,
        'user': user,
        'folder_detail': folder_detail,
        'drop_list_shops': drop_list_shops,
        'drop_list_folder_status': drop_list_folder_status,
        'drop_list_folder_status_received': drop_list_folder_status_received,
        'drop_list_folder_type': drop_list_folder_type,
        'drop_list_users': drop_list_users,
        'paginator': paginator,
        'page_range_custom': page_range_custom,
        'sort_param': sort_raw,
        'sort_toggle': sort_toggle,
        'base_qs': base_qs,
        'package_types': package_types,
        'partners_active': partners_active,
        'partners_options_json': partners_options_json,
        'region_options_json': region_options_json,
        'filters': {
            'choice_shop': choice_shop,
            'choice_folder_code': choice_folder_code,
            'choice_folder_status': choice_folder_status,
            'choice_folder_type': choice_folder_type,
            'choice_lastest_receiver': choice_lastest_receiver,
            'filter_receive_date': choice_receive_date,
            'filter_folder_date': choice_folder_date,
            'filter_package': choice_package_code,
        }
    }
    return render(request, "app_documents/app_document_receiving_v2.html", context)


@login_required
def api_receive_folder_update_v2(request):
    user_context = get_user_context(request.user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        return JsonResponse({'error': 'Unauthorized access.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        payload = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        payload = {}

    folder_id = payload.get('folder_id')
    folder_status_id = payload.get('folder_status_id')
    package_code = (payload.get('package_code') or "").strip()
    received_date_raw = (payload.get('received_date') or "").strip()
    redirect_url = payload.get('redirect_url') or request.META.get('HTTP_REFERER') or reverse('receiving_transaction_v2')

    if not folder_id or not folder_status_id:
        return JsonResponse({'error': 'Thiếu thông tin quyển hoặc trạng thái.'}, status=400)
    if not package_code:
        return JsonResponse({'error': 'Vui lòng nhập mã thùng nhận.'}, status=400)

    received_dt = None
    if received_date_raw:
        received_dt = parse_datetime(received_date_raw)
        if received_dt is None:
            for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    received_dt = datetime.strptime(received_date_raw, fmt)
                    break
                except ValueError:
                    continue
    if received_dt is None:
        received_dt = timezone.now()
    if timezone.is_naive(received_dt):
        received_dt = timezone.make_aware(received_dt, timezone.get_current_timezone())

    try:
        with transaction.atomic():
            folder = Folder.objects.select_for_update().get(folder_id=folder_id)
            package = Package.objects.select_related('package_type').get(package_code=package_code)
            folder_status = FolderStatus.objects.get(folder_status_id=folder_status_id)

            folder_pkg_type = (folder.folder_type_id.package_type if folder.folder_type_id else None)
            package_pkg_type = (package.package_type.package_type if package.package_type else None)
            if not folder_pkg_type or not package_pkg_type:
                return JsonResponse({'error': 'Thiếu thông tin loại thùng/loại quyển.'}, status=400)
            if str(folder_pkg_type).strip().upper() != str(package_pkg_type).strip().upper():
                return JsonResponse({'error': 'Mã thùng không khớp loại quyển.'}, status=400)

            status_changed = folder.folder_status_id_id != folder_status.folder_status_id

            folder.folder_status_id = folder_status
            folder.lastest_received_date = received_dt
            folder.lastest_received_by = request.user
            folder.package_id = package
            folder.save(update_fields=[
                'folder_status_id',
                'lastest_received_date',
                'lastest_received_by',
                'package_id',
            ])

            check_result = check_on_time(folder, received_dt)

            if status_changed:
                FoldersTransactionReceiving.objects.create(
                    folder_id=folder,
                    trans_updated_date=received_dt,
                    trans_created_by=request.user,
                    folder_status_id=folder_status,
                )

            receive_time = timezone.now()
            PackageFolderHistory.objects.create(
                folder_id=folder,
                package_id=package,
                trans_created_date=receive_time,
                trans_created_by=request.user,
            )

            document_details = DocumentsDetail.objects.select_for_update().filter(folder_id=folder.folder_id)
            for document in document_details:
                if document.package_id_id != package.package_id:
                    document.package_id = package
                    document.save(update_fields=['package_id'])
                PackageDocumentHistory.objects.create(
                    document_id=document,
                    package_id=package,
                    trans_created_date=receive_time,
                    trans_created_by=request.user,
                )

    except Folder.DoesNotExist:
        return JsonResponse({'error': 'Không tìm thấy quyển chứng từ.'}, status=404)
    except Package.DoesNotExist:
        return JsonResponse({'error': 'Mã thùng không tồn tại.'}, status=404)
    except FolderStatus.DoesNotExist:
        return JsonResponse({'error': 'Trạng thái không tồn tại.'}, status=404)
    except Exception as exc:
        return JsonResponse({'error': f'Lỗi xử lý: {exc}'}, status=500)

    message = f"Nhận quyển {folder.folder_code} thành công."
    return JsonResponse({
        'success': True,
        'message': message,
        'status_name': folder_status.folder_status_name,
        'received_date': received_dt.strftime('%Y-%m-%d %H:%M'),
        'user': request.user.username,
        'is_on_time': folder.is_on_time,
        'is_late': folder.is_late,
        'check_message': check_result.get('message', ''),
        'redirect_url': redirect_url,
    })


@login_required
def api_folder_note_v2(request, folder_id):
    user_context = get_user_context(request.user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        return JsonResponse({'error': 'Unauthorized access.'}, status=403)
    if request.method != "POST":
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    folder = get_object_or_404(Folder, pk=folder_id)
    try:
        payload = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        payload = {}
    note_val = payload.get("note")
    note_clean = note_val.strip() if isinstance(note_val, str) else ""
    folder.note = note_clean or None
    folder.save(update_fields=["note"])
    return JsonResponse({"success": True, "note": folder.note or ""})

@login_required
@require_http_methods(["POST"])
def api_document_note_v2(request, document_id):
    user_context = get_user_context(request.user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        return JsonResponse({'error': 'Unauthorized access.'}, status=403)
    try:
        payload = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        payload = {}
    note_val = payload.get("note")
    note_clean = note_val.strip() if isinstance(note_val, str) else ""
    document = get_object_or_404(DocumentsDetail, documents_id=document_id)
    document.note = note_clean or None
    document.save(update_fields=["note"])
    return JsonResponse({"success": True, "note": document.note or ""})

# Lịch sử nhận quyển chứng từ
@login_required
def fetch_history_receiving(request, folder_id):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        history = FoldersTransactionReceiving.objects.filter(folder_id=folder_id).values(
            'trans_created_date',
            'trans_created_by__username',
            'folder_status_id__folder_status_name'
        )
        return JsonResponse(list(history), safe=False)


@login_required
def fetch_history_receiving_v2(request, folder_id):
    user_context = get_user_context(request.user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        return JsonResponse({'error': 'Unauthorized access.'}, status=403)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        folder_history = FoldersTransactionReceiving.objects.filter(folder_id=folder_id).values(
            'trans_created_date',
            'trans_created_by__username',
            'folder_status_id__folder_status_name'
        )
        package_history = PackageFolderHistory.objects.filter(folder_id=folder_id).values(
            'trans_created_date',
            'trans_created_by__username',
            'package_id__package_code'
        )
        return JsonResponse({
            'folder_history': list(folder_history),
            'package_history': list(package_history),
        })
    return JsonResponse({'error': 'Bad request'}, status=400)

# Nhận nhiều quyển 1 lần Bulk Receive
@login_required
def bulk_receive_folder_view(request):
    try:
        data = json.loads(request.body)
        # From JS
        selected_items = data.get('selectedItems', [])
        selected_folder = [item.removeprefix('checkingitem') for item in selected_items]
        package_choice = data.get('package_choice')
        folder_status_choice = data.get('folder_status_choice')
        folder_note_choice = data.get('folder_note_choice')
        lasted_received_date_submit  = data.get('trueLastestReceiveDate')
        if lasted_received_date_submit == '':
            lasted_received_date_submit = timezone.now()
        else:
            lasted_received_date_submit = parse_datetime(lasted_received_date_submit)
        receive_time = timezone.now()
        user = request.user 
        try: 
            if not selected_folder:
                return JsonResponse({'success': False, 'error': 'Vui lòng chọn ít nhất một quyển.'})
            if not package_choice:
                return JsonResponse({'success': False, 'error': 'Vui lòng nhập mã thùng.'})
            if not folder_status_choice:
                return JsonResponse({'success': False, 'error': 'Vui lòng chọn trạng thái nhận.'})

            package_id_instance = Package.objects.select_related('package_type').get(package_code=package_choice)
            folder_status_instance = FolderStatus.objects.get(folder_status_id=folder_status_choice)
            package_type_code = (package_id_instance.package_type.package_type if package_id_instance.package_type else None)
            if not package_type_code:
                return JsonResponse({'success': False, 'error': 'Không xác định được loại thùng của mã thùng.'})

            folders = Folder.objects.select_related('folder_type_id').filter(folder_id__in=selected_folder)
            if folders.count() != len(selected_folder):
                return JsonResponse({'success': False, 'error': 'Có quyển không tồn tại, vui lòng tải lại.'})

            mismatched = []
            for folder in folders:
                folder_pkg_type = folder.folder_type_id.package_type if folder.folder_type_id else None
                if not folder_pkg_type or str(folder_pkg_type).strip().upper() != str(package_type_code).strip().upper():
                    mismatched.append(folder.folder_code)

            if mismatched:
                preview = ', '.join(mismatched[:5])
                suffix = '...' if len(mismatched) > 5 else ''
                return JsonResponse({'success': False, 'error': f'Mã thùng không khớp loại quyển: {preview}{suffix}'})

            with transaction.atomic():
                for folder in folders:
                    # Cập nhật trạng thái quyển chứng từ
                    folder.folder_status_id = folder_status_instance
                    folder.package_id = package_id_instance
                    folder.lastest_received_date = lasted_received_date_submit
                    folder.lastest_received_by = user
                    folder.note = folder_note_choice
                    folder.save()
                    # Gọi hàm `check_on_time` để kiểm tra và cập nhật trạng thái đúng/trễ hạn
                    check_on_time(folder,lasted_received_date_submit)
                    # Tạo log nhận quyển chứng từ
                    FoldersTransactionReceiving.objects.create(
                        folder_id=folder,
                        trans_updated_date=lasted_received_date_submit,
                        trans_created_by=user,
                        folder_status_id=folder.folder_status_id
                    )
                    # Tạo log gán thùng cho quyển chứng từ 
                    PackageFolderHistory.objects.create(
                        folder_id=folder,
                        package_id=folder.package_id,
                        trans_created_date=receive_time,
                        trans_created_by=user)
                    document_details = DocumentsDetail.objects.select_for_update().filter(folder_id = folder.folder_id)
                    for document in document_details:
                        document.package_id = package_id_instance
                        document.save() 
                        # Sau khi gán thùng cho chứng từ thì tạo log gán thùng cho chứng từ
                        PackageDocumentHistory.objects.create(
                            document_id = document,
                            package_id = package_id_instance,
                            trans_created_date=receive_time,
                            trans_created_by=user )      
                messages.success(request, f'Nhận {len(selected_folder)} quyển chứng từ thành công')         
        except Package.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Mã thùng không tồn tại.'})
        except FolderStatus.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Trạng thái nhận không tồn tại.'})
        except IntegrityError:
            messages.error(request, 'sys001-Có lỗi xảy ra khi xử lý dữ liệu. Vui lòng thử lại sau!')
            return JsonResponse({'success': False, 'error': 'sys001-Có lỗi xảy ra khi xử lý dữ liệu. Vui lòng thử lại sau!'})           
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

# Tạo quyển bổ sung 
@login_required
def receiving_additional_view(request, folder_id): 
    folder = get_object_or_404(Folder, pk=folder_id)
    user = request.user
    if request.method == 'POST': 
        if 'form-additional-folder' :
            choice_additional_folder_note = request.POST.get('additional_folder_note_submit') #Ghi chú bổ sung 
            choice_additional_folder_status = request.POST.get('additional_folder_status_submit') # Trạng thái quyển bổ sung 
            choice_additional_package_code = request.POST.get('additional_package_code_submit') # Thùng bổ sung
            folder_code_additional = request.POST.get('filter_choice_folder_code') #Folder.objects.get(folder_id = folder_id).folder_code 
            lasted_received_date_submit  = request.POST.get('filter_True_Lastest_Receive_Date')
            if lasted_received_date_submit == '':
                lasted_received_date_submit = timezone.now()
            else:
                # Nếu cần xử lý chuỗi thành datetime, hãy thực hiện tại đây
                lasted_received_date_submit = parse_datetime(lasted_received_date_submit)
            # Hàm tạo quyển bổ sung bằng cách đếm xem có bao nhiêu quyển bổ sung đã được tạo ra từ quyển gốc
            count_folder_additional = Folder.objects.filter(folder_code__contains = folder_code_additional).count()
            # Tạo kí tự quyển bổ sung. 
            folder_code_additional = folder_code_additional + f'-{count_folder_additional}'
            # Tạo dictionary chứa thông tin lọc từ dữ liệu POST
            filter_params = {
                'choice_shop': request.POST.get('filter_choice_shop', ''),
            }
            redirect_name = request.POST.get('redirect_name', 'receiving_transaction')
            if not choice_additional_package_code or not choice_additional_folder_status:
                messages.error(request, 'Vui lòng chọn thùng và trạng thái cho quyển bổ sung.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            
            # Nếu thùng không tồn tại thì thông báo lỗi 
            if not Package.objects.filter(package_code=choice_additional_package_code).exists() :
                messages.error(request, 'Thùng không tồn tại. Vui lòng tạo 1 thùng mới.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
                
            if not FolderStatus.objects.filter(folder_status_id=choice_additional_folder_status).exists():
                messages.error(request, 'Trạng thái không tồn tại. Vui lòng chọn trạng thái khác.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))   

            try : 
                created_date = timezone.now()   
                folder_status_id_found = FolderStatus.objects.get(folder_status_id=choice_additional_folder_status)
                package_id_found = Package.objects.get(package_code=choice_additional_package_code)        
                # Try to create a new CheckingAdditional instance
                folder_aditional_instance = Folder.objects.create(
                    folder_code=folder_code_additional,
                    shop_id=folder.shop_id,
                    folder_type_id=folder.folder_type_id,
                    folder_status_id=folder_status_id_found,
                    manager_id=folder.manager_id,
                    folder_created_date=folder.folder_created_date,
                    note = choice_additional_folder_note if choice_additional_folder_note else None,
                    package_id=package_id_found,
                    lastest_received_date = lasted_received_date_submit,
                    lastest_received_by = user,
                    is_original=False,
                    is_issue=folder.is_issue,
                )
                message_of_success_additional = f'Tạo quyển bổ sung thành công. Quyển bổ sung có mã quyển: {folder_code_additional}' 
                
                FoldersTransactionReceiving.objects.create(
                    folder_id = folder_aditional_instance , 
                    trans_updated_date = lasted_received_date_submit, 
                    trans_created_by = user,
                    folder_status_id = folder_status_id_found
                )
                PackageFolderHistory.objects.create(
                    folder_id = folder_aditional_instance,
                    package_id = package_id_found,
                    trans_created_date = created_date,
                    trans_created_by = user)
                
                messages.success(request, message_of_success_additional)  
                redirect_url = f"{reverse(redirect_name)}?{urlencode(filter_params)}"
                return HttpResponseRedirect(redirect_url)  
            except IntegrityError:
                # Redirect về trang trước đó
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))   # Redirect to the desired URL after handling the form submission
    return redirect('receiving_transaction')  # Redirect if it's not a POST request or if something goes wrong

#------------------- PACKAGE -------------------------------
# Export to excel packages function 
def export_packages_view(queryset):
    # Tạo file Excel mới
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Packages"
    # Tạo tiêu đề cho các cột
    columns = ['STT', 'id' ,'Mã thùng F88', 'Mã thùng F88 Cũ', 'Mã thùng Đối tác', 'Đối tác','Người tạo', 'Ngày tạo', 'Loại thùng', 'Trạng thái thùng', 'Khu vực' ]
    ws.append(columns)
    # Thêm dữ liệu vào file Excel
    for index, package in enumerate(queryset, start=1):
        partner_package = getattr(package, 'partnerpackage', None)
        ws.append([
            index,
            package.package_id,
            package.package_code,
            package.package_code_old or '',
            partner_package.partner_package_code if partner_package else '',
            partner_package.partner_name if partner_package else '',
            package.created_by.username, 
            package.created_date.strftime('%Y-%m-%d') if package.created_date else '',
            package.package_type.folder_type_name if package.package_type else '',
            partner_package.status_id.package_status_name if partner_package and partner_package.status_id else '',
            package.region_id.region_name if package.region_id else ''
        ])
    # Tạo response để gửi file Excel về cho client
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename=Packages_{timezone.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    
    wb.save(response)
    return response
# Package management 
@login_required
def package_management_view(request):
    user = request.user 
    user_context = get_user_context(user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        messages.error(request, "Unauthorized access.")
        return redirect('home')
    package_list = Package.objects.none()
    if request.method == 'GET':
        filters = {}
        choice_package = request.GET.get('choice_package')
        choice_partner_package = request.GET.get('choice_partner_package')
        choice_package_old = request.GET.get('choice_package_old')
        filterpackagestatus = request.GET.get('filterpackagestatus')
        filterregion = request.GET.get('filterregion')  
        choice_user_tao_thung = request.GET.get('choice_user_tao_thung')
        filter_empty_package = request.GET.get('filter_empty_package')
        
        if choice_package:
            filters['package_code__iexact'] = choice_package
        if choice_partner_package:
            filters['partnerpackage__partner_package_code__iexact'] = choice_partner_package
        if choice_package_old:
            filters['package_code_old__icontains'] = choice_package_old    
        if filterpackagestatus:
            filters['partnerpackage__status_id'] = filterpackagestatus
        if choice_user_tao_thung: 
            filters['created_by__username'] = choice_user_tao_thung.lower()
        if filterregion:
            filters['created_by__userprofile__region__region_id'] = filterregion
        if filter_empty_package == '1':
            filters['folder__isnull'] = True
        
        base_queryset = Package.objects.select_related('partnerpackage', 'package_type', 'region_id').annotate(folder_count=Count('folder', distinct=True)).order_by('-created_date')
        if len(filters)   == 0:
            package_list = base_queryset
        else : 
            package_list = base_queryset.filter(**filters)

        # Check if export to Excel is requested
        if request.GET.get('export') == '1':
            return export_packages_view(package_list)

        paginator = Paginator(package_list, 50)  # Show 50 documents per page
        page_number = request.GET.get('page')
        package_list = paginator.get_page(page_number)
        # filter_params = {
        #     'choice_package' :  request.GET.get('choice_package'),
        #     'choice_partner_package' : request.GET.get('choice_partner_package') ,
        #     'choice_package_old' : request.GET.get('choice_package_old'),
        #     'filterpackagestatus' : request.GET.get('filterpackagestatus'),
        #     'filterregion' : request.GET.get('filterregion')  ,
        #     'choice_user_tao_thung' : request.GET.get('choice_user_tao_thung'),
        # }
    user_by_role = AccessControls.get_users_based_on_role(user)
    region_by_role = AccessControls.get_regions_based_on_role(user)
    partnerpackage_status = PartnerPackageStatus.objects.all()
    partnerpackage_list = PartnerPackage.objects.all()
    partners = Partner.objects.filter(is_active=True).order_by('partner_name')
    partners_require_selection = partners.filter(require_partner_selection=True).exists()
    droplist_users =  user_by_role #User.objects.filter()
    droplist_regions = region_by_role ##Region.objects.filter()
    query_string = '&'.join(f"{key}={value}" for key, value in request.GET.items() if key != 'page')
    context = {
        **user_context,
        'package_list': package_list,
        'user': user,
        'partnerpackage_status': partnerpackage_status,
        'partnerpackage_list': partnerpackage_list,
        'droplist_users': droplist_users,
        'droplist_regions': droplist_regions,
        'partners': partners,
        'partners_require_selection': partners_require_selection,
     }
    context['query_string'] = query_string
    return render(request, 'app_documents/app_package_management.html', context )

@login_required
def package_list_management_view(request):
    user = request.user
    user_context = get_user_context(user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        messages.error(request, "Unauthorized access.")
        return redirect('home')

    search_term = request.GET.get('package_search', '').strip()
    status_filter = request.GET.get('status_id', '').strip()
    created_from = request.GET.get('created_from', '').strip()
    created_to = request.GET.get('created_to', '').strip()

    def _parse_input_date(val):
        if not val:
            return None
        try:
            return datetime.strptime(val, "%d/%m/%Y").date()
        except ValueError:
            return dateparse.parse_date(val)

    filters = Q()
    if search_term:
        filters &= (
            Q(package_code__icontains=search_term) |
            Q(package_code_old__icontains=search_term) |
            Q(partnerpackage__partner_package_code__icontains=search_term)
        )
    if status_filter:
        filters &= Q(partnerpackage__status_id=status_filter)
    start_date = _parse_input_date(created_from)
    end_date = _parse_input_date(created_to)
    if start_date:
        filters &= Q(created_date__date__gte=start_date)
    if end_date:
        filters &= Q(created_date__date__lte=end_date)

    base_queryset = Package.objects.select_related('partnerpackage', 'package_type', 'region_id').annotate(
        folder_count=Count('folder', distinct=True),
        shop_count=Count('folder__shop_id', distinct=True)
    ).order_by('-created_date')

    has_filters = bool(filters.children)
    filtered_queryset = base_queryset.filter(filters) if has_filters else base_queryset

    packages_queryset = filtered_queryset

    default_in_status = PartnerPackageStatus.objects.filter(is_in_warehouse=True).first()

    def build_status_payload(status_obj):
        if status_obj:
            color = status_obj.badge_color
            if not color:
                if status_obj.is_released:
                    color = '#DC2626'
                elif status_obj.is_backed:
                    color = '#D97706'
                elif status_obj.is_in_warehouse:
                    color = '#047857'
                else:
                    color = '#E5E7EB'
            return {
                'id': status_obj.status_id,
                'name': status_obj.package_status_name,
                'color': color,
                'isReleased': status_obj.is_released,
                'isBacked': status_obj.is_backed,
                'isInWarehouse': status_obj.is_in_warehouse,
            }
        if default_in_status:
            return {
                'id': default_in_status.status_id,
                'name': default_in_status.package_status_name,
                'color': default_in_status.badge_color or '#047857',
                'isReleased': default_in_status.is_released,
                'isBacked': default_in_status.is_backed,
                'isInWarehouse': default_in_status.is_in_warehouse,
            }
        return {
            'id': None,
            'name': 'Trong kho',
            'color': '#047857',
            'isReleased': False,
            'isBacked': False,
            'isInWarehouse': True,
        }

    packages_data = []
    for package in packages_queryset:
        partner_package = getattr(package, 'partnerpackage', None)
        status = partner_package.status_id if partner_package else None
        status_payload = build_status_payload(status)
        region_name = package.region_id.region_name if package.region_id else 'Chưa cập nhật'
        package_type = package.package_type.folder_type_name if package.package_type else 'Loại thùng'
        partner_name_display = ''
        if partner_package:
            partner_name_display = partner_package.partner.partner_name if partner_package.partner else partner_package.partner_name or ''
        partner_color = ''
        if partner_package and partner_package.partner and partner_package.partner.badge_color:
            partner_color = partner_package.partner.badge_color
        package_type_color = package.package_type.badge_color if package.package_type and package.package_type.badge_color else ''

        packages_data.append({
            'id': package.package_id,
            'packageCode': package.package_code,
            'packageCodeOld': package.package_code_old or '',
            'partnerPackageCode': partner_package.partner_package_code if partner_package else '',
            'partnerName': partner_name_display,
            'partnerId': partner_package.partner.partner_id if partner_package and partner_package.partner else None,
            'partnerColor': partner_color,
            'createdDate': package.created_date.strftime('%Y-%m-%d') if package.created_date else '',
            'status': status_payload,
            'packageType': package_type,
            'packageTypeColor': package_type_color,
            'regionName': region_name,
            'folderCount': getattr(package, 'folder_count', 0),
            'shopCount': getattr(package, 'shop_count', 0),
            'note': package.note or '',
            'createdBy': package.created_by.get_full_name() or package.created_by.username if package.created_by else '',
        })

    statuses = PartnerPackageStatus.objects.all().order_by('package_status_name')
    status_options_json = json.dumps(
        list(statuses.values('status_id', 'package_status_name', 'badge_color')),
        cls=DjangoJSONEncoder,
        ensure_ascii=False,
    )
    package_types = FolderType.objects.filter(is_valid=True).order_by('package_type', 'folder_type_name')
    partners_active = Partner.objects.filter(is_active=True).order_by('partner_name')
    partners_options_json = json.dumps(
        list(partners_active.values('partner_id', 'partner_name', 'partner_code', 'require_partner_selection', 'require_partner_code')),
        cls=DjangoJSONEncoder,
        ensure_ascii=False,
    )
    region_options_json = json.dumps(
        list(Region.objects.values('region_code', 'region_name')),
        cls=DjangoJSONEncoder,
        ensure_ascii=False,
    )
    folder_type_options_json = json.dumps(
        list(package_types.values('folder_type_code', 'folder_type_name', 'package_type')),
        cls=DjangoJSONEncoder,
        ensure_ascii=False,
    )

    context = {
        **user_context,
        'packages_json': json.dumps(packages_data, cls=DjangoJSONEncoder, ensure_ascii=False),
        'filters_json': json.dumps({
            'package_search': search_term,
            'status_id': status_filter,
            'created_from': created_from,
            'created_to': created_to,
        }, cls=DjangoJSONEncoder, ensure_ascii=False),
        'status_options_json': status_options_json,
        'package_types': package_types,
        'partners_active': partners_active,
        'partners_options_json': partners_options_json,
        'region_options_json': region_options_json,
        'folder_type_options_json': folder_type_options_json,
    }
    return render(request, 'app_documents/app_package_list_v2.html', context)


@login_required
def api_package_partner(request, package_id):
    user_context = get_user_context(request.user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        return JsonResponse({'error': 'Unauthorized access.'}, status=403)
    if request.method != "POST":
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        payload = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        payload = {}
    partner_id = payload.get("partner_id")
    partner_package_code_submit = (payload.get("partner_package_code") or "").strip()
    status_id_submit = payload.get("status_id")
    pkg = get_object_or_404(Package, pk=package_id)
    partner_obj = None
    if partner_id:
        partner_obj = Partner.objects.filter(pk=partner_id).first()
        if not partner_obj:
            return JsonResponse({'error': 'Partner not found.'}, status=400)
        if partner_obj.require_partner_code and not partner_package_code_submit:
            return JsonResponse({'error': f'Đối tác {partner_obj.partner_name} yêu cầu nhập mã thùng đối tác.'}, status=400)

    partner_package_code_value = partner_package_code_submit or None
    if partner_package_code_value and PartnerPackage.objects.exclude(package_id=pkg).filter(partner_package_code=partner_package_code_value).exists():
        return JsonResponse({'error': f'Mã thùng đối tác {partner_package_code_value} đã tồn tại.'}, status=400)

    status_obj = None
    if status_id_submit:
        status_obj = PartnerPackageStatus.objects.filter(pk=status_id_submit).first()
        if not status_obj:
            return JsonResponse({'error': 'Trạng thái không hợp lệ.'}, status=400)

    default_in_status = PartnerPackageStatus.objects.filter(is_in_warehouse=True).first()

    def build_status_payload(status_obj):
        if status_obj:
            color = status_obj.badge_color
            if not color:
                if status_obj.is_released:
                    color = '#DC2626'
                elif status_obj.is_backed:
                    color = '#D97706'
                elif status_obj.is_in_warehouse:
                    color = '#047857'
                else:
                    color = '#E5E7EB'
            return {
                'id': status_obj.status_id,
                'name': status_obj.package_status_name,
                'color': color,
                'isReleased': status_obj.is_released,
                'isBacked': status_obj.is_backed,
                'isInWarehouse': status_obj.is_in_warehouse,
            }
        if default_in_status:
            return {
                'id': default_in_status.status_id,
                'name': default_in_status.package_status_name,
                'color': default_in_status.badge_color or '#047857',
                'isReleased': default_in_status.is_released,
                'isBacked': default_in_status.is_backed,
                'isInWarehouse': default_in_status.is_in_warehouse,
            }
        return {
            'id': None,
            'name': 'Trong kho',
            'color': '#047857',
            'isReleased': False,
            'isBacked': False,
            'isInWarehouse': True,
        }

    partner_pkg, _ = PartnerPackage.objects.get_or_create(
        package_id=pkg,
        defaults={
            "created_date": timezone.now(),
            "created_by": request.user,
        },
    )
    old_partner = partner_pkg.partner
    old_partner_name = partner_pkg.partner_name
    old_code = partner_pkg.partner_package_code
    old_status = partner_pkg.status_id

    # Chặn cập nhật mã đối tác nếu đã release
    if old_status and old_status.is_released:
        if partner_package_code_value and partner_package_code_value != old_code:
            return JsonResponse({'error': 'Thùng đã ở trạng thái released, không được cập nhật mã thùng đối tác.'}, status=400)

    # Kiểm tra quyền đổi trạng thái nếu đã release/backed
    if status_obj and old_status and (old_status.is_released or old_status.is_backed) and not user_context['is_admin']:
        if old_status.status_id != status_obj.status_id:
            return JsonResponse({'error': 'Chỉ Admin được đổi trạng thái khi thùng đã ở trạng thái released/backed.'}, status=403)

    # Kiểm tra flow trạng thái hợp lệ
    def allow_transition(current, new):
        if not new:
            return True
        if not current or current.is_in_warehouse:
            return new.is_released or new.is_in_warehouse
        if current.is_released:
            return new.is_released or new.is_backed
        if current.is_backed:
            return new.is_backed or new.is_released
        return True

    if status_obj and not allow_transition(old_status, status_obj):
        return JsonResponse({'error': 'Không hợp lệ: chỉ cho phép luồng in_warehouse -> released -> backed -> released.'}, status=400)

    partner_pkg.partner = partner_obj
    partner_pkg.partner_name = partner_obj.partner_name if partner_obj else None
    partner_pkg.partner_package_code = partner_package_code_value
    if status_obj:
        partner_pkg.status_id = status_obj
    elif not partner_pkg.status_id and default_in_status:
        partner_pkg.status_id = default_in_status
    if not partner_pkg.created_date:
        partner_pkg.created_date = timezone.now()
    partner_pkg.updated_date = timezone.now()
    partner_pkg.save()

    def log_history(action, old_val, new_val):
        if (old_val or '') == (new_val or ''):
            return None
        return PartnerPackageHistory.objects.create(
            package=pkg,
            action=action,
            old_value=old_val or '',
            new_value=new_val or '',
            created_by=request.user,
        )

    log_history('partner_change', old_partner_name or getattr(old_partner, 'partner_name', None), partner_pkg.partner_name)
    log_history('partner_code_change', old_code, partner_pkg.partner_package_code)
    log_history('status_change', old_status.package_status_name if old_status else None, partner_pkg.status_id.package_status_name if partner_pkg.status_id else None)

    current_status = partner_pkg.status_id
    status_payload = build_status_payload(current_status)

    history_qs = PartnerPackageHistory.objects.filter(package=pkg).select_related('created_by').order_by('-created_at')[:20]
    history_payload = []
    for h in history_qs:
        history_payload.append({
            'action': h.action,
            'oldValue': h.old_value or '',
            'newValue': h.new_value or '',
            'user': h.created_by.get_full_name() or h.created_by.username if h.created_by else '',
            'date': h.created_at.strftime('%Y-%m-%d %H:%M'),
        })

    return JsonResponse({
        'status': 'ok',
        'partner_id': partner_obj.partner_id if partner_obj else None,
        'partner_name': partner_obj.partner_name if partner_obj else '',
        'partner_package_code': partner_pkg.partner_package_code or '',
        'status_obj': status_payload,
        'history': history_payload,
    })


@login_required
def api_package_note(request, package_id):
    user_context = get_user_context(request.user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        return JsonResponse({'error': 'Unauthorized access.'}, status=403)
    if request.method != "POST":
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    pkg = get_object_or_404(Package, pk=package_id)
    try:
        payload = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        payload = {}
    note_val = payload.get("note")
    note_clean = note_val.strip() if isinstance(note_val, str) else ""
    pkg.note = note_clean or None
    pkg.updated_date = timezone.now()
    pkg.save(update_fields=["note", "updated_date"])
    return JsonResponse({"success": True, "note": pkg.note or ""})


@login_required
def package_list_detail_view(request, package_id):
    user = request.user
    user_context = get_user_context(user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        return JsonResponse({'error': 'Unauthorized access.'}, status=403)

    package = get_object_or_404(
        Package.objects.select_related('partnerpackage', 'package_type', 'region_id'),
        pk=package_id
    )

    documents_prefetch = Prefetch(
        'documentsdetail_set',
        queryset=DocumentsDetail.objects.select_related('document_status_id', 'document_type_id', 'loan_id', 'contract_id').order_by('documents_created_date')
    )
    folders_prefetch = Prefetch(
        'folder_set',
        queryset=Folder.objects.select_related('shop_id', 'folder_type_id', 'folder_status_id').prefetch_related(documents_prefetch).order_by('shop_id__shop_name', 'folder_created_date')
    )
    package = Package.objects.select_related('partnerpackage', 'package_type', 'region_id').prefetch_related(folders_prefetch).get(pk=package_id)

    partner_package = getattr(package, 'partnerpackage', None)
    status = partner_package.status_id if partner_package else None
    default_in_status = PartnerPackageStatus.objects.filter(is_in_warehouse=True).first()

    def build_status_payload(status_obj):
        if status_obj:
            color = status_obj.badge_color
            if not color:
                if status_obj.is_released:
                    color = '#DC2626'
                elif status_obj.is_backed:
                    color = '#D97706'
                elif status_obj.is_in_warehouse:
                    color = '#047857'
                else:
                    color = '#E5E7EB'
            return {
                'name': status_obj.package_status_name,
                'color': color,
                'id': status_obj.status_id,
                'isReleased': status_obj.is_released,
                'isBacked': status_obj.is_backed,
                'isInWarehouse': status_obj.is_in_warehouse,
            }
        if default_in_status:
            return {
                'name': default_in_status.package_status_name,
                'color': default_in_status.badge_color or '#047857',
                'id': default_in_status.status_id,
                'isReleased': default_in_status.is_released,
                'isBacked': default_in_status.is_backed,
                'isInWarehouse': default_in_status.is_in_warehouse,
            }
        return {
            'name': 'Trong kho',
            'color': '#047857',
            'id': None,
            'isReleased': False,
            'isBacked': False,
            'isInWarehouse': True,
        }
    status_payload = build_status_payload(status)
    region_name = package.region_id.region_name if package.region_id else 'Chưa cập nhật'
    package_type = package.package_type.folder_type_name if package.package_type else 'Loại thùng'
    partner_name_display = ''
    if partner_package:
        partner_name_display = partner_package.partner.partner_name if partner_package.partner else partner_package.partner_name or ''
    partner_color = ''
    if partner_package and partner_package.partner and partner_package.partner.badge_color:
        partner_color = partner_package.partner.badge_color
    package_type_color = package.package_type.badge_color if package.package_type and package.package_type.badge_color else ''
    created_by_name = package.created_by.get_full_name() or package.created_by.username if package.created_by else ''

    shop_groups = {}
    for folder in getattr(package, 'folder_set', []).all():
        shop = folder.shop_id
        shop_name = shop.shop_name if shop else 'PGD chưa rõ'
        shop_code = shop.shop_code if shop else ''
        key = f"{shop_name}-{shop_code}"
        if key not in shop_groups:
            shop_groups[key] = {
                'shopName': shop_name,
                'shopCode': shop_code,
                'count': 0,
                'folders': []
            }
        shop_groups[key]['count'] += 1
        documents_iterable = folder.documentsdetail_set.select_related('document_status_id', 'document_type_id', 'loan_id', 'contract_id').all()
        docs_payload = []
        for doc in documents_iterable:
            doc_type = doc.document_type_id.document_type_name if doc.document_type_id else ''
            doc_status = doc.document_status_id.documents_status_name if doc.document_status_id else '---'
            contract_code = doc.contract_id.contract_code if doc.contract_id else ''
            loan_code = doc.loan_id.loan_code if doc.loan_id else ''
            docs_payload.append({
                'code': doc.documents_code,
                'type': doc_type,
                'createdDate': doc.documents_created_date.strftime('%Y-%m-%d') if doc.documents_created_date else '',
                'status': doc_status,
                'refCode': contract_code or loan_code or '',
            })

        shop_groups[key]['folders'].append({
            'folderCode': folder.folder_code,
            'typeLabel': 'Gốc' if folder.is_original else 'Bổ sung',
            'createdDate': folder.folder_created_date.strftime('%Y-%m-%d') if folder.folder_created_date else '',
            'folderStatus': folder.folder_status_id.folder_status_name if getattr(folder, 'folder_status_id', None) else '---',
            'documents': docs_payload,
        })

    detail_payload = {
        'id': package.package_id,
        'packageCode': package.package_code,
        'packageCodeOld': package.package_code_old or '',
        'partnerPackageCode': partner_package.partner_package_code if partner_package else '',
        'partnerName': partner_name_display,
        'partnerId': partner_package.partner.partner_id if partner_package and partner_package.partner else None,
        'partnerColor': partner_color,
        'createdDate': package.created_date.strftime('%Y-%m-%d') if package.created_date else '',
        'createdBy': created_by_name,
        'status': status_payload,
        'packageType': package_type,
        'packageTypeColor': package_type_color,
        'regionName': region_name,
        'folderCount': getattr(package, 'folder_set', []).count(),
        'shopCount': len(shop_groups.keys()),
        'foldersByShop': list(shop_groups.values()),
        'note': package.note or '',
        'history': [],
    }
    history_qs = PartnerPackageHistory.objects.filter(package=package).select_related('created_by').order_by('-created_at')[:20]
    detail_payload['history'] = [
        {
            'action': h.action,
            'oldValue': h.old_value or '',
            'newValue': h.new_value or '',
            'user': h.created_by.get_full_name() or h.created_by.username if h.created_by else '',
            'date': h.created_at.strftime('%Y-%m-%d %H:%M'),
        }
        for h in history_qs
    ]
    return JsonResponse(detail_payload, safe=False)

# Package management edit view
@login_required
def edit_package_view(request, package_id):
    user = request.user
    user_context = get_user_context(user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        return JsonResponse({'error': 'Unauthorized access.'}, status=403)
    package = get_object_or_404(Package, pk=package_id)
    partners_qs = Partner.objects.filter(is_active=True)
    partners_require_selection = partners_qs.filter(require_partner_selection=True).exists()
    if request.method == 'POST':
        partner_package_code_submit = request.POST.get('partner_code_choice', '').strip()
        partner_id_choice = request.POST.get('partner_id_choice')
        old_package_code_choice = request.POST.get('old_package_code_choice')
        date_action = timezone.now()

        partner_instance = None
        if partner_id_choice:
            partner_instance = partners_qs.filter(partner_id=partner_id_choice).first()
            if not partner_instance:
                return JsonResponse({'error': 'Đối tác không tồn tại hoặc đã bị vô hiệu.'}, status=400)
        elif partners_require_selection and partners_qs.exists():
            return JsonResponse({'error': 'Vui lòng chọn đối tác lưu trữ.'}, status=400)
        if partner_instance and partner_instance.require_partner_code and not partner_package_code_submit:
            return JsonResponse({'error': f'Đối tác {partner_instance.partner_name} yêu cầu nhập mã thùng đối tác.'}, status=400)
        if partner_package_code_submit and PartnerPackage.objects.exclude(package_id=package).filter(partner_package_code=partner_package_code_submit).exists():
            return JsonResponse({'error': f'Mã thùng đối tác {partner_package_code_submit} đã tồn tại.'}, status=400)
        
        partner_package_code_value = partner_package_code_submit or None
        try:
            partner_package = PartnerPackage.objects.get(package_id=package)
        except PartnerPackage.DoesNotExist:
            partner_package = None

        if partner_instance:
            if partner_package:
                has_changes = (
                    partner_package.partner_package_code != partner_package_code_value or
                    partner_package.partner_id != (partner_instance.partner_id if partner_instance else None)
                )
                if has_changes:
                    partner_package.partner_package_code = partner_package_code_value
                    partner_package.partner_name = partner_instance.partner_code
                    partner_package.partner = partner_instance
                    partner_package.updated_date = date_action
                    partner_package.save()
                else:
                    return JsonResponse({'message': 'No changes detected.'})
            else:
                default_status = PartnerPackageStatus.objects.get(status_id=1)
                PartnerPackage.objects.create(
                    package_id=package,
                    partner_package_code=partner_package_code_value,
                    partner_name=partner_instance.partner_code,
                    partner=partner_instance,
                    created_date=date_action,
                    created_by=user,
                    status_id=default_status
                )
        else:
            # No partner selected, remove existing relation if exists
            if partner_package:
                partner_package.delete()
        
        if old_package_code_choice and old_package_code_choice != package.package_code_old:
            package.package_code_old = old_package_code_choice
            package.updated_date = date_action
            package.save()
        
        return JsonResponse({'message': f'Package {package.package_code} updated successfully.', 'package_id': package.package_id})
    return JsonResponse({'error': 'Invalid request method.'}, status=405)

# Function điều kiện validate định dạng mã thùng
def validate_package_code(value, user):
    package_pattern = r'^(CIMB|NH|VH)-(\d{6})-([A-Za-z0-9]{1})(\d{2})$'
    match = re.match(package_pattern, value)
    profile = UserProfile.objects.get(user=user)
    region_code_user = (profile.region.region_code or "").upper()
    if not match:
        return {
            'is_valid': False,
            'error': "Tên thùng phải tuân thủ định dạng '{FOLDER_TYPE}-{yyMMdd}-{region_code}{bb}' (ví dụ: VH-241001-M01)."
        }
    prefix_part, date_part, region_part, sequence_part = match.groups()
    if not (1 <= int(sequence_part) <= 99):
        return {'is_valid': False, 'error': "Số thứ tự bb phải từ 01-99."}
    if prefix_part.upper() not in ['CIMB', 'NH', 'VH']:
        return {'is_valid': False, 'error': "FOLDER_TYPE phải là CIMB/NH/VH."}
    if region_code_user and region_part.upper() != region_code_user[:1]:
        return {'is_valid': False, 'error': f"Bạn là vùng {region_code_user}, vui lòng dùng mã vùng {region_code_user[:1]} trong package_code."}
    existing_codes = Package.objects.filter(package_code__startswith=f'{prefix_part}-{date_part}-{region_part}')
    if existing_codes.exists():
        last_sequence = max(int(code.package_code.split('-')[-1][1:]) for code in existing_codes)
        if int(sequence_part) <= last_sequence:
            return {'is_valid': False, 'error': "Thùng với số thứ tự này đã tồn tại. Vui lòng tạo số thứ tự cao hơn."}
    if Package.objects.filter(package_code=value).exists():
        return {'is_valid': False, 'error': "Thùng đã tồn tại trong hệ thống. Vui lòng nhập lại."}
    return {'is_valid': True}


def validate_package_code_v2(value, selected_region_code=None):
    """
    Cú pháp mới: {FolderType}-{yymmdd}-{a}{bb}
    FolderType: lấy theo package_type của FolderType (VD: VH/NH/CIMB, mở rộng được).
    yymmdd: ngày tạo thùng.
    a: mã vùng/kho người dùng chọn.
    bb: số thứ tự 2 chữ số, không trùng, max 99.
    """
    code = (value or "").strip().upper()
    pattern = r'^([A-Z0-9]{2,10})-(\d{6})-([A-Z0-9]{1})(\d{2})$'
    match = re.match(pattern, code)
    if not match:
        return {'is_valid': False, 'error': "Mã thùng phải theo định dạng {FolderType}-yymmdd-aBB (ví dụ: VH-241231-M01)."}

    folder_type_part, date_part, region_part, seq_part = match.groups()

    folder_type_obj = FolderType.objects.filter(package_type__iexact=folder_type_part, is_valid=True).first()
    if not folder_type_obj:
        return {'is_valid': False, 'error': "Loại thùng không hợp lệ. Vui lòng chọn loại trong danh sách."}

    try:
        created_date = datetime.strptime(date_part, "%y%m%d").date()
    except ValueError:
        return {'is_valid': False, 'error': "Ngày trong mã thùng không hợp lệ (yymmdd)."}

    try:
        seq_int = int(seq_part)
    except ValueError:
        return {'is_valid': False, 'error': "Số thứ tự BB phải là số."}
    if not (1 <= seq_int <= 99):
        return {'is_valid': False, 'error': "Số thứ tự BB phải từ 01-99."}

    region_char = region_part.upper()
    if selected_region_code:
        selected_region_char = selected_region_code.strip().upper()[:1]
        if region_char != selected_region_char:
            return {'is_valid': False, 'error': f"Mã kho (a) phải khớp vùng đang chọn: {selected_region_char}."}

    prefix = f"{folder_type_part.upper()}-{date_part}-{region_char}"
    existing_qs = Package.objects.filter(package_code__istartswith=prefix)
    if existing_qs.filter(package_code__iexact=code).exists():
        return {'is_valid': False, 'error': "Mã thùng đã tồn tại."}

    max_seq = 0
    for pkg in existing_qs:
        tail = pkg.package_code.rsplit('-', 1)[-1]
        if not tail:
            continue
        tail_region = tail[:1].upper()
        tail_seq = tail[1:]
        if tail_region != region_char:
            continue
        try:
            tail_seq_int = int(tail_seq)
            if tail_seq_int > max_seq:
                max_seq = tail_seq_int
        except ValueError:
            continue

    next_suggested = max_seq + 1 if max_seq < 99 else None
    if seq_int <= max_seq:
        msg = f"Số thứ tự đã dùng đến {max_seq:02d} cho {prefix}."
        if next_suggested and next_suggested <= 99:
            msg += f" Gợi ý: dùng {next_suggested:02d}."
        return {'is_valid': False, 'error': msg, 'next_suggested_sequence': next_suggested}

    return {
        'is_valid': True,
        'normalized_code': code,
        'folder_type': folder_type_obj,
        'created_date': created_date,
        'region_part': region_char,
        'next_suggested_sequence': next_suggested,
    }

# View cho phép tạo thùng mới
@login_required
def create_package_view(request, user_id):
    user= User.objects.get(pk=user_id)
    user_context = get_user_context(request.user)
    user_profiles = UserProfile.objects.get(user=user)
    package_type = FolderType.objects.filter(is_valid=True)
    regions = Region.objects.all()
    partners_qs = Partner.objects.filter(is_active=True).order_by('partner_name')
    partners_require_selection = partners_qs.filter(require_partner_selection=True).exists()
    context = {
        'employee_code': user_profiles.employee_code,
        'region_code': user_profiles.region.region_code,
        **user_context,
        'user': user,
        'user_profiles': user_profiles,
        'package_types': package_type,
        'regions' : regions,
        'partners': partners_qs,
        'partners_require_selection': partners_require_selection,
        }
    if not user_context['is_admin'] and not user_context['is_checker']:
        messages.error(request, "Bạn không có quyền truy cập trang này.")
        return redirect('home')
    if request.method == 'POST':
        package_code_submit = request.POST.get('package_code_submit')
        partner_package_code_submit = request.POST.get('partner_package_code_choice', '').strip()
        partner_id_submit = request.POST.get('partner_id_choice')
        package_type_submit = request.POST.get('package_type_choice')
        package_region_submit = request.POST.get('region_choice')
        partner_instance = None
        if partner_id_submit:
            try:
                partner_instance = partners_qs.get(partner_id=partner_id_submit)
            except Partner.DoesNotExist:
                return JsonResponse({'success': False, 'message': 'Đối tác không tồn tại hoặc đã bị vô hiệu.'}, status=400)
        elif partners_require_selection and partners_qs.exists():
            return JsonResponse({'success': False, 'message': 'Vui lòng chọn đối tác lưu trữ.'}, status=400)
        if partner_instance and partner_instance.require_partner_code and not partner_package_code_submit:
            return JsonResponse({'success': False, 'message': f'Đối tác {partner_instance.partner_name} yêu cầu nhập mã thùng đối tác.'}, status=400)
        if partner_package_code_submit and PartnerPackage.objects.filter(partner_package_code=partner_package_code_submit).exists():
            return JsonResponse({'success': False, 'message': f'Mã thùng đối tác {partner_package_code_submit} đã tồn tại trong hệ thống.'}, status=400)
        if not partner_instance and partners_qs.exists():
            return JsonResponse({'success': False, 'message': 'Vui lòng chọn đối tác lưu trữ.'}, status=400)
        # Validate package code using the custom validation function
        validation_result = validate_package_code(package_code_submit, user)
        if not validation_result['is_valid']:
            return JsonResponse({'success': False, 'message': validation_result['error']}, status=400)
        # Save new package
        package = Package.objects.create(
            package_code=package_code_submit,
            package_type= FolderType.objects.get(package_type=package_type_submit),
            created_by=request.user,
            region_id =  Region.objects.get(region_code=package_region_submit) 
        )
        partner_package = None
        if partner_instance:
            partner_status_instance_1 = PartnerPackageStatus.objects.get(status_id=1)  # Assuming status_id=1 means 'newly created'
            partner_package = PartnerPackage.objects.create(
                package_id=package,
                partner_package_code=partner_package_code_submit or None,
                partner_name=partner_instance.partner_code,
                partner=partner_instance,
                created_date=timezone.now(),
                status_id=partner_status_instance_1,
                created_by=request.user
            )
        payload = {
            'package_id': model_to_dict(package),
            'partner_package': model_to_dict(partner_package) if partner_package else None,
            'success': True,
            'message': 'Tạo thùng mới thành công.'
            }
        return JsonResponse(payload, status=200)
    
    return render(request, 'app_documents/app_create_package.html', context)

# View GEN số thứ tự tiếp theo cho thùng mới
@login_required
def get_next_package_sequence(request):
    base_code = request.GET.get('baseCode')
    if not base_code:
        return JsonResponse({'success': False, 'message': 'Base code is required.'})
    try:
        existing_codes = Package.objects.filter(package_code__startswith=base_code)
        max_sequence = 0
        for package in existing_codes:
            try:
                sequence = int(package.package_code.split('-')[-1][1:])
                max_sequence = max(max_sequence, sequence)
            except (ValueError, IndexError) as e:
                logger.error(f"Error parsing sequence from package code {package.package_code}: {e}")
                continue
        
        next_sequence = max_sequence + 1
        if next_sequence >= 100:
            return JsonResponse({'success': False, 'message': 'No available sequences left.'})
        
        return JsonResponse({'success': True, 'nextSequence': f"{next_sequence:02d}"})
    except Exception as e:
        logger.error("Failed to fetch package sequence", exc_info=True)
        return JsonResponse({'success': False, 'message': 'Server error when fetching sequence number.'})

@login_required
def api_package_create_v2(request):
    """
    Endpoint tạo thùng v2 qua JSON body, dùng validate_package_code_v2.
    Body mẫu:
    {
      "package_code": "VH-241231-M01",
      "region_code": "M",   # 1 ký tự vùng/kho người chọn
      "partner_id": 123,    # optional
      "partner_package_code": "CRN-001",  # optional
      "folder_type_id": 5   # optional, để cross-check với package_code
    }
    """
    user_context = get_user_context(request.user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        return JsonResponse({'error': 'Unauthorized access.'}, status=403)
    if request.method != "POST":
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        payload = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON payload.'}, status=400)

    package_code = (payload.get('package_code') or '').strip()
    region_code = (payload.get('region_code') or '').strip()
    partner_id = payload.get('partner_id')
    partner_package_code = (payload.get('partner_package_code') or '').strip() or None
    folder_type_id = payload.get('folder_type_id')

    validation = validate_package_code_v2(package_code, selected_region_code=region_code)
    if not validation.get('is_valid'):
        resp = {'error': validation.get('error', 'Validation failed.')}
        if validation.get('next_suggested_sequence'):
            resp['next_suggested_sequence'] = validation['next_suggested_sequence']
        return JsonResponse(resp, status=400)

    folder_type_obj = validation['folder_type']
    if folder_type_id and str(folder_type_id) != str(folder_type_obj.folder_type_id):
        return JsonResponse({'error': 'Loại thùng ở mã và lựa chọn không khớp.'}, status=400)

    region_obj = None
    if region_code:
        region_obj = Region.objects.filter(region_code__iexact=region_code[:1]).first()
        if not region_obj:
            return JsonResponse({'error': f"Mã vùng {region_code} không tồn tại."}, status=400)

    partner_obj = None
    if partner_id:
        try:
            partner_obj = Partner.objects.get(partner_id=partner_id, is_active=True)
        except Partner.DoesNotExist:
            return JsonResponse({'error': 'Đối tác không tồn tại hoặc đã bị vô hiệu.'}, status=400)

    if partner_package_code and PartnerPackage.objects.filter(partner_package_code=partner_package_code).exists():
        return JsonResponse({'error': f'Mã thùng đối tác {partner_package_code} đã tồn tại trong hệ thống.'}, status=400)

    default_status = PartnerPackageStatus.objects.filter(is_in_warehouse=True).first() or PartnerPackageStatus.objects.filter(status_id=1).first()

    try:
        with transaction.atomic():
            created_dt = timezone.make_aware(datetime.combine(validation['created_date'], datetime.min.time()))
            package = Package.objects.create(
                package_code=validation['normalized_code'],
                package_type=folder_type_obj,
                created_by=request.user,
                region_id=region_obj,
                created_date=created_dt,
            )
            partner_package = None
            if partner_obj or partner_package_code:
                partner_package = PartnerPackage.objects.create(
                    package_id=package,
                    partner_package_code=partner_package_code,
                    partner_name=partner_obj.partner_code if partner_obj else None,
                    partner=partner_obj,
                    created_date=timezone.now(),
                    status_id=default_status,
                    created_by=request.user,
                )
    except Exception as e:
        logger.error("api_package_create_v2 failed", exc_info=True)
        return JsonResponse({'error': f'Lỗi hệ thống: {str(e)}'}, status=500)

    return JsonResponse({
        'success': True,
        'package': {
            'id': package.package_id,
            'package_code': package.package_code,
            'package_type': folder_type_obj.package_type,
            'folder_type_id': folder_type_obj.folder_type_id,
            'region': region_obj.region_code if region_obj else None,
        },
        'partner_package': {
            'id': partner_package.pk,
            'partner_package_code': partner_package.partner_package_code,
            'partner_id': partner_obj.partner_id if partner_obj else None,
        } if partner_package else None,
        'next_suggested_sequence': validation.get('next_suggested_sequence'),
    }, status=200)

# View cho phép xóa thùng  
@login_required
def clear_package_view(request, folder_id): 
    ''' Xóa thùng của quyển chứng từ 
    Chỉ cho phép xóa thùng trong ngày hiện tại.
    So sánh ngày hiện tại với ngày gán thùng vào quyển chứng từ (Folder) 
    Ngày gán quyển chứng từ trong bảng TransactionReceiving 
    ''' 
    if request.method == 'POST':
        data = json.loads(request.body)
        package_id = data.get('package_id_submit')
        if package_id:
            today = timezone.now().date() 
            # Kiểm tra trong quyển chứng từ đã được duyệt chưa? 
            if DocumentsDetail.objects.filter(folder_id=folder_id,document_status_id__documents_status_code = '102').exists(): 
                return JsonResponse({'success': False, 'message': 'Quyển chứng từ đã có chứng từ được duyệt, Không được gỡ thùng khỏi quyển chứng từ.'})
            # Kiểm tra ngày gán thùng lớn nhất vào quyển chứng từ 
            if FoldersTransactionReceiving.objects.filter(folder_id=folder_id, trans_created_date__date = today).exists(): 
                Folder.objects.filter(folder_id=folder_id).update(package_id=None)
                DocumentsDetail.objects.filter(folder_id=folder_id).update(package_id=None)
                Folder.objects.filter(folder_id=folder_id).update(
                        lastest_received_date=None
                    ,   lastest_received_by=None
                    ,   folder_status_id= FolderStatus.objects.get( is_not_received_yet = True )
                    ,   is_on_time = None 
                    ,   is_late = None 
                    ,   note = None)
                return JsonResponse({'success': True, 'message': 'Xóa thùng thành công.'})
            else:
                return JsonResponse({'success': False, 'message': 'Đã quá thời hạn xóa thùng. Liên hệ admin'})
        else:
            return JsonResponse({'success': False, 'message': 'Không tìm thấy thùng cần xóa.'})
    return JsonResponse({'success': False, 'message': 'Invalid request.'})

# View kiểm tra thùng F88
@login_required
def check_package_view(request):
    package_code = request.GET.get('user_entering_package_code', '').strip()
    # First, check if the package code matches the required format
    package_pattern = r'^(VH|CIMB)-(\d{6})-(\d)(\d{2})$'
    if not re.match(package_pattern, package_code):
        return JsonResponse({
            'is_valid_package': False,
            'error_message': "Định dạng thùng phải đúng template 'TYPE-yymmdd-axx'. Với TYPE là loại thùng.\nyymmdd: là năm-tháng-ngày-hiện tại.\na sẽ là mã vùng của bạn\nxx phải là chữ số thứ tự từ 01-99"
            'package_exists'
        })
    # Then, check if the package code already exists in the database
    package_exists = Package.objects.filter(package_code=package_code).exists()
    if package_exists:
        partner_package_status_noneligible = PartnerPackage.objects.filter( package_id__package_code = package_code , status_id__status_id = 2).exists()
        return JsonResponse({
            'is_valid_package': False,
            'error_message': f'Thùng {package_code} đã tồn tại trong hệ thống. Vui lòng nhập mã khác.',
            'package_exists' : package_exists,
            'partner_package_status_noneligible': partner_package_status_noneligible
        })
    # If both checks pass, the package code is considered valid
    return JsonResponse({
        'is_valid_package': True,
        'error_message': '',
        'package_exists' : package_exists 
        })

# View kiểm tra thùng Đối tác
@login_required 
def check_partner_package_view(request): 
    partner_package_code = request.GET.get('user_entering_partner_package_code', '').strip() 
    package_partner_exists = PartnerPackage.objects.filter(partner_package_code=partner_package_code).exists()
    if package_partner_exists:
        return JsonResponse({
            'error_message': f'Thùng {partner_package_code} đã tồn tại trong hệ thống. Vui lòng nhập mã khác.',
            'package_partner_exists' : package_partner_exists
        })
    return JsonResponse({ 
        'error_message': '',
        'package_partner_exists' : package_partner_exists
    })

# View chuyển trạng thái thùng đối tác 
@login_required
def change_partnerpackage_status(request, package_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            new_partnerpackage_status_id = data.get('new_partnerpackage_status')

            if not new_partnerpackage_status_id:
                return JsonResponse({'success': False, 'error': 'Trạng thái mới không hợp lệ.'}, status=400)

            partnerpackage = get_object_or_404(PartnerPackage, package_id_id=package_id)
            new_status = get_object_or_404(PartnerPackageStatus, pk=new_partnerpackage_status_id)
            partnerpackage.status_id = new_status
            partnerpackage.save()
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    else:
        return JsonResponse({'success': False, 'error': 'Yêu cầu không hợp lệ.'}, status=400)
# ----------------- BULK PACKAGE (validate + save) -----------------
def _parse_date_safe(val):
    if pd.isna(val):
        return None
    parsed = pd.to_datetime(val, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def _validate_bulk_packages(df, user, user_context, upload_filename=""):
    def _clean_str(val):
        if pd.isna(val):
            return ""
        return str(val).strip()

    required_cols = [
        "package_code",
        "package_type",
        "region_code",
        "partner_code",
        "partner_package_code",
        "created_date",
        "note",
        "username",
    ]
    df = df.rename(columns={c: c.strip().lower() for c in df.columns})
    rename_map = {
        "folder_type": "package_type",
        "folder_typeid": "package_type",
        "package_type_code": "package_type",
        "region": "region_code",
        "partner": "partner_code",
        "partner_code": "partner_code",
        "partner_package": "partner_package_code",
        "partner_packagecode": "partner_package_code",
        "created": "created_date",
        "created_at": "created_date",
        "creator": "username",
    }
    for src, dst in rename_map.items():
        if src in df.columns and dst not in df.columns:
            df = df.rename(columns={src: dst})
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValidationError(f"Thiếu cột: {', '.join(missing)}")

    pattern = re.compile(r"^(CIMB|NH|VH)-(\d{6})-([A-Za-z0-9]{1})(\d{2})$")
    region_map = {r.region_code.upper(): r for r in Region.objects.all()}
    folder_types = list(FolderType.objects.filter(is_valid=True))
    folder_type_by_package = {}
    for ft in folder_types:
        key = (ft.package_type or "").upper()
        if key not in folder_type_by_package:
            folder_type_by_package[key] = []
        folder_type_by_package[key].append(ft)
    partner_map = {p.partner_code.upper(): p for p in Partner.objects.filter(is_active=True)}

    seen_package = set()
    seen_partner_pkg = set()

    result_rows = []
    valid_rows = []

    for idx, row in df.iterrows():
        errors = []
        raw_code = _clean_str(row.get("package_code"))
        package_type_val = _clean_str(row.get("package_type"))
        region_code = _clean_str(row.get("region_code"))
        partner_code = _clean_str(row.get("partner_code"))
        partner_pkg_code = _clean_str(row.get("partner_package_code"))
        created_date_val = _parse_date_safe(row.get("created_date"))
        note_val_raw = row.get("note")
        username_val = _clean_str(row.get("username"))

        match = pattern.match(raw_code)
        if not raw_code:
            errors.append("Thiếu package_code.")
        elif not match:
            errors.append("package_code không đúng format {FOLDER_TYPE}-{yyMMdd}-{region}{bb}.")
        else:
            prefix, ymd, region_in_code, seq = match.groups()
            if package_type_val and prefix.upper() != package_type_val.upper():
                errors.append("package_code không khớp package_type.")
            if region_code and region_in_code.upper() != region_code.upper():
                errors.append("package_code không khớp region_code.")
            if seq == "00":
                errors.append("Số thứ tự bb phải từ 01-99.")

        folder_type_obj = None
        resolved_folder_type_code = ""
        if package_type_val:
            ft_list = folder_type_by_package.get(package_type_val.upper(), [])
            if not ft_list:
                errors.append(f"package_type '{package_type_val}' không tồn tại.")
            elif len(ft_list) > 1:
                errors.append(
                    f"package_type '{package_type_val}' mapping nhiều folder_type_code: "
                    f"{', '.join([ft.folder_type_code for ft in ft_list if ft.folder_type_code])}. "
                    "Vui lòng cấu hình/chuẩn hóa để duy nhất."
                )
            else:
                folder_type_obj = ft_list[0]
                resolved_folder_type_code = folder_type_obj.folder_type_code or ""

        region_obj = None
        if region_code:
            region_obj = region_map.get(region_code.upper())
            if not region_obj:
                errors.append(f"region_code '{region_code}' không tồn tại.")

        partner_obj = None
        if partner_code:
            partner_obj = partner_map.get(partner_code.upper())
            if not partner_obj:
                errors.append(f"partner_code '{partner_code}' không tồn tại.")

        if partner_pkg_code:
            if partner_pkg_code in seen_partner_pkg:
                errors.append(f"partner_package_code '{partner_pkg_code}' trùng trong file.")
            if PartnerPackage.objects.filter(partner_package_code=partner_pkg_code).exists():
                errors.append(f"partner_package_code '{partner_pkg_code}' đã tồn tại.")

        if raw_code:
            if raw_code in seen_package:
                errors.append(f"package_code '{raw_code}' trùng trong file.")
            if Package.objects.filter(package_code=raw_code).exists():
                errors.append(f"package_code '{raw_code}' đã tồn tại.")

        if partner_obj and partner_obj.require_partner_code and not partner_pkg_code:
            errors.append(f"Đối tác {partner_obj.partner_name} yêu cầu partner_package_code.")

        creator = user
        used_creator = user.username
        if user_context.get("is_admin"):
            if username_val:
                creator = User.objects.filter(username=username_val).first()
                if not creator:
                    errors.append(f"username '{username_val}' không tồn tại.")
                else:
                    used_creator = creator.username
            else:
                creator = user
                used_creator = user.username
        else:
            # Non-admin: ignore provided username, always use uploader
            creator = user
            used_creator = user.username

        if created_date_val:
            try:
                created_dt = datetime.combine(created_date_val, datetime.min.time())
                if timezone.is_naive(created_dt):
                    created_dt = timezone.make_aware(created_dt, timezone.get_current_timezone())
            except Exception:
                errors.append("created_date không hợp lệ.")
        else:
            created_dt = timezone.now()

        if pd.isna(note_val_raw) or str(note_val_raw).strip() == "":
            note_val = f"Dữ liệu được bởi file {upload_filename}, được upload bởi {user.username}."
        else:
            note_val = str(note_val_raw).strip()

        status = "valid" if not errors else "invalid"
        if not errors:
            seen_package.add(raw_code)
            if partner_pkg_code:
                seen_partner_pkg.add(partner_pkg_code)
            valid_rows.append(
                {
                    "package_code": raw_code,
                    "folder_type": folder_type_obj,
                    "region": region_obj,
                    "partner": partner_obj,
                    "partner_package_code": partner_pkg_code or None,
                    "created_dt": created_dt,
                    "note": note_val,
                    "creator": creator,
                }
            )

        result_rows.append(
            {
                "package_code": raw_code,
                "package_type": package_type_val,
                "resolved_folder_type_code": resolved_folder_type_code,
                "region_code": region_code,
                "partner_code": partner_code,
                "partner_package_code": partner_pkg_code,
                "created_date": created_date_val.strftime("%Y-%m-%d") if created_date_val else "",
                "note": note_val,
                "username": username_val,
                "used_username": used_creator,
                "status": status,
                "error": "; ".join(errors),
            }
        )

    return result_rows, valid_rows


@login_required
@require_http_methods(["POST"])
def package_bulk_validate(request):
    file = request.FILES.get("file")
    if not file:
        return JsonResponse({"error": "Thiếu file upload."}, status=400)
    if file.size > 30 * 1024 * 1024:
        return JsonResponse({"error": "File vượt quá 30MB."}, status=400)
    try:
        df = pd.read_excel(file, sheet_name="Template")
    except Exception as exc:
        return JsonResponse({"error": f"Lỗi đọc file: {exc}"}, status=400)

    try:
        user_context = get_user_context(request.user)
        result_rows, _ = _validate_bulk_packages(df, request.user, user_context, upload_filename=file.name)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(result_rows).to_excel(writer, sheet_name="Result", index=False)
    output.seek(0)
    resp = HttpResponse(
        output.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = 'attachment; filename="bulk_package_validate_result.xlsx"'
    return resp


@login_required
@require_http_methods(["POST"])
def package_bulk_save(request):
    file = request.FILES.get("file")
    if not file:
        return JsonResponse({"error": "Thiếu file upload."}, status=400)
    if file.size > 30 * 1024 * 1024:
        return JsonResponse({"error": "File vượt quá 30MB."}, status=400)
    try:
        df = pd.read_excel(file, sheet_name="Template")
    except Exception as exc:
        return JsonResponse({"error": f"Lỗi đọc file: {exc}"}, status=400)

    user_context = get_user_context(request.user)
    try:
        result_rows, valid_rows = _validate_bulk_packages(df, request.user, user_context, upload_filename=file.name)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    invalid_count = len([r for r in result_rows if r["status"] == "invalid"])
    if invalid_count > 0:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            pd.DataFrame(result_rows).to_excel(writer, sheet_name="Result", index=False)
        output.seek(0)
        resp = HttpResponse(
            output.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = 'attachment; filename="bulk_package_save_errors.xlsx"'
        return resp

    created = 0
    partner_created = 0
    default_status = PartnerPackageStatus.objects.filter(is_in_warehouse=True).first() or PartnerPackageStatus.objects.first()
    with transaction.atomic():
        for entry in valid_rows:
            package = Package.objects.create(
                package_code=entry["package_code"],
                package_type=entry["folder_type"],
                created_by=entry["creator"],
                region_id=entry["region"],
                created_date=entry["created_dt"],
            )
            created += 1
            if entry["partner"] or entry["partner_package_code"]:
                PartnerPackage.objects.create(
                    package_id=package,
                    partner_package_code=entry["partner_package_code"],
                    partner=entry["partner"],
                    partner_name=entry["partner"].partner_code if entry["partner"] else None,
                    created_date=entry["created_dt"],
                    updated_date=entry["created_dt"],
                    status_id=default_status,
                    created_by=entry["creator"],
                )
                partner_created += 1
    return JsonResponse(
        {
            "success": True,
            "created_packages": created,
            "created_partnerpackages": partner_created,
        }
    )

# Tạo thùng nhiều từ file Excel
@login_required
def import_packages_view(request):
    if request.method == 'POST' and request.FILES.get('filePackage'):
        excel_file = request.FILES['filePackage']
        try:
            df = pd.read_excel(excel_file)
            user_created = request.user
            partners_qs = Partner.objects.filter(is_active=True)
            partners_require_selection = partners_qs.filter(require_partner_selection=True).exists()
            with transaction.atomic():
                for index, row in df.iterrows():
                    new_package_code_raw = row['newPackageCode']
                    old_package_code = row['oldPackageCode']
                    partner_package_code = row['partnerPackageCode']
                    partner_name_value = row['partnerName']
                    package_type_name = row['packageType']
                    partner_package_status = row['partnerPackageStatus']
                    package_region = row['packageRegion']
                    if pd.isna(new_package_code_raw):
                        raise transaction.TransactionManagementError("Missing package code in import file.")
                    new_package_code = str(new_package_code_raw).strip()
                    partner_package_code_value = None if pd.isna(partner_package_code) or str(partner_package_code).strip() == '' else str(partner_package_code).strip()
                    partner_name_value = None if pd.isna(partner_name_value) or str(partner_name_value).strip() == '' else str(partner_name_value).strip()
                   
                    # Validate package type by matching with FolderType's package_type
                    try:
                        package_type = FolderType.objects.get(package_type=package_type_name)
                    except FolderType.DoesNotExist:
                        messages.error(request, f"Loại thùng hàng '{package_type_name}' không tồn tại.")
                        raise transaction.TransactionManagementError(f"Loại thùng hàng '{package_type_name}' không tồn tại.")
            
                    # Validate package code
                    validation_result = validate_package_code(new_package_code, user_created)
                    if not validation_result['is_valid']:
                        messages.error(request, validation_result['error'])
                        raise transaction.TransactionManagementError(validation_result['error'])
                    # Create or update Package
                    package, created = Package.objects.update_or_create(
                        package_code=new_package_code,
                        package_type= package_type,
                        created_by= user_created,
                        package_code_old= old_package_code,
                        updated_date= timezone.now(),
                        region_id= Region.objects.get(region_code = package_region )
                    )
                    # Create or update PartnerPackage
                    partner_instance = None
                    if partner_name_value:
                        partner_instance = partners_qs.filter(partner_code__iexact=partner_name_value).first()
                        if not partner_instance:
                            partner_instance = partners_qs.filter(partner_name__iexact=partner_name_value).first()
                    if not partner_instance and partners_require_selection and partners_qs.exists():
                        raise transaction.TransactionManagementError(f"Vui lòng cấu hình và chọn đối tác hợp lệ cho thùng {new_package_code}.")
                    if partner_instance and partner_instance.require_partner_code and not partner_package_code_value:
                        raise transaction.TransactionManagementError(f"Đối tác {partner_instance.partner_name} yêu cầu mã thùng đối tác cho thùng {new_package_code}.")
                    if partner_package_code_value and PartnerPackage.objects.exclude(package_id=package).filter(partner_package_code=partner_package_code_value).exists():
                        raise transaction.TransactionManagementError(f"Mã thùng đối tác {partner_package_code_value} đã tồn tại.")
                    if partner_instance or partner_package_code_value:
                        if partner_package_status: 
                            status = PartnerPackageStatus.objects.get(status_id=partner_package_status)  
                        else: 
                            status = PartnerPackageStatus.objects.get(status_id=1)  # Assuming status_id=1 is the default
                        PartnerPackage.objects.update_or_create(
                            package_id=package,
                            defaults={
                                'partner_package_code': partner_package_code_value,
                                'partner_name': partner_instance.partner_code if partner_instance else partner_name_value,
                                'partner': partner_instance,
                                'created_date': timezone.now(),
                                'created_by': request.user,
                                'status_id': status,
                                'updated_date': timezone.now(),
                            }
                        )        
            messages.success(request, "Tải lên và xử lý dữ liệu thành công.")
            return redirect('package_management_view')
        except Exception as e:
            messages.error(request, f"Đã xảy ra lỗi trong quá trình tải lên: {e}")
            # Rollback will happen automatically due to atomic
    return redirect('package_management')

#---------------DASHBOARD-------------------------

@login_required
def documents_dashboard (request):
     # Get user context from the utility function
    user = request.user
    user_context = get_user_context(user)
    if not user_context.get("is_admin"):
        messages.error(request, "Bạn không có quyền truy cập dashboard.")
        return redirect("home")

    # Thời gian lọc
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    checker_user_id = request.GET.get("checker_user")
    heatmap_mode = request.GET.get("heatmap_mode", "hour")

    start_date, end_date = parse_dates(start_date_str, end_date_str)
    metrics = get_dashboard_metrics(start_date, end_date, checker_user_id, heatmap_mode)

    context = {
        **user_context,
        "user": user,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "approved_contracts": metrics["approved_contracts"],
        "first_time_contracts": metrics["first_time_contracts"],
        "checker_user_id": checker_user_id or "",
        "drop_checkers": metrics["drop_checkers"],
        "heatmap_list": metrics["heatmap_list"],
        "ranking": metrics["ranking"],
        "heatmap_mode": heatmap_mode,
    }
    return render(request, 'app_documents/app_dashboard.html', context)

@login_required
def folder_received_dashboard(request):
    user = request.user
    user_context = get_user_context(user)
    if not user_context.get("is_admin"):
        messages.error(request, "Bạn không có quyền truy cập báo cáo này.")
        return redirect("home")

    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    start_date, end_date = parse_dates(start_date_str, end_date_str)
    metrics = get_folder_received_metrics(start_date, end_date)

    context = {
        **user_context,
        "user": user,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "folder_received_count": metrics["folder_received_count"],
    }
    return render(request, "app_documents/app_dashboard_folder.html", context)


@login_required
def document_kpi_dashboard_v2(request):
    user = request.user
    user_context = get_user_context(user)
    if not user_context.get("is_admin"):
        messages.error(request, "Bạn không có quyền truy cập dashboard.")
        return redirect("home")

    tab = request.GET.get("tab", "receive")
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    month_str = request.GET.get("month")
    folder_type_id = request.GET.get("folder_type_id")

    kpi_defaults = [
        {"code": "on_time_rate", "name": "KPI nhận đúng hạn", "target_rate": 90.0},
        {"code": "late_rate", "name": "KPI nhận trễ hạn", "target_rate": 90.0},
        {"code": "not_received_rate", "name": "KPI chưa nhận", "target_rate": 90.0},
    ]
    default_codes = [item["code"] for item in kpi_defaults]
    settings_by_code = {
        item.metric_code: item
        for item in DocumentKpiSetting.objects.filter(metric_code__in=default_codes)
    }
    for item in kpi_defaults:
        setting = settings_by_code.get(item["code"])
        if not setting:
            setting = DocumentKpiSetting.objects.create(
                metric_code=item["code"],
                metric_name=item["name"],
                target_rate=item["target_rate"],
                updated_by=user,
            )
            settings_by_code[item["code"]] = setting
        elif not setting.metric_name:
            setting.metric_name = item["name"]
            setting.updated_by = user
            setting.save(update_fields=["metric_name", "updated_by"])

    if request.method == "POST" and tab == "config":
        action = request.POST.get("action")
        if action == "update_kpi":
            for setting in DocumentKpiSetting.objects.filter(metric_code__in=default_codes):
                raw_value = request.POST.get(f"target_rate_{setting.metric_code}")
                if raw_value is None:
                    continue
                try:
                    new_rate = float(raw_value)
                except (TypeError, ValueError):
                    continue
                if new_rate != float(setting.target_rate):
                    setting.target_rate = new_rate
                    setting.updated_by = user
                    setting.save(update_fields=["target_rate", "updated_by", "updated_at"])
            messages.success(request, "Đã cập nhật KPI.")
        return redirect(f"{reverse('document_kpi_v2')}?tab=config")

    kpi_settings = [settings_by_code[code] for code in default_codes if code in settings_by_code]
    kpi_targets = {
        setting.metric_code: float(setting.target_rate)
        for setting in kpi_settings
        if setting.is_active
    }
    for item in kpi_defaults:
        kpi_targets.setdefault(item["code"], item["target_rate"])
    kpi_labels = {item["code"]: item["name"] for item in kpi_defaults}
    kpi_on_time_warn = max(kpi_targets.get("on_time_rate", 90.0) - 5, 0)

    today = timezone.now().date()
    if month_str:
        try:
            year, month = [int(part) for part in month_str.split("-")]
            last_day = calendar.monthrange(year, month)[1]
            start_date = datetime(year, month, 1).date()
            end_date = datetime(year, month, last_day).date()
        except (ValueError, IndexError):
            start_date, end_date = parse_dates(start_date_str, end_date_str)
    else:
        start_date, end_date = parse_dates(start_date_str, end_date_str)

    start_date = start_date or today.replace(day=1)
    end_date = end_date or today

    base_qs = Folder.objects.select_related('shop_id', 'shop_id__region_id', 'folder_type_id', 'folder_status_id').filter(
        folder_created_date__range=[start_date, end_date]
    )
    if folder_type_id and folder_type_id.isdigit():
        base_qs = base_qs.filter(folder_type_id=folder_type_id)

    receiving_qs = base_qs.filter(is_original=True, is_issue=True)
    on_time_count = receiving_qs.filter(is_on_time=True).count()
    late_count = receiving_qs.filter(is_late=True).count()
    received_count = receiving_qs.filter(folder_status_id__is_received=True).count()
    not_received_issue_original_count = receiving_qs.filter(
        folder_status_id__is_not_received_yet=True
    ).count()
    total_count = received_count + not_received_issue_original_count
    base_total_count = base_qs.count()
    total_original_count = base_qs.filter(is_original=True).count()
    total_issue_count = base_qs.filter(is_issue=True).count()

    def safe_rate(part, total):
        return round((part / total) * 100, 2) if total else 0.0

    on_time_rate_all = safe_rate(on_time_count, received_count)
    late_rate_all = safe_rate(late_count, received_count)
    issue_original_total = total_count
    not_received_rate_all = safe_rate(not_received_issue_original_count, issue_original_total)
    original_rate_all = safe_rate(total_original_count, base_total_count)
    issue_rate_all = safe_rate(total_issue_count, base_total_count)

    ratio_qs = receiving_qs
    ratio_denominator = ratio_qs.filter(lastest_received_date__isnull=False).count()
    ratio_numerator = ratio_qs.filter(is_on_time=True).count()
    ratio_percent = round((ratio_numerator / ratio_denominator) * 100, 2) if ratio_denominator else 0.0

    by_shop = receiving_qs.values('shop_id__shop_name').annotate(
        total=Count('folder_id'),
        on_time=Count('folder_id', filter=Q(is_on_time=True)),
        late=Count('folder_id', filter=Q(is_late=True)),
        not_received=Count('folder_id', filter=Q(folder_status_id__is_not_received_yet=True) | Q(lastest_received_date__isnull=True)),
    ).order_by('-total')

    shop_rows = []
    for row in by_shop:
        total = row['total'] or 0
        on_time = row['on_time'] or 0
        ratio = round((on_time / total) * 100, 2) if total else 0.0
        late_rate = round(((row['late'] or 0) / total) * 100, 2) if total else 0.0
        not_received_rate = round(((row['not_received'] or 0) / total) * 100, 2) if total else 0.0
        shop_rows.append({
            'shop_name': row['shop_id__shop_name'] or 'Không xác định',
            'total': total,
            'on_time': on_time,
            'late': row['late'] or 0,
            'not_received': row['not_received'] or 0,
            'ratio': ratio,
            'on_time_rate': ratio,
            'late_rate': late_rate,
            'not_received_rate': not_received_rate,
        })
    shops_top = sorted(shop_rows, key=lambda x: (-x['ratio'], -x['total']))[:10]
    shops_bottom = sorted(shop_rows, key=lambda x: (x['ratio'], x['total']))[:10]
    shops_combined = []
    shop_seen = set()
    for row in shops_top + shops_bottom:
        if row['shop_name'] in shop_seen:
            continue
        shop_seen.add(row['shop_name'])
        shops_combined.append(row)

    by_region_manager = receiving_qs.values(
        'manager_id__regionManager__regionManager_id',
        'manager_id__regionManager__regionManager_name',
        'manager_id__regionManager__regionManager_code',
    ).annotate(
        total=Count('folder_id'),
        on_time=Count('folder_id', filter=Q(is_on_time=True)),
        late=Count('folder_id', filter=Q(is_late=True)),
        not_received=Count('folder_id', filter=Q(folder_status_id__is_not_received_yet=True) | Q(lastest_received_date__isnull=True)),
    ).order_by('-total')

    region_map = {}
    area_lookup = {}
    for row in by_region_manager:
        total = row['total'] or 0
        on_time = row['on_time'] or 0
        ratio = round((on_time / total) * 100, 2) if total else 0.0
        region_id = row['manager_id__regionManager__regionManager_id'] or 'none'
        region_map[region_id] = {
            'id': region_id,
            'name': row['manager_id__regionManager__regionManager_name'] or 'Chưa phân vùng',
            'code': row['manager_id__regionManager__regionManager_code'] or '',
            'total': total,
            'on_time': on_time,
            'late': row['late'] or 0,
            'not_received': row['not_received'] or 0,
            'ratio': ratio,
            'areas': [],
        }

    by_area_manager = receiving_qs.values(
        'manager_id__regionManager__regionManager_id',
        'manager_id__regionManager__regionManager_name',
        'manager_id__regionManager__regionManager_code',
        'manager_id__areaManager__areaManager_id',
        'manager_id__areaManager__areaManager_name',
        'manager_id__areaManager__areaManager_code',
    ).annotate(
        total=Count('folder_id'),
        on_time=Count('folder_id', filter=Q(is_on_time=True)),
        late=Count('folder_id', filter=Q(is_late=True)),
        not_received=Count('folder_id', filter=Q(folder_status_id__is_not_received_yet=True) | Q(lastest_received_date__isnull=True)),
    ).order_by('-total')

    for row in by_area_manager:
        total = row['total'] or 0
        on_time = row['on_time'] or 0
        ratio = round((on_time / total) * 100, 2) if total else 0.0
        region_id = row['manager_id__regionManager__regionManager_id'] or 'none'
        area_id = row['manager_id__areaManager__areaManager_id'] or ''
        if region_id not in region_map:
            region_map[region_id] = {
                'id': region_id,
                'name': row['manager_id__regionManager__regionManager_name'] or 'Chưa phân vùng',
                'code': row['manager_id__regionManager__regionManager_code'] or '',
                'total': 0,
                'on_time': 0,
                'late': 0,
                'not_received': 0,
                'ratio': 0.0,
                'areas': [],
            }
        area_entry = {
            'id': area_id,
            'uid': f"{region_id}_{area_id or 'none'}",
            'name': row['manager_id__areaManager__areaManager_name'] or 'Chưa phân khu vực',
            'code': row['manager_id__areaManager__areaManager_code'] or '',
            'total': total,
            'on_time': on_time,
            'late': row['late'] or 0,
            'not_received': row['not_received'] or 0,
            'ratio': ratio,
            'shops': [],
        }
        region_map[region_id]['areas'].append(area_entry)
        area_lookup[(region_id, area_id)] = area_entry

    by_shop_area = receiving_qs.values(
        'manager_id__regionManager__regionManager_id',
        'manager_id__areaManager__areaManager_id',
        'shop_id',
        'shop_id__shop_name',
        'shop_id__shop_code',
    ).annotate(
        total=Count('folder_id'),
        on_time=Count('folder_id', filter=Q(is_on_time=True)),
        late=Count('folder_id', filter=Q(is_late=True)),
        not_received=Count('folder_id', filter=Q(folder_status_id__is_not_received_yet=True) | Q(lastest_received_date__isnull=True)),
    ).order_by('-total')

    for row in by_shop_area:
        total = row['total'] or 0
        on_time = row['on_time'] or 0
        late = row['late'] or 0
        not_received = row['not_received'] or 0
        ratio = round((on_time / total) * 100, 2) if total else 0.0
        late_rate = round((late / total) * 100, 2) if total else 0.0
        not_received_rate = round((not_received / total) * 100, 2) if total else 0.0
        region_id = row['manager_id__regionManager__regionManager_id'] or 'none'
        area_id = row['manager_id__areaManager__areaManager_id'] or ''
        if region_id not in region_map:
            region_map[region_id] = {
                'id': region_id,
                'name': 'Chưa phân vùng',
                'code': '',
                'total': 0,
                'on_time': 0,
                'late': 0,
                'not_received': 0,
                'ratio': 0.0,
                'areas': [],
            }
        area_entry = area_lookup.get((region_id, area_id))
        if not area_entry:
            area_entry = {
                'id': area_id,
                'uid': f"{region_id}_{area_id or 'none'}",
                'name': 'Chưa phân khu vực',
                'code': '',
                'total': 0,
                'on_time': 0,
                'late': 0,
                'not_received': 0,
                'ratio': 0.0,
                'shops': [],
            }
            region_map[region_id]['areas'].append(area_entry)
            area_lookup[(region_id, area_id)] = area_entry
        area_entry['shops'].append({
            'id': row['shop_id'],
            'name': row['shop_id__shop_name'] or 'Không xác định',
            'code': row['shop_id__shop_code'] or '',
            'total': total,
            'on_time': on_time,
            'late': late,
            'not_received': not_received,
            'on_time_rate': ratio,
            'late_rate': late_rate,
            'not_received_rate': not_received_rate,
        })

    for area_entry in area_lookup.values():
        area_entry['shops'] = sorted(area_entry['shops'], key=lambda x: (-x['total'], x['name']))

    for region in region_map.values():
        region['areas'] = sorted(region['areas'], key=lambda x: (x['ratio'], -x['total'], x['name']))
    region_area_rows = sorted(region_map.values(), key=lambda x: (x['ratio'], -x['total'], x['name']))

    by_month = receiving_qs.annotate(month=TruncMonth('folder_created_date')).values('month').annotate(
        total=Count('folder_id'),
        on_time=Count('folder_id', filter=Q(is_on_time=True)),
        late=Count('folder_id', filter=Q(is_late=True)),
        not_received=Count('folder_id', filter=Q(folder_status_id__is_not_received_yet=True) | Q(lastest_received_date__isnull=True)),
    ).order_by('month')

    month_rows = []
    month_chart_rows = []
    prev_month = None
    def change_pct(current, previous):
        if previous in (None, 0):
            return None
        return round(((current - previous) / previous) * 100, 2)
    for row in by_month:
        label = row['month'].strftime('%Y-%m') if row['month'] else ''
        total = row['total'] or 0
        on_time = row['on_time'] or 0
        late = row['late'] or 0
        not_received = row['not_received'] or 0
        month_rows.append({
            'month': label,
            'total': total,
            'on_time': on_time,
            'late': late,
            'not_received': not_received,
            'total_change_pct': change_pct(total, prev_month['total'] if prev_month else None),
            'on_time_change_pct': change_pct(on_time, prev_month['on_time'] if prev_month else None),
            'late_change_pct': change_pct(late, prev_month['late'] if prev_month else None),
            'not_received_change_pct': change_pct(not_received, prev_month['not_received'] if prev_month else None),
        })
        prev_month = {
            'total': total,
            'on_time': on_time,
            'late': late,
            'not_received': not_received,
        }
        if total:
            month_chart_rows.append({
                'month': label,
                'on_time_rate': round((on_time / total) * 100, 2),
                'late_rate': round((late / total) * 100, 2),
                'not_received_rate': round((not_received / total) * 100, 2),
            })
        else:
            month_chart_rows.append({
                'month': label,
                'on_time_rate': 0.0,
                'late_rate': 0.0,
                'not_received_rate': 0.0,
            })

    context = {
        **user_context,
        'user': user,
        'active_tab': tab,
        'tab_qs': urlencode({k: v for k, v in request.GET.items() if k != 'tab'}),
        'start_date': start_date.strftime("%Y-%m-%d"),
        'end_date': end_date.strftime("%Y-%m-%d"),
        'month': month_str or '',
        'folder_type_id': folder_type_id or '',
        'filter_folder_types': FolderType.objects.filter(is_valid=True).order_by('folder_type_name'),
        'kpi_settings': kpi_settings,
        'kpi_targets': kpi_targets,
        'kpi_labels': kpi_labels,
        'kpi_on_time_warn': kpi_on_time_warn,
        'on_time_count': on_time_count,
        'late_count': late_count,
        'not_received_count': not_received_issue_original_count,
        'total_count': total_count,
        'received_count': received_count,
        'issue_original_total': issue_original_total,
        'ratio_percent': ratio_percent,
        'ratio_numerator': ratio_numerator,
        'ratio_denominator': ratio_denominator,
        'shops_breakdown': shops_combined,
        'region_area_breakdown': region_area_rows,
        'months_breakdown': month_rows,
        'months_chart_json': json.dumps(month_chart_rows, cls=DjangoJSONEncoder, ensure_ascii=False),
        'total_original_count': total_original_count,
        'total_issue_count': total_issue_count,
        'on_time_rate_all': on_time_rate_all,
        'late_rate_all': late_rate_all,
        'not_received_rate_all': not_received_rate_all,
        'original_rate_all': original_rate_all,
        'issue_rate_all': issue_rate_all,
    }
    return render(request, "app_documents/app_document_kpi_v2.html", context)

@login_required
def export_kpi_shop_detail(request):
    user = request.user
    user_context = get_user_context(user)
    if not user_context.get("is_admin"):
        messages.error(request, "Bạn không có quyền truy cập dữ liệu.")
        return redirect("home")

    shop_id = request.GET.get("shop_id")
    if not shop_id or not shop_id.isdigit():
        messages.error(request, "Thiếu phòng giao dịch.")
        return redirect("document_kpi_v2")

    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    month_str = request.GET.get("month")
    folder_type_id = request.GET.get("folder_type_id")

    today = timezone.now().date()
    if month_str:
        try:
            year, month = [int(part) for part in month_str.split("-")]
            last_day = calendar.monthrange(year, month)[1]
            start_date = datetime(year, month, 1).date()
            end_date = datetime(year, month, last_day).date()
        except (ValueError, IndexError):
            start_date, end_date = parse_dates(start_date_str, end_date_str)
    else:
        start_date, end_date = parse_dates(start_date_str, end_date_str)

    start_date = start_date or today.replace(day=1)
    end_date = end_date or today

    qs = Folder.objects.select_related(
        'shop_id',
        'folder_type_id',
        'folder_status_id',
        'manager_id__regionManager',
        'manager_id__areaManager',
    ).filter(
        shop_id=shop_id,
        is_original=True,
        is_issue=True,
        folder_created_date__range=[start_date, end_date],
    ).order_by('folder_created_date')

    if folder_type_id and folder_type_id.isdigit():
        qs = qs.filter(folder_type_id=folder_type_id)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    filename = f"pgd_detail_{shop_id}_{start_date}_{end_date}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")

    writer = csv.writer(response)
    writer.writerow([
        "Phòng giao dịch",
        "Ngày phát sinh quyển",
        "Loại quyển",
        "Tình trạng đúng hạn",
        "Tình trạng trễ hạn",
        "Tình trạng chưa nhận",
        "Ngày nhận (nếu có)",
        "Khu vực",
        "Vùng",
    ])

    for folder in qs.iterator():
        shop_name = folder.shop_id.shop_name if folder.shop_id else "Không xác định"
        folder_type = folder.folder_type_id.folder_type_name if folder.folder_type_id else ""
        on_time = "Có" if folder.is_on_time else "Không"
        late = "Có" if folder.is_late else "Không"
        not_received = "Có" if folder.folder_status_id and folder.folder_status_id.is_not_received_yet else "Không"
        received_date = folder.lastest_received_date.date().isoformat() if folder.lastest_received_date else ""
        area_name = ""
        region_name = ""
        if folder.manager_id:
            if folder.manager_id.areaManager:
                area_name = folder.manager_id.areaManager.areaManager_name or ""
            if folder.manager_id.regionManager:
                region_name = folder.manager_id.regionManager.regionManager_name or ""
        writer.writerow([
            shop_name,
            folder.folder_created_date.isoformat(),
            folder_type,
            on_time,
            late,
            not_received,
            received_date,
            area_name,
            region_name,
        ])

    return response

@login_required
def gapo_schedule_view(request):
    user = request.user
    user_context = get_user_context(user)
    if not user_context.get("is_admin"):
        messages.error(request, "Bạn không có quyền truy cập tính năng này.")
        return redirect("home")

    if request.method == "POST" and request.POST.get("action"):
        action = request.POST.get("action")
        schedule_id = request.POST.get("schedule_id")
        try:
            schedule = GapoScheduledMessage.objects.get(pk=schedule_id)
        except GapoScheduledMessage.DoesNotExist:
            messages.error(request, "Không tìm thấy lịch gửi.")
            return redirect("gapo_schedule")
        now = timezone.now()
        if action == "retry":
            schedule.status = GapoScheduledMessage.Status.PENDING
            schedule.last_error = None
            schedule.save(update_fields=["status", "last_error", "updated_at"])
            eta = schedule.schedule_at if schedule.schedule_at > now else None
            send_gapo_scheduled_message.apply_async(args=[schedule.id], eta=eta)
            messages.success(request, "Đã retry lịch gửi.")
        elif action == "resend_now":
            schedule.status = GapoScheduledMessage.Status.PENDING
            schedule.last_error = None
            schedule.schedule_at = now
            schedule.save(update_fields=["status", "last_error", "schedule_at", "updated_at"])
            send_gapo_scheduled_message.apply_async(args=[schedule.id])
            messages.success(request, "Đã gửi lại ngay.")
        else:
            messages.error(request, "Hành động không hợp lệ.")
        return redirect("gapo_schedule")

    if request.method == "POST" and not request.POST.get("action"):
        form = GapoScheduleForm(request.POST)
        if form.is_valid():
            schedule = form.save(commit=False)
            schedule.created_by = user
            schedule.save()
            send_gapo_scheduled_message.apply_async(args=[schedule.id], eta=schedule.schedule_at)
            messages.success(request, "Đã lên lịch gửi tin GAPO.")
            return redirect("gapo_schedule")
    else:
        form = GapoScheduleForm()

    schedules = GapoScheduledMessage.objects.order_by("-created_at")[:20]
    context = {
        **user_context,
        "user": user,
        "form": form,
        "schedules": schedules,
    }
    return render(request, "app_documents/app_gapo_schedule.html", context)


@login_required
@require_http_methods(["POST"])
def gapo_ai_generate_view(request):
    user_context = get_user_context(request.user)
    if not user_context.get("is_admin"):
        return JsonResponse({"error": "Bạn không có quyền sử dụng AI soạn tin nhắn."}, status=403)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        payload = {}
    base_text = (payload.get("text") or "").strip()
    style = (payload.get("style") or "formal").strip()

    if not base_text:
        return JsonResponse({"error": "Vui lòng nhập nội dung gốc để AI xử lý."}, status=400)

    api_key = getattr(settings, "GEMINI_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return JsonResponse({"error": "Chưa cấu hình khóa API cho AI."}, status=500)

    hint = AI_STYLE_HINTS.get(style, "")
    prompt = f"{hint}\nYêu cầu: viết tin nhắn ngắn gọn, rõ ràng bằng tiếng Việt dựa trên nội dung: \"{base_text}\". Trả về đúng phần nội dung tin nhắn."
    request_body = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        resp = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
            headers={"Content-Type": "application/json", "X-goog-api-key": api_key},
            json=request_body,
            timeout=10,
        )
        resp.raise_for_status()
        candidates = resp.json().get("candidates", [])
        draft = ""
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            draft = "".join(part.get("text", "") for part in parts)
        if not draft:
            return JsonResponse({"error": "AI không trả về nội dung. Thử lại sau."}, status=502)
        return JsonResponse({"draft": draft})
    except requests.RequestException as exc:
        logger.error("GAPO AI draft failed", exc_info=exc)
        return JsonResponse({"error": "Gọi AI thất bại. Vui lòng thử lại."}, status=502)

def export_excel_folder_fail(request):
    documents_created_date = request.GET.get('filterfoldermonth', None) 
    # Split mm.YYYY into YYYYmm 
    documents_created_date_month, documents_created_date_year = str(documents_created_date).split(".")
    folder_month = documents_created_date_year+documents_created_date_month
    
    if documents_created_date is None:
        return JsonResponse({'error': 'Missing documents_created_date parameter'}, status=400)
    
    query = f'''WITH folder_fail AS ( 
        SELECT 
            folder_code,
            folder_id,
            folder_created_date,
            qlkv_name,
            qlv_name,
            shop_name,
            foltype.folder_type_name,
            region.region_name
        FROM "f_FolderDetail" folder
        LEFT JOIN "d_Shops" shop ON shop.shop_id = folder.shop_id
        LEFT JOIN "d_Manager" man ON man.manager_id = folder.manager_id 
        LEFT JOIN "d_FolderType" foltype ON foltype.folder_type_id = folder.folder_type_id 
        LEFT JOIN "d_Region" region ON region.region_id = shop.region_id
        WHERE 
            folder.is_issue = true 
            AND folder.is_original = true 
            AND to_char(folder_created_date, 'yyyymm') = '{folder_month}' 
            AND lastest_received_date IS NULL 
    )
    SELECT 
        folder_fail.*,
        loan.loan_code,
        loan.customer_code,
        loan.customer_name,
        loan.employee_code,
        loan.employee_name,
        doctype.document_type_name,
        bus.business_type_name
    FROM "f_DocumentsDetail" doc 
    RIGHT JOIN folder_fail ON doc.folder_id = folder_fail.folder_id
    LEFT JOIN "d_DocumentType" doctype ON doctype.document_type_id = doc.document_type_id 
    LEFT JOIN "d_LoanDetail" loan ON loan.loan_id = doc.loan_id 
    LEFT JOIN "d_BusinessType" bus ON bus.business_type_id = doc.business_type_id 
    WHERE to_char(doc.documents_created_date, 'yyyymm') = '{folder_month}' '''
    with connection.cursor() as cursor:
        cursor.execute(query)
        columns = [col[0] for col in cursor.description]
        results = cursor.fetchall()

    if not results:
        return JsonResponse({'error': 'No data found for the given date'}, status=404)
        
    # Create an Excel workbook and add a worksheet
    wb = Workbook()
    ws = wb.active
    ws.title = "Folder Fail Data"
    
    # Write column headers
    for col_num, column_title in enumerate(columns, 1):
        cell = ws.cell(row=1, column=col_num)
        cell.value = column_title
    
    # Write data rows
    for row_num, row_data in enumerate(results, 2):
        for col_num, cell_value in enumerate(row_data, 1):
            cell = ws.cell(row=row_num, column=col_num)
            cell.value = cell_value
    
    # Create a response object
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename=folder_fail_data_{folder_month}.xlsx'
    
    # Save the workbook to the response
    wb.save(response)
    
    return response

@login_required
def historical_folder_view(request):
    user = request.user
    user_context = get_user_context(user)
   
    if not user_context['is_admin'] and not user_context['is_checker']:
        return redirect('home')
    filters = {}
    # Lấy giá trị từ các bộ lọc
    choice_shop = request.GET.get('choice_shop')
    choice_folder_code = request.GET.get('choice_folder_code')
    choice_folder_type = request.GET.get('choice_folder_type')
    choice_folder_status = request.GET.get('choice_folder_status')
    filter_package = request.GET.get('filter_package')
    # Áp dụng các bộ lọc nếu có
    if choice_shop:
        filters['shop_id__shop_name__icontains'] = choice_shop
    if choice_folder_code:
        filters['folder_code__icontains'] = choice_folder_code
    if choice_folder_type:
        filters['folder_type_id'] = choice_folder_type
    if choice_folder_status:
        filters['folder_status_id'] = choice_folder_status
    if filter_package:
        filters['package_id__package_code__icontains'] = filter_package

    # Lọc dữ liệu từ HistoricalFolder theo các bộ lọc
    folder_detail = HistoricalFolder.objects.filter(**filters).order_by('folder_created_date')
    # Phân trang kết quả
    paginator = Paginator(folder_detail, 50)
    page_number = request.GET.get('page')
    folder_detail = paginator.get_page(page_number)
    # Chuẩn bị các dữ liệu cho template
    context = {
        **user_context,
        'user': user,
        'folder_detail': folder_detail,
        'drop_list_shops': Shop.objects.all(),
        'drop_list_folder_type': FolderType.objects.all(),
        'drop_list_folder_status': FolderStatus.objects.all(),
    }
    return render(request, 'app_documents/app_historical_folder.html', context)

@login_required
def historical_documents_view(request):
    user = request.user
    user_context = get_user_context(user)
   
    if not user_context['is_admin'] and not user_context['is_checker']:
        return redirect('home')
    
    filters = {}
    # Lấy giá trị từ các bộ lọc
    choice_shop = request.GET.get('choice_shop')
    choice_documents_code = request.GET.get('choice_documents_code')
    choice_document_type = request.GET.get('choice_document_type')
    choice_business_type = request.GET.get('choice_business_type')
    filter_package = request.GET.get('filter_package')
    
    # Áp dụng các bộ lọc nếu có
    if choice_shop:
        filters['shop_id__shop_name__icontains'] = choice_shop
    if choice_documents_code:
        filters['documents_code__icontains'] = choice_documents_code
    if choice_document_type:
        filters['document_type_name__icontains'] = choice_document_type
    if choice_business_type:
        filters['business_type_name__icontains'] = choice_business_type
    if filter_package:
        filters['package_id__package_code__icontains'] = filter_package

    # Lọc dữ liệu từ HistoricalDocuments theo các bộ lọc
    documents_detail = HistoricalDocuments.objects.filter(**filters).order_by('archived_at')
    
    # Phân trang kết quả
    paginator = Paginator(documents_detail, 50)
    page_number = request.GET.get('page')
    documents_detail = paginator.get_page(page_number)
    
    # Chuẩn bị các dữ liệu cho template
    context = {
        **user_context,
        'user': user,
        'documents_detail': documents_detail,
        'drop_list_shops': Shop.objects.all(),
        'drop_list_document_type': DocumentType.objects.all(),
        'drop_list_business_type': BusinessType.objects.all(),
    }
    return render(request, 'app_documents/app_historical_document.html', context)

# Yêu cầu thay đổi các quyển chứng từ nhận sai
@login_required
def request_change_folder_view(request, folder_id):
    """Người dùng đề xuất thay đổi thông tin của Folder"""
    if request.method == 'POST':
        folder = Folder.objects.get(folder_id=folder_id)
        if not folder:
            return JsonResponse({'success': False, 'message': 'Không tìm thấy quyển chứng từ.'})
        note = request.POST.get('note', '')
        # Tạo bản ghi yêu cầu thay đổi cho folder
        ChangeRequest.objects.create(
            folder=folder,
            user=request.user,
            request_type='folder',
            note=note
        )
        return JsonResponse({'success': True, 'message': 'Đã gửi đề xuất thay đổi cho admin.'})
    return JsonResponse({'success': False, 'message': 'Invalid request.'})

# Yêu cầu thay đổi các chứng từ duyệt sai
@login_required
def request_change_document_view(request, document_id):
    """Người dùng đề xuất thay đổi thông tin của DocumentsDetail"""
    if request.method == 'POST':
        document = DocumentsDetail.objects.get(documents_id=document_id)
        if not document:
            return JsonResponse({'success': False, 'message': 'Không tìm thấy chứng từ.'})
        note = request.POST.get('note', '')
        # Tạo bản ghi yêu cầu thay đổi cho document
        ChangeRequest.objects.create(
            document=document,
            user=request.user,
            request_type='document',
            note=note
        )
        return JsonResponse({'success': True, 'message': 'Đã gửi đề xuất thay đổi cho admin.'})
    return JsonResponse({'success': False, 'message': 'Invalid request.'})


# Borrow request helpers
def _borrow_request_log(borrow_request, action, from_status=None, to_status=None, user=None, item=None, note=None, meta=None):
    BorrowRequestLog.objects.create(
        borrow_request=borrow_request,
        item=item,
        action=action,
        from_status=from_status,
        to_status=to_status,
        note=note,
        meta=meta,
        created_by=user,
    )


def _refresh_borrow_request_status(borrow_request):
    items = list(borrow_request.items.all())
    if not items:
        if borrow_request.status != BorrowRequestStatus.PENDING:
            borrow_request.status = BorrowRequestStatus.PENDING
            borrow_request.save(update_fields=['status'])
        return

    statuses = {item.status for item in items}
    if statuses.issubset({BorrowRequestItemStatus.RETURNED, BorrowRequestItemStatus.LOST, BorrowRequestItemStatus.CANCELLED}):
        borrow_request.status = BorrowRequestStatus.RETURNED
    elif BorrowRequestItemStatus.HANDED_OVER in statuses or BorrowRequestItemStatus.RETURNED in statuses or BorrowRequestItemStatus.LOST in statuses:
        if BorrowRequestItemStatus.ASSIGNED in statuses or BorrowRequestItemStatus.PENDING in statuses:
            borrow_request.status = BorrowRequestStatus.PARTIALLY_RETURNED
        else:
            borrow_request.status = BorrowRequestStatus.HANDED_OVER
    elif statuses.issubset({BorrowRequestItemStatus.ASSIGNED, BorrowRequestItemStatus.PENDING}):
        borrow_request.status = BorrowRequestStatus.ASSIGNED
    else:
        borrow_request.status = BorrowRequestStatus.PARTIALLY_RETURNED

    borrow_request.save(update_fields=['status'])


#BORROW
@login_required
def borrow_request_management_v2(request):
    user = request.user
    user_context = get_user_context(user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        return redirect('home')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create':
            borrower_id = request.POST.get('borrower_id')
            reference_code = request.POST.get('reference_code')
            needed_date = request.POST.get('needed_date')
            appointment_date = request.POST.get('appointment_date')
            ticket_code = request.POST.get('ticket_code')
            contact_email = request.POST.get('contact_email')
            contact_phone = request.POST.get('contact_phone')
            note = request.POST.get('note')
            if not borrower_id or not needed_date:
                messages.error(request, 'Vui lòng nhập phòng ban và ngày cần.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            borrower = Shop.objects.filter(shop_id=borrower_id).first()
            if not borrower:
                messages.error(request, 'Không tìm thấy phòng ban.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            try:
                needed_date_value = datetime.strptime(needed_date, "%Y-%m-%d").date()
            except ValueError:
                messages.error(request, 'Ngày cần không hợp lệ.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            appointment_date_value = None
            if appointment_date:
                try:
                    appointment_date_value = datetime.strptime(appointment_date, "%Y-%m-%d").date()
                except ValueError:
                    messages.error(request, 'Ngày hẹn trả không hợp lệ.')
                    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            new_request = BorrowRequest.objects.create(
                borrower=borrower,
                requester=user,
                reference_code=reference_code or None,
                needed_date=needed_date_value,
                appointment_date=appointment_date_value,
                ticket_code=ticket_code or None,
                contact_email=contact_email or None,
                contact_phone=contact_phone or None,
                note=note or None,
                status=BorrowRequestStatus.PENDING,
                created_by=user,
                updated_by=user,
            )
            _borrow_request_log(new_request, 'create', None, BorrowRequestStatus.PENDING, user=user)
            return redirect('borrow_request_detail_v2', request_id=new_request.request_id)

    filters = {}
    choice_borrower = (request.GET.get('borrower') or '').strip()
    choice_status = (request.GET.get('status') or '').strip()
    choice_ticket = (request.GET.get('ticket') or '').strip()
    choice_needed_date = (request.GET.get('needed_date') or '').strip()

    if choice_borrower:
        if choice_borrower.isdigit():
            filters['borrower__shop_id'] = choice_borrower
        else:
            filters['borrower__shop_name__icontains'] = choice_borrower
    if choice_status:
        filters['status'] = choice_status
    if choice_ticket:
        filters['ticket_code__icontains'] = choice_ticket
    if choice_needed_date:
        date_parts = choice_needed_date.split(' to ')
        if len(date_parts) == 2:
            start_date = datetime.strptime(date_parts[0], "%Y-%m-%d").date()
            end_date = datetime.strptime(date_parts[1], "%Y-%m-%d").date()
            filters['needed_date__range'] = [start_date, end_date]
        elif len(date_parts) == 1:
            single_date = datetime.strptime(date_parts[0], "%Y-%m-%d").date()
            filters['needed_date__range'] = [single_date, single_date]

    qs = BorrowRequest.objects.select_related('borrower', 'requester').prefetch_related('items').annotate(items_count=Count('items')).order_by('-created_at')
    if filters:
        qs = qs.filter(**filters)

    paginator = Paginator(qs, 25)
    page_number = request.GET.get('page')
    borrow_requests = paginator.get_page(page_number)
    today = timezone.now().date()
    for req in borrow_requests:
        overdue_count = 0
        for item in req.items.all():
            if item.status in (BorrowRequestItemStatus.RETURNED, BorrowRequestItemStatus.CANCELLED):
                continue
            due_date = item.appointment_date or req.appointment_date
            if due_date and due_date < today:
                overdue_count += 1
        req.overdue_count = overdue_count

    current = borrow_requests.number if borrow_requests else 1
    total_pages = borrow_requests.paginator.num_pages if borrow_requests else 1
    start_range = max(current - 2, 1)
    end_range = min(current + 2, total_pages)
    page_range_custom = list(range(1, min(2, total_pages) + 1))
    page_range_custom += list(range(start_range, end_range + 1))
    page_range_custom += list(range(max(total_pages - 1, 1), total_pages + 1))
    page_range_custom = sorted(set([p for p in page_range_custom if 1 <= p <= total_pages]))

    qs_no_page = request.GET.copy()
    qs_no_page.pop('page', None)
    base_qs = qs_no_page.urlencode()

    context = {
        **user_context,
        'user': user,
        'borrow_requests': borrow_requests,
        'page_range_custom': page_range_custom,
        'base_qs': base_qs,
        'drop_list_shops': Shop.objects.filter(for_borrow_only=True).order_by('shop_name'),
        'drop_list_request_status': BorrowRequestStatus.choices,
        'filters': {
            'borrower': choice_borrower,
            'status': choice_status,
            'ticket': choice_ticket,
            'needed_date': choice_needed_date,
        },
    }
    return render(request, 'app_documents/app_borrow_request_v2.html', context)


@login_required
def borrow_request_detail_v2(request, request_id):
    user = request.user
    user_context = get_user_context(user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        return redirect('home')

    borrow_request = get_object_or_404(BorrowRequest, request_id=request_id)
    items = borrow_request.items.select_related('documents_id', 'legacy_borrowing').order_by('-created_at')
    logs = borrow_request.logs.select_related('created_by', 'item').order_by('-created_at')
    status_labels = dict(BorrowRequestStatus.choices)
    status_flow = [
        BorrowRequestStatus.PENDING,
        BorrowRequestStatus.ASSIGNED,
        BorrowRequestStatus.HANDED_OVER,
        BorrowRequestStatus.PARTIALLY_RETURNED,
        BorrowRequestStatus.RETURNED,
        BorrowRequestStatus.CANCELLED,
        BorrowRequestStatus.REJECTED,
    ]
    logs_by_status = {}
    for log in logs:
        status_key = log.to_status or log.from_status or 'unknown'
        logs_by_status.setdefault(status_key, []).append(log)
    log_steps = []
    for status_code in status_flow:
        if status_code in logs_by_status:
            log_steps.append({
                'code': status_code,
                'label': status_labels.get(status_code, status_code),
                'logs': logs_by_status[status_code],
            })
    for status_code, status_logs in logs_by_status.items():
        if status_code in status_flow:
            continue
        log_steps.append({
            'code': status_code,
            'label': status_labels.get(status_code, status_code),
            'logs': status_logs,
        })
    preview_key = (request.GET.get('preview_key') or '').strip()
    preview_rows = []
    preview_error = None

    if preview_key:
        documents = DocumentsDetail.objects.select_related(
            'shop_id',
            'document_type_id',
            'folder_id',
            'status_id',
            'document_status_id',
            'package_id',
        ).filter(
            Q(loan_id__loan_code__iexact=preview_key) | Q(contract_id__contract_code__iexact=preview_key)
        ).order_by('documents_created_date', 'documents_id')
        if not documents.exists():
            preview_error = 'Không tìm thấy chứng từ theo contract_code hoặc loan_code.'
        else:
            doc_ids = list(documents.values_list('documents_id', flat=True))
            active_borrow_ids = set(
                BorrowingDocument.objects.filter(
                    documents_id__in=doc_ids,
                    borrow_status_id__flag_return=False,
                ).values_list('documents_id', flat=True)
            )
            assigned_ids = set(
                BorrowRequestItem.objects.filter(
                    borrow_request=borrow_request,
                    documents_id__in=doc_ids,
                ).values_list('documents_id', flat=True)
            )
            for doc in documents:
                reasons = []
                doc_status = doc.document_status_id
                if not doc_status or not doc_status.is_checked:
                    reasons.append('Chưa duyệt')
                if doc_status and doc_status.is_borrow:
                    reasons.append('Đang mượn')
                if doc.documents_id in active_borrow_ids:
                    reasons.append('Đang có giao dịch mượn')
                if doc.documents_id in assigned_ids:
                    reasons.append('Đã gán trong yêu cầu')
                preview_rows.append({
                    'doc': doc,
                    'eligible': not reasons,
                    'reason': ', '.join(reasons),
                })

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_item':
            document_code = (request.POST.get('documents_code') or '').strip()
            if not document_code:
                messages.error(request, 'Vui lòng nhập mã chứng từ.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            try:
                document = DocumentsDetail.objects.select_related('document_status_id').get(documents_code=document_code)
            except DocumentsDetail.DoesNotExist:
                messages.error(request, 'Không tìm thấy chứng từ.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            if document.document_status_id and document.document_status_id.is_borrow:
                messages.error(request, 'Chứng từ đang được mượn.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            if document.document_status_id and not document.document_status_id.is_checked:
                messages.error(request, 'Chứng từ chưa ở trạng thái đã duyệt.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            active_borrow = BorrowingDocument.objects.filter(documents_id=document, borrow_status_id__flag_return=False).exists()
            if active_borrow:
                messages.error(request, 'Chứng từ đang có giao dịch mượn.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            item = BorrowRequestItem.objects.create(
                borrow_request=borrow_request,
                documents_id=document,
                appointment_date=borrow_request.appointment_date,
                status=BorrowRequestItemStatus.ASSIGNED,
                created_by=user,
                updated_by=user,
            )
            _borrow_request_log(borrow_request, 'assign_document', borrow_request.status, BorrowRequestStatus.ASSIGNED, user=user, item=item, meta={'documents_id': document.documents_id})
            _refresh_borrow_request_status(borrow_request)
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

        if action == 'assign_selected':
            selected_ids = request.POST.getlist('document_ids')
            if not selected_ids:
                messages.error(request, 'Vui lòng chọn chứng từ để gán.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            documents = DocumentsDetail.objects.select_related(
                'document_status_id',
            ).filter(documents_id__in=selected_ids)
            active_borrow_ids = set(
                BorrowingDocument.objects.filter(
                    documents_id__in=selected_ids,
                    borrow_status_id__flag_return=False,
                ).values_list('documents_id', flat=True)
            )
            existing_ids = set(
                BorrowRequestItem.objects.filter(
                    borrow_request=borrow_request,
                    documents_id__in=selected_ids,
                ).values_list('documents_id', flat=True)
            )
            added_count = 0
            skipped = []
            for doc in documents:
                doc_status = doc.document_status_id
                if doc.documents_id in existing_ids:
                    skipped.append(doc.documents_code)
                    continue
                if not doc_status or not doc_status.is_checked:
                    skipped.append(doc.documents_code)
                    continue
                if doc_status.is_borrow or doc.documents_id in active_borrow_ids:
                    skipped.append(doc.documents_code)
                    continue
                item = BorrowRequestItem.objects.create(
                    borrow_request=borrow_request,
                    documents_id=doc,
                    appointment_date=borrow_request.appointment_date,
                    status=BorrowRequestItemStatus.ASSIGNED,
                    created_by=user,
                    updated_by=user,
                )
                _borrow_request_log(borrow_request, 'assign_document', borrow_request.status, BorrowRequestStatus.ASSIGNED, user=user, item=item, meta={'documents_id': doc.documents_id})
                added_count += 1
            if added_count:
                _refresh_borrow_request_status(borrow_request)
                messages.success(request, f'Đã gán {added_count} chứng từ.')
            if skipped:
                messages.warning(request, f'Bỏ qua {len(skipped)} chứng từ không hợp lệ hoặc đã gán.')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

        if action == 'handover':
            items_to_handover = borrow_request.items.filter(status=BorrowRequestItemStatus.ASSIGNED, documents_id__isnull=False)
            if not items_to_handover.exists():
                messages.error(request, 'Không có chứng từ để bàn giao.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            borrow_status = BorrowingStatus.objects.filter(flag_is_borrowing=True).first()
            if not borrow_status:
                messages.error(request, 'Không tìm thấy trạng thái mượn.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            document_status_borrow = DocumentStatus.objects.filter(is_borrow=True).first()
            if not document_status_borrow:
                messages.error(request, 'Không tìm thấy trạng thái chứng từ đang mượn.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            for item in items_to_handover:
                legacy = BorrowingDocument.objects.create(
                    documents_id=item.documents_id,
                    borrow_date=timezone.now().date(),
                    appointment_date=item.appointment_date or borrow_request.appointment_date,
                    lender=user,
                    borrower=borrow_request.borrower,
                    borrower_detail=None,
                    ticket_code=borrow_request.ticket_code,
                    note=borrow_request.note,
                    borrow_status_id=borrow_status,
                )
                DocumentsDetail.objects.filter(documents_id=item.documents_id.documents_id).update(document_status_id=document_status_borrow)
                item.legacy_borrowing = legacy
                item.status = BorrowRequestItemStatus.HANDED_OVER
                item.handed_over_date = timezone.now()
                item.updated_by = user
                item.save(update_fields=['legacy_borrowing', 'status', 'handed_over_date', 'updated_by', 'updated_at'])
                _borrow_request_log(borrow_request, 'handover', BorrowRequestStatus.ASSIGNED, BorrowRequestStatus.HANDED_OVER, user=user, item=item)
            _refresh_borrow_request_status(borrow_request)
            messages.success(request, 'Đã bàn giao chứng từ.')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

        if action == 'return_item':
            item_id = request.POST.get('item_id')
            item = get_object_or_404(BorrowRequestItem, item_id=item_id, borrow_request=borrow_request)
            return_status = BorrowingStatus.objects.filter(flag_return=True).first()
            checked_status = DocumentStatus.objects.filter(is_checked=True).first()
            if item.legacy_borrowing and return_status:
                item.legacy_borrowing.borrow_status_id = return_status
                item.legacy_borrowing.return_date = timezone.now().date()
                item.legacy_borrowing.save(update_fields=['borrow_status_id', 'return_date'])
            if item.documents_id and checked_status:
                DocumentsDetail.objects.filter(documents_id=item.documents_id.documents_id).update(document_status_id=checked_status)
            item.status = BorrowRequestItemStatus.RETURNED
            item.return_date = timezone.now()
            item.updated_by = user
            item.save(update_fields=['status', 'return_date', 'updated_by', 'updated_at'])
            _borrow_request_log(borrow_request, 'return', BorrowRequestStatus.HANDED_OVER, BorrowRequestStatus.RETURNED, user=user, item=item)
            _refresh_borrow_request_status(borrow_request)
            messages.success(request, 'Đã hoàn trả chứng từ.')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

        if action == 'lost_item':
            item_id = request.POST.get('item_id')
            item = get_object_or_404(BorrowRequestItem, item_id=item_id, borrow_request=borrow_request)
            lost_status = BorrowingStatus.objects.filter(flag_is_lost=True).first()
            doc_lost_status = DocumentStatus.objects.filter(is_lost=True).first()
            if item.legacy_borrowing and lost_status:
                item.legacy_borrowing.borrow_status_id = lost_status
                item.legacy_borrowing.save(update_fields=['borrow_status_id'])
            if item.documents_id and doc_lost_status:
                DocumentsDetail.objects.filter(documents_id=item.documents_id.documents_id).update(document_status_id=doc_lost_status)
            item.status = BorrowRequestItemStatus.LOST
            item.updated_by = user
            item.save(update_fields=['status', 'updated_by', 'updated_at'])
            _borrow_request_log(borrow_request, 'lost', BorrowRequestStatus.HANDED_OVER, BorrowRequestStatus.PARTIALLY_RETURNED, user=user, item=item)
            _refresh_borrow_request_status(borrow_request)
            messages.success(request, 'Đã cập nhật báo mất.')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

        if action == 'cancel_request':
            from_status = borrow_request.status
            borrow_request.status = BorrowRequestStatus.CANCELLED
            borrow_request.updated_by = user
            borrow_request.save(update_fields=['status', 'updated_by', 'updated_at'])
            _borrow_request_log(borrow_request, 'cancel', from_status, BorrowRequestStatus.CANCELLED, user=user)
            messages.success(request, 'Đã hủy yêu cầu.')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

        if action == 'update_request':
            appointment_date = request.POST.get('appointment_date')
            if appointment_date:
                try:
                    borrow_request.appointment_date = datetime.strptime(appointment_date, "%Y-%m-%d").date()
                except ValueError:
                    messages.error(request, 'Ngày hẹn trả không hợp lệ.')
                    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            borrow_request.reference_code = request.POST.get('reference_code') or borrow_request.reference_code
            borrow_request.ticket_code = request.POST.get('ticket_code') or borrow_request.ticket_code
            borrow_request.contact_email = request.POST.get('contact_email') or borrow_request.contact_email
            borrow_request.contact_phone = request.POST.get('contact_phone') or borrow_request.contact_phone
            borrow_request.note = request.POST.get('note') or borrow_request.note
            borrow_request.updated_by = user
            borrow_request.save(update_fields=['appointment_date', 'reference_code', 'ticket_code', 'contact_email', 'contact_phone', 'note', 'updated_by', 'updated_at'])
            _borrow_request_log(borrow_request, 'update', borrow_request.status, borrow_request.status, user=user)
            messages.success(request, 'Đã cập nhật yêu cầu.')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

        if action == 'update_item_appointment':
            item_id = request.POST.get('item_id')
            appointment_date = request.POST.get('appointment_date')
            if not item_id or not appointment_date:
                messages.error(request, 'Vui lòng chọn ngày hẹn trả.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            try:
                appointment_date_value = datetime.strptime(appointment_date, "%Y-%m-%d").date()
            except ValueError:
                messages.error(request, 'Ngày hẹn trả không hợp lệ.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            item = get_object_or_404(BorrowRequestItem, item_id=item_id, borrow_request=borrow_request)
            item.appointment_date = appointment_date_value
            item.updated_by = user
            item.save(update_fields=['appointment_date', 'updated_by', 'updated_at'])
            if item.legacy_borrowing:
                item.legacy_borrowing.appointment_date = appointment_date_value
                item.legacy_borrowing.save(update_fields=['appointment_date'])
            _borrow_request_log(
                borrow_request,
                'Cập nhật hẹn trả',
                borrow_request.status,
                borrow_request.status,
                user=user,
                item=item,
                note=f'Hẹn trả: {appointment_date_value.strftime("%Y-%m-%d")}',
            )
            messages.success(request, 'Đã cập nhật ngày hẹn trả.')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    context = {
        **user_context,
        'user': user,
        'borrow_request': borrow_request,
        'items': items,
        'logs': logs,
        'log_steps': log_steps,
        'preview_key': preview_key,
        'preview_rows': preview_rows,
        'preview_error': preview_error,
        'drop_list_shops': Shop.objects.filter(for_borrow_only=True).order_by('shop_name'),
        'status_choices': BorrowRequestStatus.choices,
    }
    return render(request, 'app_documents/app_borrow_request_detail_v2.html', context)


@csrf_exempt
def api_borrow_request_create(request):
    api_key_setting = getattr(settings, 'BORROW_REQUEST_API_KEY', '') or os.environ.get('BORROW_REQUEST_API_KEY', '')
    if not api_key_setting:
        return JsonResponse({'success': False, 'error': 'API key not configured.'}, status=503)
    client_key = (
        request.headers.get('X-API-KEY')
        or request.headers.get('X-Api-Key')
        or request.headers.get('x-api-key')
        or request.META.get('HTTP_X_API_KEY')
    )
    if not client_key or not secrets.compare_digest(client_key, api_key_setting):
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)
    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST
    borrower_id = data.get('borrower_id')
    needed_date = data.get('needed_date')
    appointment_date = data.get('appointment_date')
    reference_code = data.get('reference_code')
    ticket_code = data.get('ticket_code')
    contact_email = data.get('contact_email')
    contact_phone = data.get('contact_phone')
    note = data.get('note')
    source_system = data.get('source_system')
    external_ref = data.get('external_ref')
    if not borrower_id or not needed_date:
        return JsonResponse({'success': False, 'error': 'borrower_id and needed_date are required.'}, status=400)
    borrower = Shop.objects.filter(shop_id=borrower_id).first()
    if not borrower:
        return JsonResponse({'success': False, 'error': 'Borrower not found.'}, status=404)
    user = request.user if request.user.is_authenticated else None
    borrow_request = BorrowRequest.objects.create(
        borrower=borrower,
        requester=user,
        reference_code=reference_code or None,
        needed_date=needed_date,
        appointment_date=appointment_date or None,
        ticket_code=ticket_code or None,
        contact_email=contact_email or None,
        contact_phone=contact_phone or None,
        note=note or None,
        status=BorrowRequestStatus.PENDING,
        source_system=source_system or None,
        external_ref=external_ref or None,
        created_by=user,
        updated_by=user,
    )
    _borrow_request_log(borrow_request, 'create', None, BorrowRequestStatus.PENDING, user=user, meta={'source_system': source_system, 'external_ref': external_ref})
    return JsonResponse({'success': True, 'request_id': borrow_request.request_id})

@login_required
def borrow_document_management_v2(request):
    user = request.user
    user_context = get_user_context(user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        return redirect('home')

    filters = {}
    choice_document_code = (request.GET.get('document_code') or '').strip()
    choice_borrower = (request.GET.get('borrower') or '').strip()
    choice_status = (request.GET.get('borrow_status') or '').strip()

    if choice_document_code:
        filters['documents_id__documents_code__icontains'] = choice_document_code
    if choice_borrower:
        if choice_borrower.isdigit():
            filters['borrower__shop_id'] = choice_borrower
        else:
            filters['borrower__shop_name__icontains'] = choice_borrower
    if choice_status:
        filters['borrow_status_id'] = choice_status

    borrow_qs = BorrowingDocument.objects.select_related(
        'documents_id', 'borrower', 'borrow_status_id', 'lender'
    ).order_by('-borrow_date', '-borrow_id')
    if filters:
        borrow_qs = borrow_qs.filter(**filters)

    paginator = Paginator(borrow_qs, 25)
    page_number = request.GET.get('page')
    borrow_list = paginator.get_page(page_number)

    current = borrow_list.number if borrow_list else 1
    total_pages = paginator.num_pages if paginator else 1
    start_range = max(current - 2, 1)
    end_range = min(current + 2, total_pages)
    page_range_custom = list(range(1, min(2, total_pages) + 1))
    page_range_custom += list(range(start_range, end_range + 1))
    page_range_custom += list(range(max(total_pages - 1, 1), total_pages + 1))
    page_range_custom = sorted(set([p for p in page_range_custom if 1 <= p <= total_pages]))

    qs_no_page = request.GET.copy()
    qs_no_page.pop('page', None)
    base_qs = qs_no_page.urlencode()

    context = {
        **user_context,
        'user': user,
        'borrow_list': borrow_list,
        'page_range_custom': page_range_custom,
        'paginator': paginator,
        'base_qs': base_qs,
        'drop_list_shops': Shop.objects.filter(for_borrow_only=True).order_by('shop_name'),
        'drop_list_borrowing_status': BorrowingStatus.objects.all().order_by('borrow_status_name'),
        'filters': {
            'document_code': choice_document_code,
            'borrower': choice_borrower,
            'borrow_status': choice_status,
        },
    }
    return render(request, 'app_documents/app_borrow_document_v2.html', context)


@login_required
def request_borrow_document_view(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            document_id = data.get('document_id')
            borrower_id = data.get('borrower_id')
            borrow_date = data.get('borrow_date')
            ticket_code = data.get('ticket_code')
            appointment_date = data.get('appointment_date')
            borrower_detail = data.get('borrower_detail')
            note = data.get('note')
            # Kiểm tra chứng từ có tồn tại không
            try:
                documents = DocumentsDetail.objects.get(documents_id=document_id)
            except DocumentsDetail.DoesNotExist:
                return JsonResponse({"success": False, "message": "Chứng từ không tồn tại."}, status=404)
            # Kiểm tra phòng ban có tồn tại không
            try:
                borrower = Shop.objects.get(shop_id=borrower_id)
            except Shop.DoesNotExist:
                return JsonResponse({"success": False, "message": "Phòng ban không tồn tại."}, status=404)
            # Kiểm tra trạng thái mượn có tồn tại không
            try:
                borrow_status = BorrowingStatus.objects.get(flag_is_borrowing=True)
            except BorrowingStatus.DoesNotExist:
                return JsonResponse({"success": False, "message": "Không tìm thấy trạng thái mượn."}, status=404)
            # Kiểm tra xem có bản ghi mượn nào chưa trả hay không
            borrow_document = BorrowingDocument.objects.filter(
                documents_id=document_id,
                borrow_status_id__flag_return=False
            ).first()
            # Nếu chưa có chứng từ mượn, thì tạo 1 transaction mượn chứng từ
            if not borrow_document:
                # Tạo mới bản ghi BorrowingDocument
                BorrowingDocument.objects.create(
                    documents_id=documents,
                    borrow_date=borrow_date,
                    appointment_date=appointment_date,
                    lender=request.user,
                    borrower=borrower,
                    borrower_detail = borrower_detail ,
                    ticket_code= ticket_code,
                    note=note,
                    borrow_status_id=borrow_status
                )
                # Cập nhật trạng thái của chứng từ thành trạng thái có `is_borrow=True` đang mượn. 
                document_status = DocumentStatus.objects.get(is_borrow=True)
                if document_status:
                    documents.document_status_id = document_status
                    documents.save()
            else:
                # Cập nhật bản ghi mượn hiện tại nếu đã tồn tại mà chưa trả
                JsonResponse({'success': True, 'message': 'Chứng từ này đang cho mượn rồi. Vui lòng kiểm tra lại'})
            return JsonResponse({'success': True, 'message': 'Cho mượn chứng từ thành công.'})
        except Exception as e:
            return JsonResponse({"success": False, "message": f"Lỗi: {str(e)}"}, status=400)
    return JsonResponse({"success": False, "message": "Phương thức không hợp lệ."}, status=400)

@login_required
def manage_borrow_document(request, document_id, action):
    if request.method == 'POST':  # Chỉ chấp nhận POST requests
        # Lấy document dựa trên document_id
        document = get_object_or_404(DocumentsDetail, documents_id=document_id)
        # Lấy borrow record gần nhất cho document này với trạng thái đang mượn
        borrow_record_active = BorrowingDocument.objects.filter(documents_id=document, borrow_status_id__flag_is_borrowing=True).first()
        try: 
            data = json.loads(request.body) 
            return_date = data.get('return_date') 
            if return_date == '': 
                return_date = datetime.now()
        except Exception as e:
            return_date = datetime.now()
            return JsonResponse({"success": False, "message": f"Lỗi: {str(e)}"}, status=400)
        
        if borrow_record_active:
            if action == 'return':
                # Cập nhật trạng thái document và borrow record khi hoàn trả
                document_status = DocumentStatus.objects.get(is_checked=True)  # Lấy trạng thái "Đã duyệt"
                if document_status:
                    document.document_status_id = document_status
                    document.save()
                # Lấy trạng thái "Đã trả" của borrow record
                borrow_status = BorrowingStatus.objects.get(flag_return=True) 
                if borrow_status:
                    borrow_record_active.borrow_status_id = borrow_status
                    borrow_record_active.return_date = return_date
                    borrow_record_active.save()
            elif action == 'lost':
                # Cập nhật trạng thái document và borrow record khi báo mất
                document_status = DocumentStatus.objects.get(is_lost=True)  # Lấy trạng thái "Đã mất"
                if document_status:
                    document.document_status_id = document_status
                    document.save()
                # Lấy trạng thái "Đã mất" của borrow record
                borrow_status = BorrowingStatus.objects.get(flag_is_lost=True) 
                if borrow_status:
                    borrow_record_active.borrow_status_id = borrow_status
                    borrow_record_active.save()
            else:
                return JsonResponse({'status': 'error', 'message': 'Invalid action'}, status=400)
            return JsonResponse({'status': 'Thao tác thành công?'})
        return JsonResponse({'status': 'error', 'message': 'Không tìm thấy chứng từ mượn, hỏi Admin!'}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)
