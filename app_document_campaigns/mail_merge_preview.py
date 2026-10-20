"""UI prototype only: no campaigns, uploads, links or deliveries are persisted."""
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET


@login_required
@require_GET
def preview(request):
    from .views import _is_campaign_admin
    if not _is_campaign_admin(request.user):
        return HttpResponse('Chỉ admin được xem bản thiết kế Mail Merge.', status=403)
    return render(request, 'app_document_campaigns/mail_merge_preview.html', {
        'creating': request.GET.get('mode') == 'create',
        'steps': ['Cấu hình', 'Tải dữ liệu', 'Thiết kế bảng', 'Mapping PGD / email',
                  'Phát hành & theo dõi', 'Chốt & báo cáo'],
    })
