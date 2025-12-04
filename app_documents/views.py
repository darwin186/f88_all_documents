from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.urls import reverse, path
from django.views.decorators.http import require_http_methods
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
from django.db.models import Count, Max, Q, Min
from django.forms.models import model_to_dict
from django.core.serializers.json import DjangoJSONEncoder
from urllib.parse import urlencode
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
import json
import re
import logging
import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from django.db.models.functions import ExtractHour
import openpyxl
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo
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
    Partner,
    Region,
    HistoricalFolder,
    HistoricalDocuments,
    ChangeRequest,
    BorrowingDocument,
    BorrowingStatus,
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
def checking_transaction_view(request):
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
                            if checking_status_instance_log.checking_status_code != '103':
                                CheckingAdditional.objects.filter(additional=documents_detail_instance_log).update(is_valid=False) 
                            # Nếu trạng thái chứng từ đổi thành hẹn bổ sung thì đánh dấu is_valid trong AdditionalChecking là True
                            if checking_status_instance_log.checking_status_code == '103':
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
                redirect_url = f"{reverse('checking_transaction')}?{urlencode(filter_params)}"
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
        return render(request, "app_documents/app_checkingtransaction.html",context)

# Lịch sử duyệt chứng từ
@login_required
def fetch_history(request, document_id):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        history = DocumentsTransactionChecking.objects.filter(documents_id=document_id).values(
            'trans_created_date', 
            'trans_created_by__username', 
            'checking_status_id__checking_status_name'
            )
        return JsonResponse(list(history), safe=False)
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
                # Nếu user đã CheckingAdditional thành công thì chuyển trạng thái của checkingdocuments status_id thành 3
                already_check_documents_103  = CheckingTransactionStatus.objects.get(checking_status_code = '103') # Instance của kiểm Thiếu chứng từ hẹn bổ sung
                already_documents_status_102 = DocumentStatus.objects.get(documents_status_code = '102') # Instance của trạng thái chứng từ đã duyệt
                 # Nếu user đã CheckingAdditional thành công thì chuyển trạng thái của checkingdocuments status_id thành 3 
                DocumentsDetail.objects.filter(documents_id = document_id).update(
                                                                                status_id = already_check_documents_103.status_id , # Trạng thái duyệt là hẹn bổ sung 
                                                                                document_status_id = already_documents_status_102.status_id, # ID  Đã duyệt lấy theo code
                                                                                lastest_checked_date = timezone.now(),
                                                                                lastest_checked_by = request.user)
                # Nếu trạng thái hiện tại của chứng từ khác hẹn bổ sung thì có nghĩa là đang thay đổi trạng thái, từ đó log thay đổi.
                if previous_check_status != '3':
                    DocumentsTransactionChecking.objects.create(
                                        documents_id = document,
                                        trans_created_date = additional_create_date,
                                        trans_created_by=request.user,
                                        checking_status_id = already_check_documents_103,
                                        )
            except IntegrityError:
                # Handle the case where a CheckingAdditional instance already exists for this document
                existing_additional = CheckingAdditional.objects.get(additional=document)
                existing_additional.additional_note = additional_note
                existing_additional.date_addition = date_addition
                existing_additional.is_valid = True
                existing_additional.save()
                messages.info(request, 'Cập nhật dữ liệu hẹn chứng từ thành công')
                # Nếu user đã CheckingAdditional thành công thì chuyển trạng thái của checkingdocuments status_id thành 3
                DocumentsDetail.objects.filter(documents_id = document_id).update(status_id = CheckingTransactionStatus.objects.get(checking_status_code='103'))
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
        try:
            with transaction.atomic():
                for document_id in selected_documents:
                    documents_detail_instance = DocumentsDetail.objects.filter(documents_id=document_id)
                    documents_detail_instance_log = DocumentsDetail.objects.get(documents_id=document_id)
                    documents_status_choice_instance = CheckingTransactionStatus.objects.get(status_id=documents_status_choice)
                    documents_detail_instance.update(
                        status_id = documents_status_choice_instance, 
                        document_status_id = DocumentStatus.objects.get(documents_status_code='102'),
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
                    if documents_status_choice_instance.checking_status_code == '103' :
                        CheckingAdditional.objects.create(
                            additional = documents_detail_instance_log, 
                            is_valid=True,
                            additional_note = additional_bulk_note_choice if additional_bulk_note_choice else None,
                            date_addition = additional_bulk_date_choice if additional_bulk_date_choice else None,
                            additional_created_date = checking_time,
                            additional_created_by = user
                            )
                messages.success(request, f'Duyệt {len(selected_items)} quyển chứng từ thành công') 
                return JsonResponse({'success': True})
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
def receive_folder_view(request): 
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
                            message_check_on_time =  check_on_time(folder_detail_instance_log,lasted_received_date_submit) # Đánh dấu lại tối ưu sau
                            messages.add_message(request, messages.INFO, message_check_on_time) 
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
                redirect_url = f"{reverse('receiving_transaction')}?{urlencode(filter_params)}"
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
        return render( request, "app_documents/app_receivingtransaction.html" , context)

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
            with transaction.atomic():
                for folder_id in selected_folder:
                    folder_id_instance = Folder.objects.get(folder_id=folder_id)
                    package_id_instance = Package.objects.get(package_code=package_choice)
                    folder_status_instance = FolderStatus.objects.get(folder_status_id=folder_status_choice)
                    # Cập nhật trạng thái quyển chứng từ
                    folder = folder_id_instance
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
                    document_details = DocumentsDetail.objects.select_for_update().filter(folder_id = folder_id)
                    with transaction.atomic(): 
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
                redirect_url = f"{reverse('receiving_transaction')}?{urlencode(filter_params)}"
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
    package_pattern = r'^(CIMB|VH)-(\d{6})-(\d)(\d{2})$'
    match = re.match(package_pattern, value)
    profile = UserProfile.objects.get(user=user) 
    region = profile.region.region_code
    if not match:
        return {'is_valid': False, 
                'error': "Tên thùng phải tuân thủ đúng định dạng 'TYPE-yymmdd-axx'. Với TYPE là loại thùng.\nyymmdd: là năm-tháng-ngày-hiện tại.\na sẽ là mã vùng của bạn\nxx phải là chữ số thứ tự từ 01-99"}
    # Extract components from the package code
    prefix_part, date_part, region_sequence_part, sequence_part = match.groups()
    region_code_part = region_sequence_part[0]
    sequence_part = sequence_part[:]
   # Check if sequence is numeric and in the proper range
    if not sequence_part.isdigit() or not (1 <= int(sequence_part) <= 99):
        return {    'is_valid': False, 
                    'error': "xx phải là số thứ tự từ 01 đến 99."}
    package_type_list = list(FolderType.objects.values_list('package_type', flat=True))
    if prefix_part not in package_type_list:
        return {  'is_valid': False, 
                    'error': "Bạn phải chọn loại thùng."}
    if region_code_part != region:
        return {    'is_valid': False, 
                    'error': f"Bạn tạo sai thùng của miền! Bạn là CTV miền {profile.region.region_name}. Vui lòng tạo thùng với code {region}."}
    existing_codes = Package.objects.filter(package_code__startswith=f'{prefix_part}-{date_part}-{region_code_part}')
    if existing_codes.exists():
        last_sequence = max(int(code.package_code.split('-')[-1][1:]) for code in existing_codes)
        if int(sequence_part) <= last_sequence:
            return {'is_valid': False, 'error': "Thùng với số thứ tự này đã tồn tại. Vui lòng tạo thùng với số thứ tự cao hơn."}
    if Package.objects.filter(package_code=value).exists():
        return {'is_valid': False, 'error': "Thùng đã tồn tại trong hệ thống. Vui lòng nhập lại"}
    return {'is_valid': True}
    
# View cho phép tạo thùng mới
@login_required
def create_package_view(request, user_id):
    user= User.objects.get(pk=user_id)
    user_context = get_user_context(request.user)
    user_profiles = UserProfile.objects.get(user=user)
    package_type = FolderType.objects.all()
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


#BORROW
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
