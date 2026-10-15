"""Read-only portals for current receiving/checking data, scoped to the caller."""
from datetime import date, datetime
from io import BytesIO

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.db.models import Exists, OuterRef
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from .models import (
    BusinessType, DocumentsDetail, DocumentType, Folder, FolderType, Shop,
)
from .utils import get_user_context

RECEIVING_HEADERS = [
    'STT', 'Mã quyển', 'Phòng Giao Dịch', 'Ngày phát sinh', 'Loại quyển chứng từ',
    'Phiên bản', 'Ngày nhận', 'Trạng thái', 'Mã thùng', 'Người nhận',
]
EXCEL_MAX_DATA_ROWS = 1_048_575  # 1,048,576 rows minus the header.

CHECKING_HEADERS = [
    'STT', 'Mã quyển', 'PGD', 'Ngày phát sinh', 'Ngày nhận', 'Loại quyển chứng từ',
    'Mã HĐCC/GNN', 'Khách hàng', 'Loại chứng từ', 'Nghiệp vụ', 'Trạng thái',
    'Duyệt', 'Ngày duyệt', 'Người duyệt', 'Mã thùng', 'Mã thùng đối tác',
]


def value(obj, path, default=''):
    for name in path.split('.'):
        obj = getattr(obj, name, None)
        if obj is None:
            return default
    return obj


def shop_label(shop):
    # The operational PGD code/name is stored in shop_name, as on both screens.
    # shop_code is a separate four-digit internal code.
    return value(shop, 'shop_name')


def receiving_row(folder, index):
    version = 'Gốc' if folder.is_original else 'Bổ sung'
    if folder.is_issue:
        version += ' PSCT'
    status = value(folder, 'folder_status_id.folder_status_name')
    if folder.is_late:
        status += ' Trễ hạn'
    elif folder.is_on_time:
        status += ' Đúng hạn'
    package = value(folder, 'package_id.package_code')
    partner = value(folder, 'package_id.partnerpackage.partner_package_code')
    packages = ([f'F88: {package}'] if package else []) + ([f'ĐT: {partner}'] if partner else [])
    return [index, folder.folder_code, shop_label(folder.shop_id), folder.folder_created_date,
            value(folder, 'folder_type_id.folder_type_name'), version, folder.lastest_received_date,
            status.strip(), ' | '.join(packages) or '—', value(folder, 'lastest_received_by.username')]


def checking_row(document, index):
    # Match the checking UI's customer source, independently of contract-first code.
    customer = (value(document, 'loan_id.customer_name') if document.loan_id
                else value(document, 'contract_id.customer_id.customer_name'))
    # Match the visible table's capfirst filter without lowercasing the rest.
    customer = customer[:1].upper() + customer[1:] if customer else ''
    return [index, value(document, 'folder_id.folder_code'), shop_label(document.shop_id),
            value(document, 'folder_id.folder_created_date', None),
            value(document, 'folder_id.lastest_received_date', None),
            value(document, 'folder_id.folder_type_id.folder_type_name'),
            value(document, 'contract_id.contract_code') or value(document, 'loan_id.loan_code'),
            customer, value(document, 'document_type_id.document_type_name'),
            value(document, 'business_type_id.business_type_name'),
            value(document, 'document_status_id.documents_status_name'),
            value(document, 'status_id.checking_status_name', 'Chưa duyệt'),
            document.lastest_checked_date, value(document, 'lastest_checked_by.username'),
            value(document, 'package_id.package_code'),
            value(document, 'package_id.partnerpackage.partner_package_code')]


def date_range(raw, label):
    parts = raw.strip().split(' to ')
    if len(parts) not in (1, 2):
        raise ValueError(f'{label}: dùng YYYY-MM-DD hoặc YYYY-MM-DD to YYYY-MM-DD.')
    try:
        start, end = date.fromisoformat(parts[0]), date.fromisoformat(parts[-1])
    except ValueError:
        raise ValueError(f'{label}: ngày không hợp lệ.') from None
    if start > end:
        raise ValueError(f'{label}: từ ngày phải nhỏ hơn hoặc bằng đến ngày.')
    return start, end


def filter_specs(kind, user):
    folder_prefix = 'folder_id__' if kind == 'checking' else ''
    document_prefix = 'document:' if kind == 'receiving' else ''
    return [
        ('choice_shop', 'Phòng giao dịch', 'shop', Shop.objects.all().order_by('shop_name')),
        ('choice_folder_type', 'Loại quyển chứng từ', folder_prefix + 'folder_type_id', FolderType.objects.all().order_by('folder_type_name')),
        ('filter_folder_date', 'Ngày phát sinh', folder_prefix + 'folder_created_date__range', 'date'),
        ('filter_receive_date', 'Ngày nhận', folder_prefix + 'lastest_received_date__date__range', 'date'),
        ('filter_package', 'Mã thùng', 'package_id__package_code__icontains', None),
        ('filter_partner_package', 'Mã thùng đối tác', 'package_id__partnerpackage__partner_package_code__icontains', None),
        ('filtercheckdate', 'Ngày duyệt', document_prefix + 'lastest_checked_date__date__range', 'date'),
        ('choice_user_duyet', 'Người duyệt', document_prefix + 'lastest_checked_by__username__icontains', None),
        ('choice_lastest_receiver', 'Người nhận', folder_prefix + 'lastest_received_by__username__icontains', None),
        ('choicebusinesstype', 'Nghiệp vụ', document_prefix + 'business_type_id', BusinessType.objects.filter(allow_checking=True).order_by('business_type_name')),
        ('choice_document_type', 'Loại chứng từ', document_prefix + 'document_type_id', DocumentType.objects.all().order_by('document_type_name')),
    ]


def report_queryset(kind, user, params, specs):
    model = DocumentsDetail if kind == 'checking' else Folder
    # This module is admin-only, matching the KPI dashboard; allow all PGDs.
    queryset = model.objects.all()
    filters, document_filters = {}, {}
    for key, label, lookup, options in specs:
        if lookup == 'shop':
            shop_ids = params.getlist(key)
            if shop_ids:
                if any(not shop_id.isdigit() for shop_id in shop_ids):
                    raise ValueError('Phòng giao dịch: giá trị không hợp lệ.')
                filters['shop_id__in'] = [int(shop_id) for shop_id in shop_ids]
            continue
        raw = params.get(key, '').strip()
        if not raw:
            continue
        target_filters = document_filters if lookup.startswith('document:') else filters
        lookup = lookup.removeprefix('document:')
        if options == 'date':
            target_filters[lookup] = date_range(raw, label)
        elif options is not None:
            if not raw.isdigit():
                raise ValueError(f'{label}: giá trị không hợp lệ.')
            target_filters[lookup] = int(raw)
        else:
            target_filters[lookup] = raw
    if not filters and not document_filters:
        return queryset.none()
    queryset = queryset.filter(**filters)
    if document_filters:
        # All document conditions must match the same document; keep one row per folder.
        matching_documents = DocumentsDetail.objects.filter(folder_id=OuterRef('pk'), **document_filters)
        queryset = queryset.filter(Exists(matching_documents))
    if kind == 'checking':
        return queryset.filter(business_type_id__allow_checking=True).select_related(
            'shop_id', 'folder_id', 'folder_id__folder_type_id', 'loan_id',
            'contract_id__customer_id', 'document_type_id', 'business_type_id',
            'document_status_id', 'status_id', 'lastest_checked_by',
            'package_id__partnerpackage',
        ).order_by('folder_id__folder_created_date', 'documents_id')
    return queryset.select_related(
        'shop_id', 'folder_type_id', 'folder_status_id', 'lastest_received_by',
        'package_id__partnerpackage',
    ).order_by('-folder_created_date', 'folder_id')


def excel_response(headers, rows, kind):
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet('Nhan chung tu' if kind == 'receiving' else 'Duyet chung tu')
    sheet.freeze_panes = 'A2'
    for index, header in enumerate(headers, 1):
        sheet.column_dimensions[get_column_letter(index)].width = 8 if index == 1 else min(44, max(22, len(header) + 4))
    header_cells = []
    for header in headers:
        cell = WriteOnlyCell(sheet, value=header)
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='00844A')
        header_cells.append(cell)
    sheet.append(header_cells)
    count = 0
    for row in rows:
        cells = []
        for entry in row:
            if isinstance(entry, datetime) and timezone.is_aware(entry):
                entry = timezone.make_naive(entry, timezone.get_default_timezone())
            cell = WriteOnlyCell(sheet, value=entry)
            if isinstance(entry, str):
                cell.data_type = 's'  # Preserve IDs and raw strings, including leading '='.
                cell.number_format = '@'
            elif isinstance(entry, datetime):
                cell.number_format = 'dd/mm/yyyy hh:mm'
            elif isinstance(entry, date):
                cell.number_format = 'dd/mm/yyyy'
            cells.append(cell)
        sheet.append(cells)
        count += 1
    sheet.auto_filter.ref = f'A1:{get_column_letter(len(headers))}{count + 1}'
    output = BytesIO()
    workbook.save(output)
    response = HttpResponse(output.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    stamp = timezone.localtime() if settings.USE_TZ else timezone.now()
    response['Content-Disposition'] = f'attachment; filename="{kind}_{stamp:%Y%m%d_%H%M%S}.xlsx"'
    response['Cache-Control'] = 'no-store'
    return response


@login_required
@require_GET
def report_portal(request):
    context = get_user_context(request.user)
    if not context.get('is_admin'):
        return HttpResponse('Bạn không có quyền xuất báo cáo chứng từ.', status=403)
    kind = request.GET.get('report_kind', 'receiving')
    if kind not in ('receiving', 'checking'):
        return HttpResponse('Loại báo cáo không hợp lệ.', status=400)
    specs = filter_specs(kind, request.user)
    headers = CHECKING_HEADERS if kind == 'checking' else RECEIVING_HEADERS
    row_builder = checking_row if kind == 'checking' else receiving_row
    limit = min(EXCEL_MAX_DATA_ROWS, getattr(settings, 'DOCUMENT_RAW_EXPORT_MAX_ROWS', EXCEL_MAX_DATA_ROWS))
    error, total, rows = '', 0, []
    has_filters = any(request.GET.get(key, '').strip() for key, *_ in specs)
    try:
        queryset = report_queryset(kind, request.user, request.GET, specs)
        total = queryset.count()
        if total > limit:
            raise ValueError(f'Bộ lọc tìm thấy {total:,} dòng, vượt giới hạn {limit:,} dòng dữ liệu/file Excel (đã trừ dòng tiêu đề). Hãy thu hẹp bộ lọc rồi xuất lại.')
        if request.GET.get('download') == '1':
            if not has_filters:
                raise ValueError('Hãy chọn ít nhất một điều kiện lọc trước khi xuất.')
            return excel_response(headers, (row_builder(item, i) for i, item in enumerate(queryset.iterator(chunk_size=2000), 1)), kind)
        rows = [row_builder(item, i) for i, item in enumerate(queryset[:25], 1)]
    except ValueError as exc:
        error = str(exc)
    fields = []
    for index, (key, label, lookup, options) in enumerate(specs):
        choices = None
        if options is not None and options != 'date':
            choices = options if isinstance(options, list) else [(str(obj.pk), str(obj)) for obj in options]
        fields.append({'name': key, 'label': label, 'value': request.GET.get(key, ''),
                       'choices': choices, 'is_date': options == 'date', 'multiple': key == 'choice_shop',
                       'selected_values': request.GET.getlist(key), 'primary': index < 4})
    context.update({
        'active_tab': 'export', 'selected_shop_count': len(request.GET.getlist('choice_shop')),
        'kind': kind, 'report_title': 'Báo cáo nhận chứng từ' if kind == 'receiving' else 'Báo cáo duyệt chứng từ',
        'filters_expanded': any(request.GET.get(key, '').strip() for key, *_ in specs[4:]),
        'fields': fields, 'headers': headers, 'rows': rows, 'total': total, 'error': error,
        'can_download': has_filters and not error and total <= limit, 'export_limit': limit,
    })
    response = render(request, 'app_documents/raw_report_portal.html', context, status=400 if error else 200)
    response['Cache-Control'] = 'no-store'
    return response
